from types import SimpleNamespace

from src.pipeline.episode_data import EpisodeData
from src.pipeline.processor import EpisodeProcessor
from src.pipeline.utils import is_regen_without_audio_complete
from src.podcast.orchestrator import _filter_unprocessed_episodes
from src.podcast.regen import orchestrator as regen_orchestrator
from src.podcast.regen.orchestrator import RegenError
from src.watcher import _is_fully_processed

POLICY = {
    "version": 1,
    "mode": "regen_without_audio_or_image",
    "required_urls": ["transcript_url", "summary_url"],
    "intentionally_omitted_urls": ["mp3_url", "summary_image_url"],
}
REQUIRED_ROLES = ("extractor", "writer", "key_insights", "ticker_extractor", "marp_writer")


def provenance(**overrides):
    role = {"source": "generated", "provider": "official", "model": "gpt-6-luna", "output_sha256": "a" * 64}
    role.update(overrides)
    return {"roles": {name: dict(role) for name in REQUIRED_ROLES}}


def episode(**overrides):
    return {
        "id": "ep-1",
        "transcript_url": "gs://media/transcript.json",
        "summary_url": "gs://media/summary.md",
        "summary_content": "A real regenerated summary.",
        "generation_metadata": provenance(),
        "mp3_url": None,
        "summary_image_url": None,
        "artifact_completion_policy": POLICY,
        **overrides,
    }


def test_explicit_policy_requires_transcript_and_summary_content():
    assert is_regen_without_audio_complete(episode())
    assert not is_regen_without_audio_complete(episode(summary_content="  "))
    assert not is_regen_without_audio_complete(episode(summary_content="This is a placeholder summary."))
    assert not is_regen_without_audio_complete(episode(transcript_url=None))
    assert not is_regen_without_audio_complete(episode(summary_url=None))
    assert not is_regen_without_audio_complete(episode(generation_metadata={"roles": {"writer": {}}}))
    bad_provenance = provenance()
    bad_provenance["roles"]["writer"]["source"] = "unknown"
    assert not is_regen_without_audio_complete(episode(generation_metadata=bad_provenance))
    for field, value in (("provider", "unknown"), ("model", " "), ("output_sha256", "not-a-hash")):
        bad_provenance = provenance()
        bad_provenance["roles"]["writer"][field] = value
        assert not is_regen_without_audio_complete(episode(generation_metadata=bad_provenance))
    assert not is_regen_without_audio_complete(episode(generation_metadata={"roles": []}))
    assert not is_regen_without_audio_complete(episode(artifact_completion_policy=None))


def test_watcher_accepts_only_explicit_complete_no_audio_regen():
    assert _is_fully_processed(episode())
    assert not _is_fully_processed(episode(artifact_completion_policy=None))
    assert not _is_fully_processed(episode(summary_content=""))


def test_feed_filter_skips_explicit_regen_but_keeps_ordinary_missing_audio_incomplete():
    saved = episode()

    class Firebase:
        def get_episode_by_fields(self, **kwargs):
            return saved

        def get_episode_by_title_and_number(self, **kwargs):
            return None

    class Services:
        firebase_service = Firebase()

    feed = [{"title": "Episode", "episodeNumber": 1}]
    assert _filter_unprocessed_episodes(feed, "Show", 1, Services()) == []
    saved["artifact_completion_policy"] = None
    assert _filter_unprocessed_episodes(feed, "Show", 1, Services()) == feed



def test_processor_skip_gate_honors_policy_but_not_plain_missing_audio():
    processor = EpisodeProcessor.__new__(EpisodeProcessor)
    processor.config = SimpleNamespace(
        rerun_from=None, reuse_existing_transcript=False,
        skip_summarize=False, store_audio=True,
    )
    data = EpisodeData(
        api_data={"title": "Episode", "artifact_completion_policy": POLICY,
                  "summary_content": "A real regenerated summary.",
                  "generation_metadata": provenance()},
        podcast_name="Show", language="zh", episode_id="ep-1",
        gcs_urls={"transcript_url": "t", "summary_url": "s"},
    )
    assert processor._should_skip_episode(data)
    data.api_data["artifact_completion_policy"] = None
    assert not processor._should_skip_episode(data)


