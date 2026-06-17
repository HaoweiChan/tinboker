"""Unit tests for /picks release-window scoping in InsightService.

The blended feed and channel-history reads must honour the launch release
window (``release_episode_max_age_days``) so unreleased back-catalogue picks
stay hidden — and the cache key must isolate per window.
"""

from datetime import date, timedelta

from src.services import insight_service as svc


def test_recency_floor_disabled_by_default(monkeypatch):
    monkeypatch.setattr(svc.settings, "release_episode_max_age_days", 0)
    assert svc._release_recency_floor() is None


def test_recency_floor_enabled(monkeypatch):
    monkeypatch.setattr(svc.settings, "release_episode_max_age_days", 30)
    assert svc._release_recency_floor() == date.today() - timedelta(days=30)


def test_scope_tag_tracks_window(monkeypatch):
    monkeypatch.setattr(svc.settings, "release_episode_max_age_days", 0)
    assert svc._scope_tag() == "r0"
    monkeypatch.setattr(svc.settings, "release_episode_max_age_days", 30)
    assert svc._scope_tag() == "r30"


def test_floor_keeps_recent_drops_old(monkeypatch):
    monkeypatch.setattr(svc.settings, "release_episode_max_age_days", 30)
    floor = svc._release_recency_floor()
    today = date.today()
    recent = (today - timedelta(days=5)).isoformat() + "T00:00:00Z"
    old = (today - timedelta(days=120)).isoformat() + "T00:00:00Z"
    assert svc._in_range(recent, floor, today) is True
    assert svc._in_range(old, floor, today) is False
