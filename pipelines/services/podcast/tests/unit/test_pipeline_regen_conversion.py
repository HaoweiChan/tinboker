"""Focused safeguards for converting Regen-backed episodes to pipeline artifacts."""

from src.models.podcast_models import PodcastEpisode
from src.pipeline.steps import ticker_insights_export
from src.podcast.content_builder.nodes.writer import build_messages


def test_writer_prompt_does_not_force_financial_analogies_onto_other_topics():
    messages = build_messages({
        "source": "曼報",
        "episode_title": "SP13：故事與文化",
        "clustered_events": [{"event_id": "E1", "text": "談論一段文化故事"}],
    })
    prompt = "\n".join(message["content"] for message in messages)
    assert "Do not force financial or investment framing" in prompt
    assert "A sponsor mention is not evidence" in prompt


def test_generation_metadata_survives_episode_document_roundtrip():
    metadata = {
        "version": 1,
        "roles": {"writer": {"source": "generated", "provider": "openrouter", "model": "actual"}},
    }
    original = PodcastEpisode(
        mp3_url="https://example.test/audio.mp3",
        transcript_url="https://example.test/transcript.txt",
        summary_url="https://example.test/summary.md",
        summary_image_url="https://example.test/summary.svg",
        generation_metadata=metadata,
    )

    restored = PodcastEpisode.from_firestore_dict(original.to_firestore_dict())

    assert restored.generation_metadata == metadata


def test_summarize_rerun_replaces_ticker_rows_even_for_empty_snapshot(monkeypatch):
    from types import SimpleNamespace

    from src.podcast.exporters import ticker_insights as ticker_export

    calls = []
    monkeypatch.setattr(ticker_export, "build_episode_insight_docs", lambda **kwargs: {})
    monkeypatch.setattr(
        ticker_export, "replace_episode_insights_postgres",
        lambda episode_id, docs: calls.append((episode_id, docs)) or 0,
    )
    monkeypatch.setattr(
        ticker_export, "write_episode_insights_postgres",
        lambda *args: (_ for _ in ()).throw(AssertionError("snapshot rerun must replace")),
    )
    config = SimpleNamespace(rerun_from="summarize")
    services = SimpleNamespace(firebase_service=object())
    episode_data = SimpleNamespace(
        summary_result={"ticker_insights": []}, episode_id="ep-1",
        episode=None, spotify_metadata=None, created_time="2026-01-01T00:00:00Z",
        podcast_name="Show",
    )

    ticker_insights_export.export_ticker_insights(config, services, episode_data)

    assert calls == [("ep-1", {})]


def test_key_insights_fallback_does_not_claim_generated_provenance(monkeypatch):
    from types import SimpleNamespace

    from src.podcast.content_builder import llm
    from src.podcast.content_builder.nodes import key_insights_extractor as node

    response = SimpleNamespace(
        content='{"key_insights": []}',
        response_metadata={"model_name": "actual/model", "provider": "actual"},
    )
    monkeypatch.setattr(llm, "_model_name", lambda role: "openrouter:requested/model")
    monkeypatch.setattr(llm, "get_model", lambda role: SimpleNamespace(invoke=lambda *a, **k: response))
    monkeypatch.setattr(llm, "_json_kwargs", lambda model: {})
    calls = []
    state = {"markdown_report": "一段足夠長的真實摘要。"}
    with llm.generation_context(None, calls):
        result = node.extract_key_insights_from_markdown(
            state["markdown_report"], source="Show", episode_title="Episode"
        )

    assert len(result) >= 3  # deterministic fallback still supplies display content
    assert calls == []  # but it cannot satisfy generated-role provenance


def test_summarize_conversion_clears_all_inline_artifact_aliases():
    from src.pipeline.steps.postgres_episode import (
        _REGEN_INLINE_FIELDS,
        _clear_regen_inline_content,
    )

    doc = {field: "old generation" for field in _REGEN_INLINE_FIELDS}
    _clear_regen_inline_content(doc)

    assert doc == {field: None for field in _REGEN_INLINE_FIELDS}
    assert "sentences_markdown_content" in doc
    assert "ticker_insights_content" in doc


def test_nine_valid_key_insights_keep_generated_provenance(monkeypatch):
    from types import SimpleNamespace

    from src.podcast.content_builder import llm
    from src.podcast.content_builder.nodes import key_insights_extractor as node

    items = [f"第{i}項是經過整理的重要觀察" for i in range(1, 10)]
    response = SimpleNamespace(
        content=__import__("json").dumps({"key_insights": items}, ensure_ascii=False),
        response_metadata={"model_name": "actual/model", "provider": "actual"},
    )
    monkeypatch.setattr(llm, "_model_name", lambda role: "openrouter:requested/model")
    monkeypatch.setattr(llm, "get_model", lambda role: SimpleNamespace(invoke=lambda *a, **k: response))
    monkeypatch.setattr(llm, "_json_kwargs", lambda model: {})
    calls = []
    with llm.generation_context(None, calls):
        result = node.extract_key_insights_from_markdown(
            "足夠長的真實摘要內容。", source="Show", episode_title="Episode"
        )

    assert len(result) == 8
    assert len(calls) == 1
    assert calls[0]["role"] == "key_insights_extractor"


def test_name_normalizer_call_is_included_in_pipeline_provenance(monkeypatch):
    from types import SimpleNamespace

    from src.podcast.content_builder import graph, llm

    monkeypatch.setattr(graph, "build_graph", lambda: SimpleNamespace(invoke=lambda state: {
        "markdown_report": "完整摘要", "events_markdown": "事件", "marp_markdown": "投影片",
        "ticker_insights": None, "ticker_marp_markdown": "", "key_insights": [],
        "tags": [], "related_tickers": [], "social_cards": [], "social_thread": {},
        "sector_exposures": [], "unresolved_market_trends": [], "macro_claims": [],
        "sector_exposure_ids": [], "sector_ids": [], "unresolved_market_trend_ids": [],
    }))
    from src.podcast.content_builder import profiles
    monkeypatch.setattr(profiles, "load_profile", lambda source: {})
    response = SimpleNamespace(
        content='{"corrections": []}',
        response_metadata={"model_name": "actual/normalizer", "provider": "actual"},
    )
    monkeypatch.setattr(llm, "_model_name", lambda role: "openrouter:requested/model")
    monkeypatch.setattr(llm, "get_model", lambda role: SimpleNamespace(invoke=lambda *a, **k: response))
    monkeypatch.setattr(llm, "_json_kwargs", lambda model: {})

    result = graph.run_pipeline("transcript", [], source="Show", episode_title="Episode")

    normalizer = result["generation_metadata"]["roles"]["name_normalizer"]
    assert normalizer["model"] == "actual/normalizer"
    assert normalizer["provider"] == "actual"
