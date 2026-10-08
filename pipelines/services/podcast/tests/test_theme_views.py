"""Offline checks for transcript-grounded extraction and the optional pipeline step."""

import json
import time
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from podcast.content_builder import llm
from podcast.content_builder.theme_views import build_episode_input, validate_theme_views
from shared import platform_client, sectors
from src.pipeline import EpisodeProcessor
from src.pipeline.episode_data import EpisodeData
from src.pipeline.steps.theme_views import extract_theme_views


@pytest.fixture
def transcript():
    return {"sentences": [
        {"content": f"國巨需求有機會成長{i}。", "start": i * 1000, "end": (i + 1) * 1000}
        for i in range(10)
    ]}


@pytest.fixture
def summary():
    return "[國巨](#ticker:2327) [國巨](#ticker:2327) [雜訊](https://example.test)"


@pytest.fixture
def output():
    return {"episode_id": "episode-1", "theme_views": [{
        "theme_label": "被動元件 MLCC", "stance": "bullish", "conviction": "tentative",
        "thesis": "國巨需求有機會成長，仍需觀察。", "start_ms": 0,
        "quote": "國巨需求有機會成長0。",
        "tickers": [{"name": "國巨", "ticker": "2327", "role": "beneficiary"}],
    }]}


def test_build_input_groups_eight_sentences(transcript, summary):
    text, starts, anchors, raw = build_episode_input("episode-1", transcript, summary)
    assert text.startswith("EPISODE episode-1")
    assert text.count("- 國巨 -> 2327") == 1
    assert "[0] 國巨需求有機會成長0。" in text
    assert "[8000] 國巨需求有機會成長8。" in text
    assert starts == {0, 8000}
    assert anchors == {("國巨", "2327")}
    assert "成長9。" in raw
    assert "example.test" not in text


def test_validation_sanitizes_and_canonicalizes(transcript, summary, output):
    _, starts, anchors, raw = build_episode_input("episode-1", transcript, summary)
    view = output["theme_views"][0]
    view.update(start_ms=1000, quote="Not in the transcript")
    view["tickers"] += [
        {"name": "國巨", "ticker": "9999", "role": "beneficiary"},
        {"name": "國巨", "ticker": "2327", "role": "other"},
    ]
    result = validate_theme_views(output, "episode-1", starts, anchors, raw, [])[0]
    assert result["start_ms"] is None
    assert result["quote"] is None
    assert result["theme_label"] == "被動元件"
    assert result["exposure_id"] == "sector_mlcc"
    assert len(result["tickers"]) == 1


@pytest.mark.parametrize("bad", ["count", "stance", "conviction", "keys", "missing"])
def test_invalid_output_rejected(bad, output):
    if bad == "count":
        output["theme_views"] *= 4
    elif bad == "keys":
        output["theme_views"][0]["extra"] = True
    elif bad == "missing":
        del output["theme_views"]
    else:
        output["theme_views"][0][bad] = "invalid"
    with pytest.raises(ValueError):
        validate_theme_views(output, "episode-1", {0}, set(), "", [])


def test_unique_taxonomy_alias_and_whitespace_quote(output):
    view = output["theme_views"][0]
    view.update(theme_label=" C X L ", quote="國 巨需求")
    taxonomy = [{"display_name": "CXL 技術", "aliases": ["cxl"], "exposure_id": "sector_cxl"}]
    result = validate_theme_views(output, "episode-1", {0}, set(), "國巨需求", taxonomy)[0]
    assert result["exposure_id"] == "sector_cxl"
    assert result["quote"] == "國 巨需求"
    taxonomy.append({"display_zh": "CXL", "exposure_id": "sector_other"})
    assert validate_theme_views(output, "episode-1", {0}, set(), "", taxonomy)[0]["exposure_id"] is None
    view["theme_label"] = "記憶體漲價循環"
    result = validate_theme_views(output, "episode-1", {0}, set(), "", taxonomy)[0]
    assert (result["theme_label"], result["exposure_id"]) == ("記憶體", None)
    assert validate_theme_views({"episode_id": "episode-1", "theme_views": []}, "episode-1", set(), set(), "", []) == []


# Inside the step's 90-day window; a fixed old timestamp would be skipped as back-catalogue.
RECENT_MS = int(time.time() * 1000) - 86_400_000


@pytest.fixture
def step_setup(monkeypatch, transcript, summary, output):
    monkeypatch.setenv("TINBOKER_PLATFORM_API_URL", "https://platform.test")
    monkeypatch.setenv("TINBOKER_WRITE_TOKEN", "test-only-token")
    monkeypatch.setenv("THEME_VIEWS_EXTRACTOR_MODEL", "openrouter:test/model")
    monkeypatch.delenv("TINBOKER_ADMIN_API_URL", raising=False)
    model = Mock()
    # Fenced, as models tend to answer.
    model.invoke.return_value.content = f"```json\n{json.dumps(output)}\n```"
    get_model = Mock(return_value=model)
    monkeypatch.setattr(llm, "get_model", get_model)
    monkeypatch.setattr(sectors, "load_universe", lambda: {"exposures": []})
    put = Mock(return_value={"stored": 1})
    monkeypatch.setattr(platform_client, "put_theme_views", put)
    data = EpisodeData(
        api_data={"episodeNumber": 42, "released_at_ms": RECENT_MS},
        podcast_name="Test Show", language="zh", episode_id="episode-1",
        transcript_sentences=transcript["sentences"], summary_result={"summary_text": summary},
    )
    return data, get_model, model, put


