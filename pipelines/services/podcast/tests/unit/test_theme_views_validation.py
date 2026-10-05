"""Network-free checks for the standalone theme-view validation prototype."""

import argparse
import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from podcast.theme_views_validation import (
    parse_chapters,
    run,
    select_episodes,
    taxonomy_index,
    validate_response,
)

SUMMARY = """# Episode
## 被動元件需求 (#time:1200)
[國巨](#ticker:2327)受惠於伺服器需求增加，產品價格有望上揚。
## 記憶體 (#time:2500)
[美光](#ticker:MU)吸引資金。
## 風險
庫存仍有風險。
"""
TAXONOMY = [{"display_zh": "被動元件 MLCC", "aliases": ["被動元件", "MLCC"],
             "exposure_type": "theme", "exposure_id": "sector_mlcc"}]
VIEW = {"theme_label": "被動元件", "stance": "bullish",
        "thesis": "伺服器需求增加帶動被動元件價格上揚。", "start_time_ms": 1200,
        "named_tickers": [{"ticker": "2327", "name": "國巨"}],
        "evidence": "受惠於伺服器需求增加，產品價格有望上揚。"}


def test_validated_views_and_deterministic_taxonomy():
    result = validate_response(json.dumps({"theme_views": [VIEW]}), SUMMARY, TAXONOMY)
    assert result[0]["exposure_id"] == "sector_mlcc"
    assert result[0]["named_tickers"] == [{"ticker": "2327", "name": "國巨", "market": "TW"}]
    assert result[0]["evidence_verbatim"] is True
    assert [c["start_time_ms"] for c in parse_chapters(SUMMARY)] == [1200, 2500, None]
    assert taxonomy_index(TAXONOMY)["mlcc"] == "sector_mlcc"
    alias = dict(VIEW, theme_label=" ＭＬＣＣ ")
    assert validate_response(json.dumps({"theme_views": [alias]}), SUMMARY, TAXONOMY)[0]["exposure_id"] == "sector_mlcc"
    unknown = dict(VIEW, theme_label="伺服器零組件")
    assert validate_response(json.dumps({"theme_views": [unknown]}), SUMMARY, TAXONOMY)[0]["exposure_id"] is None
    ambiguous = TAXONOMY + [dict(TAXONOMY[0], exposure_id="different")]
    assert taxonomy_index(ambiguous)["被動元件"] is None
    assert taxonomy_index([dict(TAXONOMY[0], exposure_type="industry")]) == {}
    assert validate_response('{"theme_views": []}', SUMMARY, TAXONOMY) == []


@pytest.mark.parametrize("change", [
    {"start_time_ms": 1201}, {"start_time_ms": "1200"}, {"start_time_ms": True},
    {"stance": "buy"}, {"evidence": " "},
    {"named_tickers": [{"ticker": "2327", "name": "美光"}]},
    {"named_tickers": [{"ticker": "UNKNOWN", "name": "國巨"}]},
    {"exposure_id": "sector_mlcc"},
])
def test_rejects_invalid_or_ungrounded_response(change):
    view = dict(VIEW, **change)
    with pytest.raises(ValueError):
        validate_response(json.dumps({"theme_views": [view]}), SUMMARY, TAXONOMY)


def test_cross_chapter_grounding_is_accepted_and_loose_quotes_are_flagged():
    """Topics span a timed heading plus untimed sub-headings, and the model
    paraphrases quotes — neither may discard an otherwise grounded view."""
    for change in ({"start_time_ms": None}, {"start_time_ms": 2500},
                   {"named_tickers": [{"ticker": "MU", "name": "美光"}]}):
        view = dict(VIEW, **change)
        assert validate_response(json.dumps({"theme_views": [view]}), SUMMARY, TAXONOMY)[0]["evidence_verbatim"] is True
    loose = dict(VIEW, evidence="Invented quote")
    assert validate_response(json.dumps({"theme_views": [loose]}), SUMMARY, TAXONOMY)[0]["evidence_verbatim"] is False


