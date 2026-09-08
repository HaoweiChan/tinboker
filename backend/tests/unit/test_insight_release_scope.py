"""Unit tests for /picks window scoping in InsightService.

Picks have their own window (``release_picks_max_age_days``, default off) so
7/30/90-day returns can settle; each row reports ``episode_public`` from the
episode window (``release_episode_max_age_days``) — and the cache key must
isolate per window pair.
"""

import asyncio
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
    assert svc._scope_tag() == "p0e0"
    monkeypatch.setattr(svc.settings, "release_episode_max_age_days", 60)
    assert svc._scope_tag() == "p0e60"


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