def test_step_put_shape_and_no_document_mutation(step_setup, base_config, base_context):
    data, get_model, model, put = step_setup
    before = deepcopy(data)
    extract_theme_views(base_config, base_context, data)
    get_model.assert_called_once_with("theme_views_extractor", max_retries=0, timeout=180.0, disable_reasoning=False)
    model.invoke.assert_called_once()
    body = put.call_args.args[1]
    assert put.call_args.args[0] == "episode-1"
    assert set(body) == {"podcaster", "episode_number", "released_at_ms", "source", "theme_views"}
    assert body["podcaster"] == "Test Show"
    assert body["episode_number"] == "42"
    assert body["released_at_ms"] == RECENT_MS
    assert body["source"] == "pipeline"
    assert body["theme_views"][0]["tickers"] == [{"ticker": "2327", "name": "國巨", "role": "beneficiary"}]
    assert data == before


@pytest.mark.parametrize("missing", ["api", "model", "token", "opt_in"])
def test_missing_configuration_skips(missing, step_setup, monkeypatch, base_config, base_context, caplog):
    data, get_model, model, put = step_setup
    if missing == "api":
        monkeypatch.delenv("TINBOKER_PLATFORM_API_URL")
    elif missing == "token":
        monkeypatch.delenv("TINBOKER_WRITE_TOKEN")
    elif missing == "opt_in":
        monkeypatch.delenv("THEME_VIEWS_EXTRACTOR_MODEL")
    else:
        get_model.side_effect = RuntimeError("no model configured")
    with caplog.at_level("INFO"):
        extract_theme_views(base_config, base_context, data)
    assert "episode-1" in caplog.text
    model.invoke.assert_not_called()
    put.assert_not_called()


@pytest.mark.parametrize("failure", ["llm", "json", "http"])
def test_failures_never_retry(failure, step_setup, base_config, base_context, caplog):
    data, _, model, put = step_setup
    if failure == "llm":
        model.invoke.side_effect = RuntimeError("provider failed")
    elif failure == "json":
        model.invoke.return_value.content = "invalid JSON"
    else:
        put.side_effect = OSError("HTTP failed")
    extract_theme_views(base_config, base_context, data)
    model.invoke.assert_called_once()
    assert put.call_count == (1 if failure == "http" else 0)
    assert "episode-1" in caplog.text


def test_rerun_loads_artifacts_without_mutating_episode(step_setup, base_config, base_context, transcript, summary):
    data, _, _, put = step_setup
    base_config.rerun_from = "theme-views"
    data.transcript_sentences = None
    data.summary_result = None
    data.gcs_urls = {"transcript_url": "transcript", "summary_url": "summary"}
    base_context.gcs_service.download_transcript_by_gcs_url.return_value = transcript
    base_context.gcs_service.download_text_by_gcs_url.return_value = summary
    before = deepcopy(data)
    extract_theme_views(base_config, base_context, data)
    put.assert_called_once()
    assert data == before
    base_context.gcs_service.upload_episode_files.assert_not_called()


def test_processor_runs_once_and_rerun_only_runs_optional_step(monkeypatch, base_config, base_context):
    import src.pipeline.processor as processor_module

    base_context.stt_service = None
    processor = EpisodeProcessor(base_config, base_context)
    monkeypatch.setattr(processor, "_load_existing_data", lambda data: None)
    monkeypatch.setattr(processor, "_should_skip_episode", lambda data: False)
    steps = {}
    for name in (
        "download_episode", "transcribe_episode", "generate_summary", "upload_to_gcs",
        "render_social_cards", "persist_episode", "extract_theme_views", "ingest_into_wiki",
        "export_ticker_insights", "trigger_syndicate", "validate_episode",
    ):
        steps[name] = Mock()
        monkeypatch.setattr(processor_module, name, steps[name])
    assert processor.process_episode({"title": "Test"})
    steps["extract_theme_views"].assert_called_once()
    for mock in steps.values():
        mock.reset_mock()
    base_config.rerun_from = "theme-views"
    assert processor.process_episode({"title": "Test"})
    steps["extract_theme_views"].assert_called_once()
    assert sum(mock.call_count for mock in steps.values()) == 1


def test_put_helper_encodes_id_and_uses_existing_http_stack(monkeypatch):
    monkeypatch.setenv("TINBOKER_ADMIN_API_URL", "https://admin.test")
    monkeypatch.setenv("TINBOKER_WRITE_TOKEN", "test-only-token")
    response = Mock()
    response.__enter__ = Mock(return_value=SimpleNamespace(read=lambda: b'{"stored": 0}'))
    response.__exit__ = Mock(return_value=False)
    urlopen = Mock(return_value=response)
    monkeypatch.setattr(platform_client.urllib.request, "urlopen", urlopen)
    body = {"theme_views": []}
    assert platform_client.put_theme_views("ep/one", body) == {"stored": 0}
    request = urlopen.call_args.args[0]
    assert request.full_url == "https://admin.test/api/theme-views/episode/ep%2Fone"
    assert request.method == "PUT"
    assert json.loads(request.data) == body
    assert urlopen.call_args.kwargs["timeout"] == 30.0


