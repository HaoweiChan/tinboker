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
    """A normally-processed episode must not read as an empty placeholder.

    ``summary_content`` is written only by the regen tool; the normal pipeline keeps the
    markdown as an artifact and leaves the inline field empty, so testing that field
    alone reported 4,262 of 4,551 episodes as needing a rewrite.
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

    # The listing path (only_placeholder=False) still classifies each row, and that
    # classification is what a session reads to decide whether an episode needs work.
    out = ro.find_candidates(only_placeholder=False)["candidates"]
    flags = {c["episode_id"]: (c["has_summary"], c["is_placeholder"]) for c in out}
    assert flags == {"done": (True, False), "todo": (False, True), "bad": (True, True)}


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


def test_the_regen_queue_asks_sql_for_candidates_not_a_python_filter(monkeypatch):
    """Backfilled episodes carry their true OLD release date, so they sort to the bottom
    of the table. Filtering a newest-first window in Python can never reach them — the
    queue reported 0 while ten freshly-transcribed episodes sat in the table.
    """
    from src.podcast.regen import orchestrator as ro
    from src.service import postgres_mirror_reader

    seen = {}

    def fake_query(*, podcast_name=None, limit=20):
        seen["podcast_name"] = podcast_name
        seen["limit"] = limit
        return [{
            "episode_id": "Gooaye_old", "podcast_name": "Gooaye 股癌",
            "episode_title": "EP123 | 蘋果怎麼吃才營養",
            "transcript_url": "https://media/t.json", "released_at_ms": 1616025600000,
        }]

    monkeypatch.setattr(postgres_mirror_reader, "query_regen_candidates", fake_query)
    monkeypatch.setattr(ro, "_firestore", lambda: None)
    monkeypatch.setattr(ro, "_episode_sentences", lambda d: [])

    out = ro.find_candidates(podcast_name="Gooaye 股癌", limit=5, only_placeholder=True)

    assert seen == {"podcast_name": "Gooaye 股癌", "limit": 5}
    assert [c["episode_id"] for c in out["candidates"]] == ["Gooaye_old"]
    assert out["candidates"][0]["is_placeholder"] is True


def test_writer_submit_warns_when_output_drifts_from_the_corpus():
    """An agent writing to these prompts overshoots the pipeline's own model on every
    axis — 股癌 EP127 came out at 6,593 chars / 40 ticker links / 24 tickers against the
    pipeline's 4,090 / 15 / 11 from the same transcript. Episodes sit next to each other
    on the site, so the drift has to surface before commit.
    """
    from src.podcast.regen.orchestrator import _corpus_drift_warnings

    ok = {
        "markdown_report": "x" * 4300 + " [台積電](#ticker:2330)" * 9,
        "related_tickers": ["2330"] * 7,
        "tags": ["a"] * 8,
    }
    assert _corpus_drift_warnings(ok) == []

    drifted = {
        "markdown_report": "x" * 6593 + " [x](#ticker:2330)" * 40,
        "related_tickers": ["t%d" % i for i in range(24)],
        "tags": ["g%d" % i for i in range(18)],
    }
    warnings = " ".join(_corpus_drift_warnings(drifted))
    assert "characters" in warnings and "#ticker: links" in warnings
    assert "related_tickers" in warnings and "tags" in warnings

    thin = {"markdown_report": "x" * 900, "related_tickers": [], "tags": []}
    assert "too thin" in " ".join(_corpus_drift_warnings(thin))
