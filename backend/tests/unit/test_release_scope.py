"""
Unit tests for the release-scoping filters on PodcastService:
zh-TW (language allowlist) + the 1-month (released_at_ms recency) window.

These exercise the pure/static helpers so no Firestore/Postgres/GCS clients are
constructed.
"""
from datetime import datetime, timedelta

import pytest

from src.config import settings
from src.models.podcast import Episode
from src.services.podcast import PodcastService
from src.services.episode_transformer import EpisodeTransformer


def _ep(name: str, created_ms: int, released_ms=None) -> Episode:
    return Episode(
        id=f"{name}-{created_ms}", podcast_name=name,
        created_time=created_ms, released_at_ms=released_ms,
    )


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


# ── released_at_ms normalization ─────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    (None, None),
    ("", None),
    ("   ", None),
    (True, None),                       # bool is not a timestamp
    (1748000000000, 1748000000000),     # int ms passthrough
    (1748000000000.0, 1748000000000),   # float ms -> int
    ("1748000000000", 1748000000000),   # digit string -> int
    ("not-a-date", None),               # unparseable -> None (never now())
])
def test_normalize_released_at_ms_scalars(raw, expected):
    assert EpisodeTransformer._normalize_released_at_ms(raw) == expected


def test_normalize_released_at_ms_datetime_and_iso():
    dt = datetime(2026, 1, 15, 12, 0, 0)
    assert EpisodeTransformer._normalize_released_at_ms(dt) == _ms(dt)
    # ISO string with Z suffix parses to the same instant
    iso = "2026-01-15T12:00:00+00:00"
    parsed = EpisodeTransformer._normalize_released_at_ms(iso)
    assert parsed == int(datetime.fromisoformat(iso).timestamp() * 1000)


# ── recency cutoff (config-gated) ────────────────────────────────────

def test_recency_cutoff_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "release_episode_max_age_days", 0)
    assert PodcastService._recency_cutoff_ms() is None


def test_recency_cutoff_enabled(monkeypatch):
    monkeypatch.setattr(settings, "release_episode_max_age_days", 30)
    cutoff = PodcastService._recency_cutoff_ms()
    expected = int((datetime.now().timestamp() - 30 * 86400) * 1000)
    assert cutoff is not None and abs(cutoff - expected) < 5000  # within 5s


# ── release-ms selection: published time wins over ingestion time ────

def test_episode_release_ms_prefers_released_at_ms():
    ep = _ep("Gooaye 股癌", created_ms=2_000, released_ms=1_000)
    assert PodcastService._episode_release_ms(ep) == 1_000


def test_episode_release_ms_falls_back_to_created_time():
    ep = _ep("Gooaye 股癌", created_ms=2_000, released_ms=None)
    assert PodcastService._episode_release_ms(ep) == 2_000


# ── _scope_episodes: language allowlist + recency ────────────────────

def test_scope_passthrough_when_unscoped():
    eps = [_ep("Gooaye 股癌", 1), _ep("CNBC's Fast Money", 2)]
    assert PodcastService._scope_episodes(eps, None, None) is eps


def test_scope_language_allowlist_drops_out_of_scope_shows():
    allowed = frozenset({"Gooaye 股癌", "財報狗"})
    eps = [
        _ep("Gooaye 股癌", 10),
        _ep("CNBC's Fast Money", 11),   # English -> dropped
        _ep("財報狗", 12),
    ]
    out = PodcastService._scope_episodes(eps, allowed, None)
    assert {e.podcast_name for e in out} == {"Gooaye 股癌", "財報狗"}


def test_scope_recency_uses_publish_time_not_ingestion_time():
    """An episode ingested today (created_time=now) but PUBLISHED 4 months ago
    must be hidden by the 30-day window — this is the whole point of released_at_ms."""
    now = datetime.now()
    cutoff = _ms(now - timedelta(days=30))
    backfilled_old = _ep("財報狗", created_ms=_ms(now), released_ms=_ms(now - timedelta(days=120)))
    genuinely_recent = _ep("財報狗", created_ms=_ms(now), released_ms=_ms(now - timedelta(days=3)))
    out = PodcastService._scope_episodes([backfilled_old, genuinely_recent], None, cutoff)
    assert out == [genuinely_recent]


def test_scope_combines_language_and_recency():
    now = datetime.now()
    cutoff = _ms(now - timedelta(days=30))
    allowed = frozenset({"Gooaye 股癌"})
    eps = [
        _ep("Gooaye 股癌", _ms(now), _ms(now - timedelta(days=2))),    # keep
        _ep("Gooaye 股癌", _ms(now), _ms(now - timedelta(days=90))),   # too old
        _ep("CNBC's Fast Money", _ms(now), _ms(now - timedelta(days=1))),  # wrong lang
    ]
    out = PodcastService._scope_episodes(eps, allowed, cutoff)
    assert len(out) == 1 and out[0].podcast_name == "Gooaye 股癌"


# ── scope tag (cache-key isolation) ──────────────────────────────────

def test_scope_tag_reflects_config(monkeypatch):
    monkeypatch.setattr(settings, "release_podcast_languages", ["zh-TW"])
    monkeypatch.setattr(settings, "release_episode_max_age_days", 0)
    assert PodcastService._scope_tag() == "zh-TW:0"
    monkeypatch.setattr(settings, "release_podcast_languages", [])
    monkeypatch.setattr(settings, "release_episode_max_age_days", 30)
    assert PodcastService._scope_tag() == "all:30"
