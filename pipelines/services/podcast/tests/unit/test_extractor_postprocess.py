"""Extractor postprocess normalizes segment_type / is_substantive; build_messages
injects the show's structure hint."""
from src.podcast.content_builder.nodes.extractor import build_messages, postprocess


def _events(result):
    return postprocess(result, {})["events"]


def test_normalizes_segment_type_case_and_invalid():
    out = _events({"events": [
        {"section_topic": "a", "start_index": 0, "end_index": 1, "segment_type": "ANALYSIS"},
        {"section_topic": "b", "start_index": 2, "end_index": 3, "segment_type": "weird-type"},
    ]})
    assert out[0]["segment_type"] == "analysis"
    assert out[1]["segment_type"] == "unknown"  # invalid -> unknown (kept downstream)


def test_missing_segment_type_defaults_unknown_and_substantive_true():
    out = _events({"events": [{"section_topic": "a", "start_index": 0, "end_index": 1}]})
    assert out[0]["segment_type"] == "unknown"
    assert out[0]["is_substantive"] is True


def test_sponsor_missing_substantive_defaults_false():
    out = _events({"events": [
        {"section_topic": "ad", "start_index": 0, "end_index": 1, "segment_type": "sponsor"},
    ]})
    assert out[0]["is_substantive"] is False


def test_is_substantive_string_coercion():
    out = _events({"events": [
        {"section_topic": "q1", "start_index": 0, "end_index": 1, "segment_type": "qa", "is_substantive": "true"},
        {"section_topic": "q2", "start_index": 2, "end_index": 3, "segment_type": "qa", "is_substantive": "false"},
    ]})
    assert out[0]["is_substantive"] is True
    assert out[1]["is_substantive"] is False


def test_tolerates_bare_list_result():
    out = _events([{"section_topic": "a", "start_index": 0, "end_index": 1, "segment_type": "qa", "is_substantive": True}])
    assert out[0]["segment_type"] == "qa"
    assert out[0]["is_substantive"] is True


def test_preserves_index_fields():
    out = _events({"events": [
        {"section_topic": "a", "start_index": 4, "end_index": 9, "segment_type": "analysis"},
    ]})
    assert (out[0]["start_index"], out[0]["end_index"]) == (4, 9)


def test_build_messages_injects_structure_hint():
    state = {
        "sentences": [{"index": 0, "content": "hi", "start": 0, "end": 1}],
        "source": "Gooaye 股癌",
        "episode_title": "EP1",
        "show_profile": {"structure_hint": "開場業配 → 分析 → Q&A", "policy": {}},
    }
    msgs = build_messages(state)
    assert msgs[0]["role"] == "system"
    assert "開場業配 → 分析 → Q&A" in msgs[1]["content"]


def test_build_messages_without_profile_uses_placeholder():
    state = {"sentences": [], "source": "X", "episode_title": "Y"}
    msgs = build_messages(state)  # must not raise KeyError on the missing hint
    assert "（無特定結構提示" in msgs[1]["content"]