def test_partial_regen_cannot_opt_into_completion_policy(monkeypatch):
    monkeypatch.setattr(regen_orchestrator, "_load", lambda _: {
        "completed": ["extractor"], "invalidated_steps": [],
    })
    monkeypatch.setattr(regen_orchestrator, "_assemble", lambda _: {})
    try:
        regen_orchestrator.commit("ep-1", allow_missing_audio=True)
    except RegenError as exc:
        assert "all five required regen roles" in str(exc)
    else:
        raise AssertionError("partial regen must not record a completion policy")


def test_invalid_opt_in_is_rejected_before_any_upload(monkeypatch):
    import src.service.postgres_mirror_reader as episode_reader

    steps = list(regen_orchestrator.REQUIRED_STEPS)
    draft = {
        "completed": steps, "invalidated_steps": [], "podcast_name": "Show",
        "generation_metadata": provenance(),
    }
    monkeypatch.setattr(regen_orchestrator, "_load", lambda _: draft)
    monkeypatch.setattr(regen_orchestrator, "_assemble", lambda _: {
        "summary_content": "A regenerated summary.", "ticker_insights": [],
    })
    monkeypatch.setattr(episode_reader, "get_episode_by_id", lambda _: None)
    upload_calls = []
    monkeypatch.setattr(regen_orchestrator, "_upload_regen_content", lambda *args: upload_calls.append(args))
    try:
        regen_orchestrator.commit("ep-1", notify_platform=False, allow_missing_audio=True)
    except RegenError as exc:
        assert "transcript_url" in str(exc)
    else:
        raise AssertionError("missing source transcript must reject opt-in")
    assert upload_calls == []

    draft["transcript_url"] = "gs://media/transcript.json"
    monkeypatch.setattr(regen_orchestrator, "_assemble", lambda _: {
        "summary_content": "This is a placeholder summary.", "ticker_insights": [],
    })
    try:
        regen_orchestrator.commit("ep-1", notify_platform=False, allow_missing_audio=True)
    except RegenError as exc:
        assert "real regenerated summary" in str(exc)
    else:
        raise AssertionError("placeholder summary must reject opt-in")
    assert upload_calls == []

    monkeypatch.setattr(regen_orchestrator, "_assemble", lambda _: {
        "summary_content": "A regenerated summary.", "ticker_insights": [],
    })
    draft["generation_metadata"] = provenance(source="unknown")
    try:
        regen_orchestrator.commit("ep-1", notify_platform=False, allow_missing_audio=True)
    except RegenError as exc:
        assert "generated provenance" in str(exc)
    else:
        raise AssertionError("invalid role provenance must reject opt-in")
    assert upload_calls == []


def test_legacy_draft_uses_current_episode_transcript_without_rewriting_draft(monkeypatch):
    import src.podcast.exporters.ticker_insights as ticker_exporter
    import src.service.postgres_mirror_reader as episode_reader

    steps = list(regen_orchestrator.REQUIRED_STEPS)
    draft = {
        "completed": steps,
        "invalidated_steps": [],
        "podcast_name": "Show",
        "generation_metadata": provenance(),
        # This simulates a previously approved draft; leave it unmodified.
    }
    monkeypatch.setattr(regen_orchestrator, "_load", lambda _: draft)
    monkeypatch.setattr(regen_orchestrator, "_assemble", lambda _: {
        "summary_content": "A regenerated summary.", "ticker_insights": [],
    })
    monkeypatch.setattr(regen_orchestrator, "_require_live_media_root", lambda: None)
    monkeypatch.setattr(regen_orchestrator, "_upload_regen_content", lambda *args: ({"summary_url": "gs://media/summary.md"}, None))
    monkeypatch.setattr(regen_orchestrator, "_doc_update", lambda payload: {"summary_content": payload["summary_content"]})
    writes = []
    monkeypatch.setattr(regen_orchestrator, "_write_doc_update", lambda _episode_id, fields: writes.append(fields))
    monkeypatch.setattr(episode_reader, "get_episode_by_id", lambda _: {"transcript_url": "gs://media/transcript.json"})
    monkeypatch.setattr(ticker_exporter, "build_episode_insight_docs", lambda **kwargs: [])
    monkeypatch.setattr(ticker_exporter, "replace_episode_insights_postgres", lambda *_: 0)

    regen_orchestrator.commit("ep-1", notify_platform=False, allow_missing_audio=True)

    assert "transcript_url" not in draft
    assert writes[0]["artifact_completion_policy"] == POLICY
