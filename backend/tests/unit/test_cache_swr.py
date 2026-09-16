"""cache_swr: stale-while-revalidate + single-flight for hot, expensive keys.

The home feed's first visitor after a 10-minute TTL used to rebuild it (9-13s) while
every concurrent visitor rebuilt it too.
"""
import asyncio
import json

import pytest

from src.cache import redis_client as rc


@pytest.fixture
def store(monkeypatch):
    data = {}

    async def _get(key):
        return data.get(key)

    async def _set(key, value, ttl=300):
        data[key] = value
        return True

    monkeypatch.setattr(rc, "cache_get", _get)
    monkeypatch.setattr(rc, "cache_set", _set)
    rc._inflight.clear()
    return data


def _counter(value, delay=0.0, fail=False):
    calls = []

    async def compute():
        calls.append(1)
        await asyncio.sleep(delay)
        if fail:
            raise RuntimeError("db down")
        return value

    return compute, calls


async def test_concurrent_misses_share_one_compute(store):
    compute, calls = _counter(["a"], delay=0.05)
    out = await asyncio.gather(*[rc.cache_swr("k", compute, ttl=60, stale=600) for _ in range(5)])
    assert out == [["a"]] * 5 and len(calls) == 1
    assert json.loads(store["k"])["v"] == ["a"]


async def test_fresh_hit_never_computes(store):
    store["k"] = json.dumps({"v": ["cached"], "t": 9e12})
    compute, calls = _counter(["new"])
    assert await rc.cache_swr("k", compute, ttl=60, stale=600) == ["cached"] and calls == []


async def test_stale_hit_returns_old_value_and_refreshes_once(store):
    store["k"] = json.dumps({"v": ["old"], "t": 0})
    compute, calls = _counter(["new"], delay=0.05)
    out = await asyncio.gather(*[rc.cache_swr("k", compute, ttl=60, stale=600) for _ in range(5)])
    assert out == [["old"]] * 5  # nobody waits on the rebuild
    await asyncio.sleep(0.1)
    assert len(calls) == 1 and json.loads(store["k"])["v"] == ["new"]
    assert not rc._inflight


async def test_failed_background_refresh_keeps_serving_stale(store):
    store["k"] = json.dumps({"v": ["old"], "t": 0})
    compute, _ = _counter(None, fail=True)
    assert await rc.cache_swr("k", compute, ttl=60, stale=600) == ["old"]
    await asyncio.sleep(0.01)
    assert json.loads(store["k"])["v"] == ["old"] and not rc._inflight


async def test_failed_miss_raises_and_does_not_wedge_the_key(store):
    compute, _ = _counter(None, fail=True)
    with pytest.raises(RuntimeError):
        await rc.cache_swr("k", compute, ttl=60, stale=600)
    ok, calls = _counter(["b"])
    assert await rc.cache_swr("k", ok, ttl=60, stale=600) == ["b"] and len(calls) == 1


async def test_pre_swr_value_is_rebuilt_not_served(store):
    store["k"] = json.dumps([{"id": "legacy list format"}])
    compute, calls = _counter(["b"])
    assert await rc.cache_swr("k", compute, ttl=60, stale=600) == ["b"] and len(calls) == 1
