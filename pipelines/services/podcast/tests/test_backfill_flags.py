"""Backfill-mode guards: the floor filter and the mode-dependent "already done" test.

The second one is the one that bites: with --skip-summarize the episode never gets
a summary_url, so the default completeness test would call it unprocessed forever
and re-download + re-transcribe it on every run.
"""

from src.pipeline.utils import required_artifact_urls
from src.podcast.orchestrator import _apply_backfill_floor

FLOOR = "2020-02-27"  # Gooaye 股癌 EP1


def _ep(date):
    return {"datePublished": date, "title": str(date)}


def test_floor_keeps_the_boundary_and_drops_older():
    episodes = [
        _ep("2026-09-05T07:30:00Z"),
        _ep("2020-02-27T19:51:55Z"),   # 股癌 EP1 itself — must survive
        _ep("2020-02-26T23:59:59Z"),
        _ep("2019-11-10T15:33:00Z"),
    ]
    kept = _apply_backfill_floor(episodes, FLOOR)
    assert [e["title"] for e in kept] == [
        "2026-09-05T07:30:00Z",
        "2020-02-27T19:51:55Z",
    ]


def test_floor_keeps_undated_episodes():
    assert len(_apply_backfill_floor([_ep(None), _ep("")], FLOOR)) == 2


def test_completeness_test_follows_the_mode():
    assert required_artifact_urls() == (
        "mp3_url", "transcript_url", "summary_url", "summary_image_url",
    )
    # A --skip-summarize --no-store-audio backfill produces a transcript and
    # nothing else; requiring anything more would re-process it forever.
    assert required_artifact_urls(skip_summarize=True, store_audio=False) == (
        "transcript_url",
    )
    assert "mp3_url" not in required_artifact_urls(store_audio=False)
    assert "summary_url" not in required_artifact_urls(skip_summarize=True)


def test_backfilled_episode_counts_as_done():
    stored = {"transcript_url": "https://media/x.json", "mp3_url": None, "summary_url": None}
    required = required_artifact_urls(skip_summarize=True, store_audio=False)
    assert all(stored.get(f) for f in required)
    assert not all(stored.get(f) for f in required_artifact_urls())