def test_limits_null_anchors_and_selection():
    with pytest.raises(ValueError):
        validate_response(json.dumps({"theme_views": [VIEW] * 4}), SUMMARY, TAXONOMY)
    with pytest.raises(ValueError):
        validate_response(json.dumps({"theme_views": [VIEW] * 2}), SUMMARY, TAXONOMY)
    with pytest.raises(ValueError):
        validate_response(json.dumps({"theme_views": [VIEW, dict(VIEW, theme_label="MLCC")]}), SUMMARY, TAXONOMY)
    with pytest.raises(ValueError):
        validate_response('```json\n{"theme_views": []}\n```', SUMMARY, TAXONOMY)
    unanchored = dict(VIEW, start_time_ms=None, named_tickers=[], evidence="庫存仍有風險。")
    assert validate_response(json.dumps({"theme_views": [unanchored]}), SUMMARY, TAXONOMY)[0]["start_time_ms"] is None
    rows = [{"episode_id": f"Gooaye_{i}", "podcast_name": "Gooaye 股癌", "released_at": f"2026-01-{i + 1:02}"}
            for i in range(13)]
    assert select_episodes(rows, ["Gooaye_0", "Gooaye_0"], None, 12) == [rows[0]]
    assert select_episodes(rows, [], "Gooaye 股癌", 2) == [rows[12], rows[11]]
    with pytest.raises(ValueError):
        select_episodes(rows, [r["episode_id"] for r in rows], None, 12)
    with pytest.raises(ValueError):
        select_episodes(rows, [], "Gooaye 股癌", 13)


def test_run_caches_paid_response_before_validation_and_never_retries(tmp_path, monkeypatch):
    from podcast.content_builder import llm
    from shared import secrets

    monkeypatch.setattr(secrets, "bootstrap", Mock())
    client = Mock()
    model = Mock(model_name="test/model", _identifying_params={"temperature": 0.1})
    model.root_client.with_options.return_value = client
    model.model_copy.return_value = model
    model.invoke.return_value = SimpleNamespace(
        content=json.dumps({"theme_views": [VIEW]}),
        usage_metadata={"input_tokens": 100, "output_tokens": 30, "total_tokens": 130},
        response_metadata={"token_usage": {"cost": 0.0001}},
    )
    monkeypatch.setattr(llm, "get_model", lambda *args, **kwargs: model)
    episodes = tmp_path / "episodes.json"
    episodes.write_text(json.dumps([{"episode_id": "Gooaye_test", "podcast_name": "Gooaye 股癌",
        "episode_number": 1, "released_at": "2026-01-01", "summary_markdown": SUMMARY}]))
    taxonomy = tmp_path / "taxonomy.json"
    taxonomy.write_text(json.dumps(TAXONOMY))
    args = argparse.Namespace(episodes_json=episodes, taxonomy_json=taxonomy, out=tmp_path / "out",
                              episode_ids=["Gooaye_test"], podcast=None, limit=12, model=None)
    first = run(args)
    assert first["calls"] == 1 and first["total_tokens"] == 130
    assert first["cost_usd"] == 0.0001 and first["cost_complete"]
    assert first["errors"] == {}
    assert (args.out / "theme_views_review.md").exists()
    assert (args.out / "Gooaye_test.json").exists()
    assert run(args)["cached_responses"] == 1
    model.invoke.assert_called_once()
    model.root_client.with_options.assert_called_with(timeout=90, max_retries=0)

    # A new output directory demonstrates invalid output is cached before rejection.
    args.out = tmp_path / "invalid"
    invalid = copy.deepcopy(VIEW)
    invalid["start_time_ms"] = 99999
    model.invoke.return_value.content = json.dumps({"theme_views": [invalid]})
    assert run(args)["errors"] == {"Gooaye_test": "ValueError"}
    assert (args.out / "Gooaye_test.raw.json").exists()
    assert not (args.out / "Gooaye_test.json").exists()
    assert run(args)["cached_responses"] == 1
    assert model.invoke.call_count == 2
    # A failed request leaves an attempt marker and cannot silently bill a retry.
    args.out = tmp_path / "failed"
    model.invoke.side_effect = TimeoutError
    failed = run(args)
    assert failed["calls"] == 1 and not failed["cost_complete"]
    assert run(args)["calls"] == 0
    assert model.invoke.call_count == 3
