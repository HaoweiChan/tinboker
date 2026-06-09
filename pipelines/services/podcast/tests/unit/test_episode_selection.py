"""Unit tests for podcast episode recency selection (orchestrator)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.podcast.orchestrator import _parse_episode_date, _select_recent_episodes


def _ep(name: str, *, days_ago: int | None = None) -> dict:
    d: dict = {"title": name}
    if days_ago is not None:
        dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
        d["datePublished"] = dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return d


def test_parse_episode_date_handles_z_suffix():
    dt = _parse_episode_date("2026-06-03T07:34:50.000Z")
    assert dt is not None and dt.tzinfo is not None
    assert (dt.year, dt.month, dt.day) == (2026, 6, 3)


def test_parse_episode_date_returns_none_for_bad_input():
    assert _parse_episode_date(None) is None
    assert _parse_episode_date("not-a-date") is None


def test_select_filters_by_lookback_window():
    eps = [_ep("new", days_ago=5), _ep("old", days_ago=60)]
    out = _select_recent_episodes(eps, lookback_days=30, max_episodes=None, legacy_limit=None)
    assert [e["title"] for e in out] == ["new"]


def test_select_caps_at_max_episodes():
    eps = [_ep(str(i), days_ago=1) for i in range(10)]
    out = _select_recent_episodes(eps, lookback_days=30, max_episodes=3, legacy_limit=None)
    assert len(out) == 3


def test_select_falls_back_to_count_when_no_dates():
    eps = [{"title": str(i)} for i in range(10)]  # no datePublished
    out = _select_recent_episodes(eps, lookback_days=30, max_episodes=None, legacy_limit=4)
    assert len(out) == 4  # window can't apply → count-cap fallback


def test_select_legacy_count_when_no_window():
    eps = [{"title": str(i)} for i in range(10)]
    out = _select_recent_episodes(eps, lookback_days=None, max_episodes=None, legacy_limit=2)
    assert len(out) == 2
