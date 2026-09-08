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


def test_placeholder_detection_does_not_flag_normally_summarised_episodes(monkeypatch):
    """The backfill work queue must contain only episodes that actually need content.

    ``summary_content`` is written only by the regen tool; the normal pipeline keeps
    the markdown as an artifact and leaves the inline field empty. Testing the inline
    field alone made every normally-processed episode look like an empty placeholder.
    """
    from src.podcast.regen import orchestrator as ro

    rows = [
        # normal pipeline output: no inline summary, artifact URL present
        {"episode_id": "done", "transcript_url": "u", "summary_url": "s"},
        # --skip-summarize backfill: transcript only, nothing generated yet
        {"episode_id": "todo", "transcript_url": "u"},
        # a real placeholder that was written inline
        {"episode_id": "bad", "transcript_url": "u", "summary_url": "s",
         "summary_content": "Placeholder summary will be generated"},
    ]

    class FakeFS:
        def query_collection(self, *a, **k):
            return rows

    monkeypatch.setattr(ro, "_firestore", lambda: FakeFS())
    monkeypatch.setattr(ro, "is_placeholder_summary", lambda text: "Placeholder summary" in text)

    ids = [c["episode_id"] for c in ro.find_candidates(only_placeholder=True)["candidates"]]
    assert ids == ["todo", "bad"], ids


def test_skip_summarize_persists_the_transcript_and_runs_no_llm_steps(monkeypatch):
    """--skip-summarize must still write the episode row (regen needs one to exist),
    and must not run any step that derives from a summary that was never generated.
    """
    from pathlib import Path

    from src.pipeline import processor as p
    from src.pipeline.config import PipelineConfig

    called = []

    def _record(name):
        def _fn(config, services, episode_data):
            called.append(name)

        return _fn

    for step in (
        "download_episode", "transcribe_episode", "generate_summary", "upload_to_gcs",
        "render_social_cards", "persist_episode", "ingest_into_wiki",
        "export_ticker_insights", "trigger_syndicate", "validate_episode",
    ):
        monkeypatch.setattr(p, step, _record(step))

    config = PipelineConfig(
        config_file=Path("c.json"), podcast_name="Gooaye 股癌", podcast_link="l",
        skip_summarize=True, store_audio=False, use_file_mode=True,
    )
    proc = p.EpisodeProcessor.__new__(p.EpisodeProcessor)
    proc.config = config
    proc.services = object()
    monkeypatch.setattr(p.EpisodeProcessor, "_load_existing_data", lambda self, ed: None)
    monkeypatch.setattr(p.EpisodeProcessor, "_should_skip_episode", lambda self, ed: False)

    assert proc.process_episode({"title": "EP1 |( *・ω・)╰—╯✄", "episodeNumber": 1}) is True

    assert called == ["download_episode", "transcribe_episode", "upload_to_gcs", "persist_episode"]
    assert "generate_summary" not in called
    # Nothing below summarize can run: it is all derived from content that does not
    # exist yet, and syndicating/notifying on an empty episode would be user-visible.
    for derived in ("render_social_cards", "export_ticker_insights", "trigger_syndicate"):
        assert derived not in called
