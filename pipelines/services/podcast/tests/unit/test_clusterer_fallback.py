"""The clusterer must never zero out every chapter just because topic labels miss a keyword.

Regression for the bug where a legitimately financial episode whose LLM topic labels
happened to contain no hardcoded finance keyword produced 0 clustered events -> a
summary with no #time chapters.
"""
from src.podcast.content_builder.nodes.clusterer import cluster_sentences


def _sentences(n):
    return [{"index": i, "content": f"s{i}", "start": i * 1000, "end": i * 1000 + 900} for i in range(n)]


def test_keeps_financial_topics_when_present():
    state = {"sentences": _sentences(6), "events": [
        {"section_topic": "台積電法說會解析", "start_index": 0, "end_index": 2},
        {"section_topic": "閒聊與生活雜談", "start_index": 3, "end_index": 5},
    ]}
    out = cluster_sentences(state)["clustered_events"]
    assert [c["section_topic"] for c in out] == ["台積電法說會解析"]


def test_fallback_to_all_topics_when_no_keyword_matches():
    """No finance keyword in any label, but the episode clearly has topics -> keep them."""
    state = {"sentences": _sentences(6), "events": [
        {"section_topic": "輝達的下一步佈局", "start_index": 0, "end_index": 2},
        {"section_topic": "美光與南韓廠商的角力", "start_index": 3, "end_index": 5},
    ]}
    out = cluster_sentences(state)["clustered_events"]
    assert len(out) == 2  # neither matched a keyword, but both kept via fallback
    assert out[0]["start"] == 0


def test_fallback_drops_ads_and_intros():
    state = {"sentences": _sentences(9), "events": [
        {"section_topic": "Toyota汽車廣告", "start_index": 0, "end_index": 2},
        {"section_topic": "節目開場與主持人介紹", "start_index": 3, "end_index": 5},
        {"section_topic": "來賓暢談新書理念", "start_index": 6, "end_index": 8},
    ]}
    out = cluster_sentences(state)["clustered_events"]
    assert [c["section_topic"] for c in out] == ["來賓暢談新書理念"]


def test_empty_events_yields_empty():
    assert cluster_sentences({"sentences": _sentences(3), "events": []})["clustered_events"] == []
