"""Self-check for the notification producer's high-water-mark dedup + cold-start guard."""
import asyncio
from types import SimpleNamespace

import src.services.notification_producer as prod


def _ep(ct):
    return SimpleNamespace(
        id=f"ep{ct}", podcast_name="P", episode_title=f"t{ct}",
        created_time=ct, related_tickers=[], tags=[],
    )


def _run(feed):
    """Drive scan_and_notify with a fake Redis marker + fake feed; return notified ids."""
    store = {}
    notified = []

    async def fake_get(k):
        return store.get(k)

    async def fake_set(k, v, ttl=300):
        store[k] = v
        return True

    async def fake_recent(limit=50):
        return feed

    def fake_notify(eps):
        notified.extend(e.id for e in eps)
        return len(eps)

    prod.cache_get = fake_get
    prod.cache_set = fake_set
    prod._podcast_service = SimpleNamespace(get_recent_episodes=fake_recent)
    prod._notify_for_episodes = fake_notify
    return store, notified


def test_cold_start_sends_nothing_but_sets_marker():
    store, notified = _run([_ep(100), _ep(200)])
    sent = asyncio.run(prod.scan_and_notify())
    assert sent == 0
    assert notified == []                       # backlog not blasted
    assert store[prod._MARKER_KEY] == "200"     # marker = max created_time


def test_only_newer_than_marker_notified():
    store, notified = _run([_ep(100), _ep(200)])
    asyncio.run(prod.scan_and_notify())         # cold start -> marker 200
    # New episode arrives (created 300); old ones must not re-notify.
    prod._podcast_service.get_recent_episodes = lambda limit=50: _async([_ep(200), _ep(300)])
    asyncio.run(prod.scan_and_notify())
    assert notified == ["ep300"]
    assert store[prod._MARKER_KEY] == "300"


async def _async(v):
    return v


if __name__ == "__main__":
    test_cold_start_sends_nothing_but_sets_marker()
    test_only_newer_than_marker_notified()
    print("ok")
