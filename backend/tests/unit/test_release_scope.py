"""
Unit tests for the release-scoping filters on PodcastService:
zh-TW (language allowlist) + the 1-month (released_at_ms recency) window.

These exercise the pure/static helpers so no Firestore/Postgres/GCS clients are
constructed.
"""
from datetime import datetime, timedelta, timezone

import pytest

from src.config import settings
from src.models.podcast import Episode
from src.services.podcast import PodcastService
from src.services.episode_transformer import EpisodeTransformer


def _ep(
    name: str, created_ms: int, released_ms=None, *,
    summary_content: str = "內容摘要", key_insights=None, spotify_release_date=None,
) -> Episode:
    # Episodes carry content by default — the public scope now drops content-empty
    # placeholders, so fixtures must look like real episodes unless testing that guard.
    return Episode(
        id=f"{name}-{created_ms}", podcast_name=name,
        created_time=created_ms, released_at_ms=released_ms,
        summary_content=summary_content, key_insights=key_insights or [],
        spotify_release_date=spotify_release_date,
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
    """With no language/recency scope, content-bearing episodes all pass through."""
    eps = [_ep("Gooaye 股癌", 1), _ep("CNBC's Fast Money", 2)]
    out = PodcastService._scope_episodes(eps, None, None)
    assert {e.podcast_name for e in out} == {"Gooaye 股癌", "CNBC's Fast Money"}


def test_scope_drops_content_empty_placeholders():
    """Re-ingested placeholder episodes (no summary, no key_insights) are hidden
    even with a recent released_at_ms — they would render as empty cards."""
    now = datetime.now()
    real = _ep("Gooaye 股癌", _ms(now), _ms(now - timedelta(days=1)))
    empty = _ep("Gooaye 股癌", _ms(now), _ms(now - timedelta(days=1)), summary_content="")
    out = PodcastService._scope_episodes([real, empty], None, None)
    assert out == [real]


def test_episode_release_ms_prefers_spotify_date():
    """spotify_release_date is the trusted publish signal and wins over a
    (possibly ingestion-time) released_at_ms."""
    ep = _ep(
        "財報狗", created_ms=2_000, released_ms=9_999_999_999_999,
        spotify_release_date="2026-03-07",
    )
    expected = int(datetime(2026, 3, 7, tzinfo=timezone.utc).timestamp() * 1000)
    assert PodcastService._episode_release_ms(ep) == expected


def test_spotify_iso_timestamp_remains_authoritative():
    ep = _ep(
        "財報狗", created_ms=1,
        released_ms=_ms(datetime(2026, 3, 7, 23, 0, tzinfo=timezone.utc)),
        spotify_release_date="2026-03-07T12:30:00Z",
    )
    expected = _ms(datetime(2026, 3, 7, 12, 30, tzinfo=timezone.utc))
    assert PodcastService._episode_release_ms(ep) == expected


def test_matching_spotify_day_uses_precise_time_and_raw_dict_matches():
    released = datetime(2026, 7, 17, 8, 2, 6, tzinfo=timezone.utc)
    released_ms = _ms(released)
    ep = _ep(
        "曼報", created_ms=1, released_ms=released_ms,
        spotify_release_date="2026-07-17",
    )
    service = PodcastService.__new__(PodcastService)
    service.transformer = EpisodeTransformer()
    raw = {"spotify_release_date": "2026-07-17", "released_at_ms": released_ms}

    assert PodcastService._episode_release_ms(ep) == released_ms
    assert service._dict_release_ms(raw) == released_ms


def test_release_scope_accepts_exact_90_day_boundary_and_rejects_older():
    now = datetime(2026, 10, 15, 8, 2, 6, tzinfo=timezone.utc)
    boundary = now - timedelta(days=90)
    boundary_ms = _ms(boundary)
    boundary_ep = _ep(
        "曼報", created_ms=_ms(now), released_ms=boundary_ms,
        spotify_release_date=boundary.date().isoformat(),
    )
    old_ep = _ep(
        "曼報", created_ms=_ms(now), released_ms=boundary_ms - 1,
        spotify_release_date=boundary.date().isoformat(),
    )

    assert PodcastService._scope_episodes([boundary_ep], None, boundary_ms) == [boundary_ep]
    assert PodcastService._scope_episodes([old_ep], None, boundary_ms) == []


def test_spotify_date_wins_when_precise_timestamp_disagrees():
    expected = PodcastService._spotify_release_ms("2026-07-17")
    service = PodcastService.__new__(PodcastService)
    service.transformer = EpisodeTransformer()
    ep = _ep(
        "曼報", created_ms=1,
        released_ms=_ms(datetime(2026, 7, 16, 23, 59, tzinfo=timezone.utc)),
        spotify_release_date="2026-07-17",
    )
    raw = {
        "spotify_release_date": "2026-07-17",
        "released_at_ms": _ms(datetime(2026, 7, 16, 23, 59, tzinfo=timezone.utc)),
    }

    assert PodcastService._episode_release_ms(ep) == expected
    assert service._dict_release_ms(raw) == expected


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
    assert PodcastService._scope_tag().startswith("zh-TW:0:visibility-v1:")
    monkeypatch.setattr(settings, "release_podcast_languages", [])
    monkeypatch.setattr(settings, "release_episode_max_age_days", 30)
    assert PodcastService._scope_tag().startswith("all:30:visibility-v1:")


async def test_scope_endpoint_reports_the_episode_window(monkeypatch):
    """Counts are window-scoped; the UI labels them 「近 N 天」 from this."""
    from src.routers import podcast as router

    monkeypatch.setattr(settings, "release_episode_max_age_days", 60)
    assert await router.get_release_scope() == {"episode_window_days": 60}
    monkeypatch.setattr(settings, "release_episode_max_age_days", 0)
    assert await router.get_release_scope() == {"episode_window_days": 0}


@pytest.mark.parametrize("environment,visible", [("development", True), ("production", False), ("staging", False)])
@pytest.mark.parametrize("languages", [[], ["zh-TW"]])
async def test_development_only_shows_share_catalog_and_direct_scope(monkeypatch, environment, visible, languages):
    from unittest.mock import AsyncMock
    from src.services import podcast as module

    names = {"Gooaye 股癌", "曼報", "鈔錢部署｜盧燕俐"}
    monkeypatch.setattr(settings, "environment", environment)
    monkeypatch.setattr(settings, "release_podcast_languages", languages)
    monkeypatch.setattr(settings, "release_episode_max_age_days", 0)
    monkeypatch.setattr(module, "cache_get", AsyncMock(return_value=None))
    monkeypatch.setattr(module, "cache_set", AsyncMock())
    monkeypatch.setattr(PodcastService, "_query_allowed_podcast_names", staticmethod(lambda langs: list(names)))
    service = PodcastService.__new__(PodcastService)
    allowed = await service._allowed_podcast_names()
    for name in ("曼報", "鈔錢部署｜盧燕俐"):
        assert (name in allowed) is visible
        assert (await service._episode_in_scope(_ep(name, 1))) is visible
    scoped = PodcastService._scope_episodes([_ep(name, 1) for name in names], allowed, None)
    assert {ep.podcast_name for ep in scoped} == (names if visible else {"Gooaye 股癌"})
    assert environment in module.cache_get.await_args.args[0]


def test_visibility_cache_separates_environments(monkeypatch):
    tags = []
    for environment in ("development", "production", "staging"):
        monkeypatch.setattr(settings, "environment", environment)
        tags.append(PodcastService._scope_tag())
    assert len(set(tags)) == 3


@pytest.mark.parametrize("languages", [[], ["zh-TW"]])
def test_registry_query_applies_visibility_without_language_filter(monkeypatch, languages):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from src.database import postgres
    from src.services.content_source_service import ContentSourceService

    monkeypatch.setattr(settings, "environment", "production")
    db = Mock()
    monkeypatch.setattr(postgres, "SessionLocal", lambda: db)
    rows = [SimpleNamespace(name=name, language=lang) for name, lang in [("曼報", "zh-TW"), ("鈔錢部署｜盧燕俐", "zh-TW"), ("Gooaye 股癌", "zh-TW"), ("English", "en")]]
    source_query = Mock(return_value=(rows, len(rows)))
    monkeypatch.setattr(ContentSourceService, "list_sources", source_query)
    expected = ["Gooaye 股癌"] if languages else ["Gooaye 股癌", "English"]
    assert PodcastService._query_allowed_podcast_names(languages) == expected
    source_query.assert_called_once_with(source_type="podcast", active=True, limit=1000)
    db.close.assert_called_once()
