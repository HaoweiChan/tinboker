"""macro_extractor: vocabulary gate, deterministic timestamps, one claim per indicator,
and — above all — that it can never sink an episode."""

from __future__ import annotations

from src.podcast.content_builder import macro_vocab
from src.podcast.content_builder.nodes import macro_extractor as mx

_STATE = {
    "source": "游庭皓的財經皓角",
    "episode_title": "油價破百",
    "clustered_events": [
        {"section_topic": "債市", "sentences": [
            {"index": 40, "content": "殖利率直接衝高到4.94了", "start": 1288080, "end": 1290000},
            {"index": 41, "content": "市場在重新定價", "start": 1290000, "end": 1292000},
        ]},
    ],
}


def _row(**kw):
    base = {"indicator_id": "US10Y", "display_name": "美債10年期殖利率", "level_quoted": "4.94%",
            "direction_expected": "UP", "claim": "回購反而讓殖利率衝高", "reasons": ["市場不滿回購力道"],
            "implication": "壓抑股市估值", "time_horizon": "SHORT_TERM", "quote": "殖利率直接衝高到4.94了",
            "start_index": 40, "confidence": 0.9}
    return {**base, **kw}


def test_prompt_carries_the_vocabulary_and_the_events():
    system, user = (m["content"] for m in mx.build_messages(_STATE))
    assert "US10Y：美債10年期殖利率" in system and "DIESEL_US" in system
    assert "start_index" in system and "start_time" not in system      # the model never writes a time
    assert "殖利率直接衝高到4.94了" in user and "游庭皓的財經皓角" in user


def test_time_comes_from_the_sentence_index_in_seconds():
    out = mx.postprocess({"macro_claims": [_row()]}, _STATE)["macro_claims"]
    assert out[0]["start_time_s"] == 1288.08 and out[0]["indicator_id"] == "US10Y"
    # An invented index yields no time rather than a wrong one.
    assert mx.postprocess({"macro_claims": [_row(start_index=999)]}, _STATE)["macro_claims"][0]["start_time_s"] is None


def test_off_vocabulary_low_confidence_and_empty_claims_are_dropped():
    rows = [_row(indicator_id="BEEF"), _row(indicator_id="GOLD"), _row(confidence=0.4), _row(claim="  "),
            _row(indicator_id="wti", claim="油價破百")]
    out = mx.postprocess({"macro_claims": rows}, _STATE)["macro_claims"]
    assert [r["indicator_id"] for r in out] == ["WTI"]                  # id normalised, the rest gone


def test_one_claim_per_indicator_keeps_the_most_confident():
    rows = [_row(confidence=0.7, claim="先講的"), _row(confidence=0.95, claim="講得最完整的")]
    out = mx.postprocess({"macro_claims": rows}, _STATE)["macro_claims"]
    assert len(out) == 1 and out[0]["claim"] == "講得最完整的"


def test_enums_are_coerced_and_junk_payloads_are_empty():
    out = mx.postprocess({"macro_claims": [_row(direction_expected="sideways", time_horizon="soon")]}, _STATE)
    assert (out["macro_claims"][0]["direction_expected"], out["macro_claims"][0]["time_horizon"]) == ("UNCLEAR", "UNCLEAR")
    assert mx.postprocess("nonsense", _STATE) == {"macro_claims": []}
    assert mx.postprocess({"macro_claims": ["x", None]}, _STATE) == {"macro_claims": []}


def test_a_failing_llm_call_returns_empty_instead_of_raising(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("openrouter 502")
    monkeypatch.setattr(mx, "invoke_json", boom)
    assert mx.extract_macro(_STATE) == {"macro_claims": []}


def test_node_is_wired_as_a_terminal_branch_and_reaches_the_outputs():
    import inspect

    from src.podcast.content_builder import graph
    src = inspect.getsource(graph)
    assert 'add_edge("cluster_sentences", "extract_macro")' in src and 'add_edge("extract_macro", END)' in src
    assert '"macro_claims": result.get("macro_claims", [])' in src


def test_macro_claims_travel_from_the_summary_result_to_the_episode_doc_and_back():
    """The sector transport: a field on the episode doc, so regen persists it for free."""
    from types import SimpleNamespace

    from src.models.podcast_models import PodcastEpisode
    from src.pipeline.utils import create_episode_object

    claims = mx.postprocess({"macro_claims": [_row()]}, _STATE)["macro_claims"]
    episode = create_episode_object(
        episode_data=SimpleNamespace(api_data={}, tickers=[], podcast_name="游庭皓的財經皓角", created_time=None),
        gcs_urls={}, spotify_metadata=None,
        summary_result={"summary_text": "x", "macro_claims": claims},
    )
    assert episode.macro_claims == claims
    doc = episode.to_firestore_dict()
    assert doc["macro_claims"] == claims
    assert PodcastEpisode.from_firestore_dict(doc).macro_claims == claims
    assert PodcastEpisode.from_firestore_dict({}).macro_claims == []
    assert set(macro_vocab.MACRO_SERIES) >= {"US10Y", "WTI", "DXY"}
