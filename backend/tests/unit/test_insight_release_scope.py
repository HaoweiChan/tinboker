"""Unit tests for /picks window scoping in InsightService.

Picks have their own window (``release_picks_max_age_days``, default off) so
7/30/90-day returns can settle; each row reports ``episode_public`` from the
episode window (``release_episode_max_age_days``) — and the cache key must
isolate per window pair.
"""

import asyncio

import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock

from src.services import insight_service as svc


def test_recency_floor_disabled_by_default(monkeypatch):
    monkeypatch.setattr(svc.settings, "release_picks_max_age_days", 0)
    monkeypatch.setattr(svc.settings, "release_episode_max_age_days", 60)  # episode window must not leak in
    assert svc._release_recency_floor() is None


def test_recency_floor_enabled(monkeypatch):
    monkeypatch.setattr(svc.settings, "release_picks_max_age_days", 30)
    assert svc._release_recency_floor() == date.today() - timedelta(days=30)


def test_scope_tag_tracks_both_windows(monkeypatch):
    monkeypatch.setattr(svc.settings, "release_picks_max_age_days", 0)
    monkeypatch.setattr(svc.settings, "release_episode_max_age_days", 0)
    assert svc._scope_tag().startswith("p0e0:visibility-v1:")
    monkeypatch.setattr(svc.settings, "release_episode_max_age_days", 60)
    assert svc._scope_tag().startswith("p0e60:visibility-v1:")


def test_episode_public_follows_episode_window(monkeypatch):
    monkeypatch.setattr(svc.settings, "release_episode_max_age_days", 60)
    today = date.today()
    assert svc._episode_public((today - timedelta(days=5)).isoformat() + "T00:00:00Z") is True
    assert svc._episode_public((today - timedelta(days=120)).isoformat() + "T00:00:00Z") is False
    monkeypatch.setattr(svc.settings, "release_episode_max_age_days", 0)
    assert svc._episode_public((today - timedelta(days=120)).isoformat() + "T00:00:00Z") is True


def test_floor_keeps_recent_drops_old(monkeypatch):
    monkeypatch.setattr(svc.settings, "release_picks_max_age_days", 30)
    floor = svc._release_recency_floor()
    today = date.today()
    recent = (today - timedelta(days=5)).isoformat() + "T00:00:00Z"
    old = (today - timedelta(days=120)).isoformat() + "T00:00:00Z"
    assert svc._in_range(recent, floor, today) is True
    assert svc._in_range(old, floor, today) is False


def test_recent_before_caps_launch_day_and_isolates_cache(monkeypatch):
    """/picks 已揭曉 pages with ``before``: the mirror gets a ``<=`` end-of-day filter and
    the cache key differs from the plain feed."""
    monkeypatch.setattr(svc.settings, "release_picks_max_age_days", 0)
    seen = {}
    monkeypatch.setattr(svc, "cache_get", AsyncMock(return_value=None))
    monkeypatch.setattr(svc, "cache_set", AsyncMock(side_effect=lambda k, v, ttl=None: seen.setdefault("key", k)))

    class _FS:
        def query_collection_group(self, collection, filters, order_by, direction, limit):
            seen["filters"] = filters
            return []

    service = svc.InsightService.__new__(svc.InsightService)
    service._fs = _FS()
    out = asyncio.run(service.get_recent(limit=50, before=date(2026, 8, 31)))
    assert out == []
    assert seen["filters"] == [("podcast_launch_time", "<=", "2026-08-31T23:59:59Z")]
    assert seen.get("key", "").endswith(":50:2026-08-31")


@pytest.mark.parametrize("environment,visible", [("development", True), ("production", False), ("staging", False)])
@pytest.mark.parametrize("languages", [[], ["zh-TW"]])
async def test_new_shows_hidden_from_all_insight_reads(monkeypatch, environment, visible, languages):
    monkeypatch.setattr(svc.settings, "environment", environment)
    monkeypatch.setattr(svc.settings, "release_podcast_languages", languages)
    monkeypatch.setattr(svc.settings, "release_picks_max_age_days", 0)
    monkeypatch.setattr(svc, "cache_get", AsyncMock(return_value=None))
    monkeypatch.setattr(svc, "cache_set", AsyncMock())
    today = date.today().isoformat()
    names = ["Gooaye 股癌", "曼報", "鈔錢部署｜盧燕俐"]
    docs = [dict(schema_version=3, podcaster=name, episode_id=name, ticker="2330", podcast_launch_time=today) for name in names]

    class Reader:
        def query_collection_group(self, collection, filters, *args):
            selected = next((f[2] for f in filters or [] if f[0] == "podcaster"), None)
            return [d for d in docs if not selected or d["podcaster"] == selected]

        def get_documents_batch(self, *args):
            return []

    service = svc.InsightService.__new__(svc.InsightService)
    service._fs = Reader()
    expected = set(names if visible else names[:1])
    for rows in (await service.get_recent(), await service.get_by_ticker("2330", today, today)):
        assert {row["podcaster"] for row in rows} == expected
    for name in names[1:]:
        assert bool(await service.get_by_podcaster(name, today, today)) is visible
    assert await service.free_insight_counts() == {"2330": 3 if visible else 1}


@pytest.mark.parametrize("environment", ["development", "production", "staging"])
async def test_trending_keeps_dev_fast_path_and_filters_public_aggregation(monkeypatch, environment):
    monkeypatch.setattr(svc.settings, "environment", environment)
    monkeypatch.setattr(svc, "cache_get", AsyncMock(return_value=None))
    monkeypatch.setattr(svc, "cache_set", AsyncMock())
    collections = []

    class Reader:
        def get_all_documents(self, collection):
            collections.append(collection)
            if collection == "trending_tickers":
                return [dict(ticker="DEV", count_all_time=9)]
            return [dict(podcast_name=name, related_tickers=[ticker]) for name, ticker in [("曼報", "HIDDEN"), ("鈔錢部署｜盧燕俐", "HIDDEN"), ("Gooaye 股癌", "PUBLIC")]]

    service = svc.InsightService.__new__(svc.InsightService)
    service._fs = Reader()
    rows = await service.get_trending(days=0, limit=1)
    if environment == "development":
        assert collections == ["trending_tickers"]
        assert [r["ticker"] for r in rows] == ["DEV"]
    else:
        assert collections == ["episodes"]
        assert [r["ticker"] for r in rows] == ["PUBLIC"]
    assert environment in svc.cache_set.await_args.args[0]