def test_episode_id_rerun_uses_loaded_episode_and_never_runs_processor(
    monkeypatch, base_config, base_context,
):
    from src.pipeline.steps import theme_views
    from src.podcast import firestore_reprocessor

    step = Mock()
    processor = Mock()
    monkeypatch.setattr(theme_views, "extract_theme_views", step)
    monkeypatch.setattr(firestore_reprocessor, "EpisodeProcessor", processor)
    stored = {
        "podcast_name": "Test Show", "episode_number": "42", "released_at_ms": 123456,
        "summary_content": "[國巨](#ticker:2327)", "transcript_url": "transcript",
    }
    assert firestore_reprocessor.process_firestore_episode(
        stored, "exact-id", config_file=base_config.config_file,
        rerun_from="theme-views", transcript_service="groq", use_file_mode=False,
        reuse_existing_transcript=False, base_config=base_config,
        service_container=base_context, podcast_config_mapping={}, podcasts=[],
    )
    step.assert_called_once()
    data = step.call_args.args[2]
    assert data.episode_id == "exact-id"
    assert data.summary_result == {"summary_text": "[國巨](#ticker:2327)"}
    assert data.api_data["released_at_ms"] == 123456
    processor.assert_not_called()


def test_theme_role_resolution_and_no_sdk_retry(monkeypatch):
    import langchain_openai

    monkeypatch.setattr(llm, "_LLM_OVERRIDES", {})
    monkeypatch.delenv("PIPELINE_LLM_MODEL", raising=False)
    monkeypatch.delenv("THEME_VIEWS_EXTRACTOR_MODEL", raising=False)
    with pytest.raises(RuntimeError):
        llm.get_model("theme_views_extractor", max_retries=0, timeout=120.0)
    monkeypatch.setenv("THEME_VIEWS_EXTRACTOR_MODEL", "local:test-model")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://local.test/v1")
    constructor = Mock()
    monkeypatch.setattr(langchain_openai, "ChatOpenAI", constructor)
    llm.get_model("theme_views_extractor", max_retries=0, timeout=120.0)
    assert constructor.call_args.kwargs["max_retries"] == 0
    assert constructor.call_args.kwargs["timeout"] == 120.0
    assert constructor.call_args.kwargs["model"] == "test-model"


@pytest.mark.parametrize("synonym,canonical", [
    ("散熱", "液冷散熱"), ("軟體", "企業 SaaS"), ("CPU", "CPU 與 Agentic AI"),
])
def test_canonical_identity_survives_unavailable_taxonomy(synonym, canonical, output):
    output["theme_views"][0]["theme_label"] = synonym
    first = validate_theme_views(output, "episode-1", {0}, set(), "", [])[0]
    output["theme_views"][0]["theme_label"] = canonical
    second = validate_theme_views(output, "episode-1", {0}, set(), "", [])[0]
    assert first["exposure_id"] == second["exposure_id"]
    assert first["theme_label"] == second["theme_label"]


def test_canonical_theme_merges_spelling_variants_and_uses_taxonomy_names():
    from podcast.content_builder.theme_views import canonical_theme

    taxonomy = [{"display_zh": "客製 ASIC 矽智財", "aliases": ["ASIC"], "exposure_id": "sector_asic_ip"}]
    assert canonical_theme("ASIC", taxonomy) == ("客製 ASIC 矽智財", "sector_asic_ip")
    assert canonical_theme("AI算力", []) == canonical_theme("AI 算力", []) == ("AI 算力需求", None)
    assert canonical_theme("記憶體族群", taxonomy) == ("記憶體", None)
    assert canonical_theme("沒人聽過的題材", taxonomy) == ("沒人聽過的題材", None)


def test_a_mistyped_episode_id_echo_does_not_discard_the_views(output):
    output["episode_id"] = "not-the-id"
    assert len(validate_theme_views(output, "episode-1", {0}, set(), "", [])) == 1


def test_back_catalogue_episode_is_skipped_unless_rerun_explicitly(step_setup, base_config, base_context):
    data, _, model, put = step_setup
    data.api_data["released_at_ms"] = RECENT_MS - 200 * 86_400_000
    extract_theme_views(base_config, base_context, data)
    model.invoke.assert_not_called()
    put.assert_not_called()

    base_config.rerun_from = "theme-views"
    extract_theme_views(base_config, base_context, data)
    put.assert_called_once()


def test_outcome_is_printed_where_the_scheduled_run_shows_it(step_setup, base_config, base_context, capsys):
    data, _, _, _ = step_setup
    extract_theme_views(base_config, base_context, data)
    assert "Theme views stored for episode-1" in capsys.readouterr().out
