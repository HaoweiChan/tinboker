"""Unit tests for the self-healing ``released_at_ms`` reconcile pass.

Verifies that the inline reconcile re-derives ``released_at_ms`` from the feed
``datePublished``, fixes stale (ingestion-time) values, leaves correct docs
untouched, and never mutates anything but ``released_at_ms``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from src.pipeline.reconcile import reconcile_show_released_at_ms


def _ms(iso: str) -> int:
    text = iso[:-1] + "+00:00" if iso.endswith("Z") else iso
    return int(datetime.fromisoformat(text).astimezone(timezone.utc).timestamp() * 1000)


# Feed: EP345 aired 2023-05-03; EP670 aired 2026-06-13. Whole-second feed dates.
_FEED = [
    {"title": "EP670 | 🫡", "episodeNumber": 670, "datePublished": "2026-06-13T07:07:21.000Z"},
    {"title": "EP345 | 🪴", "episodeNumber": 345, "datePublished": "2023-05-03T08:03:09.000Z"},
    {"title": "無編號特輯", "episodeNumber": None, "datePublished": "2024-01-02T00:00:00.000Z"},
]


class _FakeFB:
    """Minimal FirebaseService stand-in recording released_at_ms writes."""

    def __init__(self, episodes):
        self._episodes = episodes
        self.writes: dict[str, dict] = {}

    def get_podcast_episodes(self, podcast_name):
        return self._episodes

    def update_episode_fields(self, episode_id, fields):
        self.writes[episode_id] = fields


def test_fixes_stale_ingestion_time_value():
    # EP345 stored with an ingestion-time released_at_ms (2026-06-07, sub-second).
    bad_ms = _ms("2026-06-07T03:14:22.828Z")
    fb = _FakeFB([
        {"id": "ep345", "episode_title": "EP345 | 🪴", "episode_number": 345,
         "released_at_ms": bad_ms},
    ])
    res = reconcile_show_released_at_ms(fb, "Gooaye 股癌", _FEED)

    assert res == {"checked": 1, "fixed": 1, "failed": 0}
    assert fb.writes == {"ep345": {"released_at_ms": _ms("2023-05-03T08:03:09.000Z")}}


def test_leaves_correct_value_untouched():
    fb = _FakeFB([
        {"id": "ep670", "episode_title": "EP670 | 🫡", "episode_number": 670,
         "released_at_ms": _ms("2026-06-13T07:07:21.000Z")},
    ])
    res = reconcile_show_released_at_ms(fb, "Gooaye 股癌", _FEED)

    assert res == {"checked": 1, "fixed": 0, "failed": 0}
    assert fb.writes == {}


def test_dry_run_counts_but_does_not_write():
    fb = _FakeFB([
        {"id": "ep345", "episode_title": "EP345 | 🪴", "episode_number": 345,
         "released_at_ms": 123},
    ])
    res = reconcile_show_released_at_ms(fb, "Gooaye 股癌", _FEED, apply=False)

    assert res == {"checked": 1, "fixed": 1, "failed": 0}
    assert fb.writes == {}


def test_matches_by_title_when_number_missing():
    fb = _FakeFB([
        {"id": "special", "episode_title": "無編號特輯", "episode_number": None,
         "released_at_ms": 0},
    ])
    res = reconcile_show_released_at_ms(fb, "Gooaye 股癌", _FEED)

    assert res["fixed"] == 1
    assert fb.writes["special"] == {"released_at_ms": _ms("2024-01-02T00:00:00.000Z")}


def test_doc_absent_from_feed_is_skipped():
    fb = _FakeFB([
        {"id": "ghost", "episode_title": "不存在於feed", "episode_number": 9,
         "released_at_ms": 1},
    ])
    res = reconcile_show_released_at_ms(fb, "Gooaye 股癌", _FEED)

    assert res == {"checked": 0, "fixed": 0, "failed": 0}
    assert fb.writes == {}


def test_empty_feed_is_a_noop():
    fb = _FakeFB([
        {"id": "ep345", "episode_title": "EP345 | 🪴", "episode_number": 345,
         "released_at_ms": 1},
    ])
    res = reconcile_show_released_at_ms(fb, "Gooaye 股癌", [])

    assert res == {"checked": 0, "fixed": 0, "failed": 0}
    assert fb.writes == {}
