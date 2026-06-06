"""Unit tests for feed-driven ``released_at_ms`` (handoff spec §2.3 #1).

Covers:
  * the feed ``datePublished`` drives ``released_at_ms`` (beats created_time),
  * a Spotify-unmatched episode still gets the correct ``released_at_ms`` from
    the feed,
  * ``created_time`` is never mutated when an existing value is present,
  * the ``_compute_released_at_ms`` preference order.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.models.podcast_models import PodcastEpisode
from src.pipeline.episode_data import EpisodeData
from src.pipeline.utils import _date_published_to_ms, create_episode_object

# A fixed feed publish date (the episode aired in March) and a much-later
# ingestion/backfill time (late May) — the mismatch the spec is about.
_FEED_ISO = "2026-03-15T07:34:50.000Z"
_FEED_MS = int(
    datetime(2026, 3, 15, 7, 34, 50, tzinfo=timezone.utc).timestamp() * 1000
)
_BACKFILL_TIME = datetime(2026, 5, 24, 3, 0, 0, tzinfo=timezone.utc)
_BACKFILL_MS = int(_BACKFILL_TIME.timestamp() * 1000)


def _episode_data(*, date_published: str | None, created_time: datetime | None) -> EpisodeData:
    api_data: dict = {"title": "三月那集", "episodeNumber": 42}
    if date_published is not None:
        api_data["datePublished"] = date_published
    return EpisodeData(
        api_data=api_data,
        podcast_name="財經一路發",
        language="zh",
        created_time=created_time,
    )


# --- _date_published_to_ms -------------------------------------------------


def test_date_published_to_ms_parses_feed_date():
    assert _date_published_to_ms({"datePublished": _FEED_ISO}) == _FEED_MS


def test_date_published_to_ms_handles_missing_or_bad():
    assert _date_published_to_ms({}) is None
    assert _date_published_to_ms({"datePublished": "not-a-date"}) is None
    assert _date_published_to_ms(None) is None


# --- create_episode_object → released_at_ms --------------------------------


def test_feed_date_drives_released_at_ms_over_created_time():
    """released_at_ms comes from the feed publish date, NOT the backfill-run created_time."""
    ed = _episode_data(date_published=_FEED_ISO, created_time=_BACKFILL_TIME)
    ep = create_episode_object(ed, gcs_urls={}, spotify_metadata=None, summary_result=None)

    assert ep.feed_date_published_ms == _FEED_MS
    assert ep._compute_released_at_ms() == _FEED_MS
    assert ep.to_firestore_dict()["released_at_ms"] == _FEED_MS
    # Sanity: the feed-derived value is the March date, not the May ingestion date.
    assert ep._compute_released_at_ms() != _BACKFILL_MS


def test_spotify_unmatched_episode_still_gets_feed_released_at_ms():
    """No Spotify metadata at all → released_at_ms still resolved from the feed."""
    ed = _episode_data(date_published=_FEED_ISO, created_time=None)
    ep = create_episode_object(ed, gcs_urls={}, spotify_metadata=None, summary_result=None)

    assert ep.spotify_release_date is None
    assert ep._compute_released_at_ms() == _FEED_MS
    assert ep.to_firestore_dict()["released_at_ms"] == _FEED_MS


def test_existing_created_time_is_never_mutated():
    """An existing created_time must pass through untouched (mutating it re-fires
    new_episode notifications — handoff spec §6.3)."""
    ed = _episode_data(date_published=_FEED_ISO, created_time=_BACKFILL_TIME)
    ep = create_episode_object(ed, gcs_urls={}, spotify_metadata=None, summary_result=None)

    assert ep.created_time == _BACKFILL_TIME
    # released_at_ms still reflects the (earlier) feed date, not created_time.
    assert ep._compute_released_at_ms() == _FEED_MS


def test_existing_created_time_kept_even_with_spotify_match():
    """A Spotify match must not overwrite a stored created_time either."""
    ed = _episode_data(date_published=_FEED_ISO, created_time=_BACKFILL_TIME)
    spotify_release = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ep = create_episode_object(
        ed,
        gcs_urls={},
        spotify_metadata={"release_datetime": spotify_release},
        summary_result=None,
    )
    assert ep.created_time == _BACKFILL_TIME


def test_created_time_falls_back_to_feed_when_absent_and_no_spotify():
    """No stored created_time AND no Spotify match → created_time uses the feed date
    (so it is at least the true publish time, not now())."""
    ed = _episode_data(date_published=_FEED_ISO, created_time=None)
    ep = create_episode_object(ed, gcs_urls={}, spotify_metadata=None, summary_result=None)

    assert isinstance(ep.created_time, datetime)
    assert int(ep.created_time.timestamp() * 1000) == _FEED_MS


def test_created_time_prefers_spotify_over_feed_when_absent():
    """When created_time is absent, a Spotify release datetime wins over the feed
    date for created_time (released_at_ms still prefers the feed date)."""
    ed = _episode_data(date_published=_FEED_ISO, created_time=None)
    spotify_release = datetime(2026, 2, 2, tzinfo=timezone.utc)
    ep = create_episode_object(
        ed,
        gcs_urls={},
        spotify_metadata={"release_datetime": spotify_release},
        summary_result=None,
    )
    assert ep.created_time == spotify_release
    # released_at_ms still comes from the feed (the most reliable signal).
    assert ep._compute_released_at_ms() == _FEED_MS


# --- _compute_released_at_ms preference order ------------------------------


def _bare_episode(**kwargs) -> PodcastEpisode:
    base = dict(mp3_url="", transcript_url="", summary_url="", summary_image_url="")
    base.update(kwargs)
    return PodcastEpisode(**base)


def test_explicit_released_at_ms_wins():
    ep = _bare_episode(
        released_at_ms=111,
        feed_date_published_ms=222,
        spotify_release_date="2026-01-01",
        created_time=_BACKFILL_TIME,
    )
    assert ep._compute_released_at_ms() == 111


def test_feed_beats_spotify_and_created_time():
    ep = _bare_episode(
        feed_date_published_ms=_FEED_MS,
        spotify_release_date="2026-01-01",
        created_time=_BACKFILL_TIME,
    )
    assert ep._compute_released_at_ms() == _FEED_MS


def test_spotify_used_when_no_feed_date():
    ep = _bare_episode(spotify_release_date="2026-01-01", created_time=_BACKFILL_TIME)
    expected = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
    assert ep._compute_released_at_ms() == expected


def test_created_time_is_last_resort():
    ep = _bare_episode(created_time=_BACKFILL_TIME)
    assert ep._compute_released_at_ms() == _BACKFILL_MS
