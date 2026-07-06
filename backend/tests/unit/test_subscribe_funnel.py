"""Subscription funnel (issue #424): source attribution must be bounded, and the outbound
entry point must record a click + redirect to the config-driven destination. These pin the
contract documented in docs/features/subscription-funnel.md so a refactor can't silently
change event names, drop attribution, or unbound the Redis key space.
"""
import pytest
from fastapi import BackgroundTasks

from src.routers import subscribe as sub


class FakeRedis:
    def __init__(self):
        self.calls: list[tuple] = []

    async def zincrby(self, key, amount, member):
        self.calls.append((key, amount, member))


def test_normalize_source_keeps_valid_slot():
    assert sub.normalize_source("article_detail_end") == "article_detail_end"


def test_normalize_source_lowercases_and_strips():
    assert sub.normalize_source("  Articles_Hero  ") == "articles_hero"


@pytest.mark.parametrize("bad", [None, "", "has space", "bad!chars", "x" * 65, "中文來源"])
def test_normalize_source_falls_back_to_unknown(bad):
    # Malformed slots are counted (as `unknown`), never rejected, and never grow the key
    # space with arbitrary members.
    assert sub.normalize_source(bad) == "unknown"


async def test_outbound_records_click_and_redirects(monkeypatch):
    fake = FakeRedis()

    async def fake_get_redis():
        return fake

    monkeypatch.setattr(sub, "get_redis", fake_get_redis)
    monkeypatch.setattr(sub.settings, "newsletter_subscribe_url", "https://example.com/sub")

    bt = BackgroundTasks()
    resp = await sub.subscribe_outbound(bt, source="Articles_Hero")

    assert resp.status_code == 302
    assert resp.headers["location"] == "https://example.com/sub"

    await bt()  # background tasks run after the response is returned
    assert fake.calls == [(sub.CLICK_KEY, 1, "articles_hero")]


async def test_view_beacon_records_view(monkeypatch):
    fake = FakeRedis()

    async def fake_get_redis():
        return fake

    monkeypatch.setattr(sub, "get_redis", fake_get_redis)

    bt = BackgroundTasks()
    event = sub.SubscribeView(source="ticker_page")
    resp = await sub.subscribe_view(event, bt)

    assert resp == {"status": "accepted"}
    await bt()
    assert fake.calls == [(sub.VIEW_KEY, 1, "ticker_page")]


async def test_recording_survives_missing_redis(monkeypatch):
    # No cache available → funnel must not raise (it must never break the redirect).
    async def no_redis():
        return None

    monkeypatch.setattr(sub, "get_redis", no_redis)
    await sub._record(sub.CLICK_KEY, "article_detail_end")  # should be a no-op, not raise
