"""The clusterer is a policy router over typed segments — and it must never zero out
every chapter.

Events carry a ``segment_type`` (+ ``is_substantive``); the router keeps/drops each per
the resolved show policy. Two guarantees are regression-tested here:
  1. ads/chitchat are dropped, analysis/guest kept, qa kept only when substantive;
  2. if the policy drops everything, the safety net still yields chapters — but never
     surfaces a sponsor/intro/outro as one.
"""
from src.podcast.content_builder.nodes.clusterer import cluster_sentences


def _sentences(n):
    return [{"index": i, "content": f"s{i}", "start": i * 1000, "end": i * 1000 + 900} for i in range(n)]


def _ev(topic, start, end, segment_type, is_substantive=True):
    return {
        "section_topic": topic, "start_index": start, "end_index": end,
        "segment_type": segment_type, "is_substantive": is_substantive,
    }


def test_drops_sponsor_and_chitchat_keeps_analysis():
    state = {"sentences": _sentences(9), "events": [
        _ev("業配：某保健食品", 0, 2, "sponsor"),
        _ev("台積電法說會解析", 3, 5, "analysis"),
        _ev("主持人聊上週去德國玩", 6, 8, "chitchat"),
    ]}
    out = cluster_sentences(state)["clustered_events"]
    assert [c["section_topic"] for c in out] == ["台積電法說會解析"]
    assert out[0]["start"] == 3000  # real timing still attached


def test_qa_kept_only_when_substantive():
    state = {"sentences": _sentences(9), "events": [
        _ev("聽眾問：可以幫我女友打氣嗎", 0, 2, "qa", is_substantive=False),
        _ev("聽眾問：怎麼看記憶體報價", 3, 5, "qa", is_substantive=True),
        _ev("聽眾問：推薦哪間餐廳", 6, 8, "qa", is_substantive=False),
    ]}
    out = cluster_sentences(state)["clustered_events"]
    assert [c["section_topic"] for c in out] == ["聽眾問：怎麼看記憶體報價"]


def test_guest_segment_kept():
    state = {"sentences": _sentences(6), "events": [
        _ev("來賓談半導體供應鏈", 0, 2, "guest"),
        _ev("片頭開場與問候", 3, 5, "intro"),
    ]}
    out = cluster_sentences(state)["clustered_events"]
    assert [c["section_topic"] for c in out] == ["來賓談半導體供應鏈"]


def test_missing_segment_type_is_kept_as_content():
    """Old data / a model that omitted the type -> unknown -> kept (never worse than before)."""
    state = {"sentences": _sentences(6), "events": [
        {"section_topic": "輝達的下一步佈局", "start_index": 0, "end_index": 2},
        {"section_topic": "美光與南韓廠商的角力", "start_index": 3, "end_index": 5},
    ]}
    out = cluster_sentences(state)["clustered_events"]
    assert len(out) == 2


def test_profile_policy_override_is_honored():
    """A show profile can override the default action for a type (here: keep chitchat)."""
    state = {
        "sentences": _sentences(6),
        "show_profile": {"structure_hint": "", "policy": {"chitchat": "keep"}},
        "events": [
            _ev("業配廣告", 0, 2, "sponsor"),
            _ev("主持人閒聊近況", 3, 5, "chitchat"),
        ],
    }
    out = cluster_sentences(state)["clustered_events"]
    assert [c["section_topic"] for c in out] == ["主持人閒聊近況"]


def test_safety_net_keeps_content_when_policy_drops_everything():
    """Policy drops all -> still yield chapters, but never an ad/intro/outro."""
    state = {"sentences": _sentences(6), "events": [
        _ev("業配廣告", 0, 2, "sponsor"),
        _ev("主持人閒聊", 3, 5, "chitchat"),
    ]}
    out = cluster_sentences(state)["clustered_events"]
    # sponsor stays dropped even in the net; chitchat resurfaces so the episode isn't empty.
    assert [c["section_topic"] for c in out] == ["主持人閒聊"]


def test_safety_net_never_surfaces_only_ads():
    state = {"sentences": _sentences(6), "events": [
        _ev("業配廣告一", 0, 2, "sponsor"),
        _ev("片尾道別", 3, 5, "outro"),
    ]}
    out = cluster_sentences(state)["clustered_events"]
    assert out == []  # nothing but ads/outro -> no bogus chapters


def test_empty_events_yields_empty():
    assert cluster_sentences({"sentences": _sentences(3), "events": []})["clustered_events"] == []


def test_dropped_segments_surface_as_skippable_with_timing_and_label():
    """Dropped segments are kept (lean, no sentences) so the player can offer skip chips."""
    state = {"sentences": _sentences(9), "events": [
        _ev("業配：某保健食品", 0, 2, "sponsor"),
        _ev("全聯紅酒品飲心得", 3, 5, "chitchat"),
        _ev("台積電法說會解析", 6, 8, "analysis"),
    ]}
    out = cluster_sentences(state)
    assert [c["section_topic"] for c in out["clustered_events"]] == ["台積電法說會解析"]
    skip = out["skipped_segments"]
    assert [s["segment_type"] for s in skip] == ["sponsor", "chitchat"]
    wine = skip[1]
    assert wine["label"] == "生活閒聊"          # zh-TW category for the chip
    assert wine["start"] == 3000 and wine["end"] == 5900  # real timing to seek to
    assert "sentences" not in wine               # lean record, no transcript payload


def test_safety_net_only_marks_ads_skippable():
    """When the policy drops everything and the net resurfaces content as chapters,
    only the ads/intro/outro remain skippable (the rest became real chapters)."""
    state = {"sentences": _sentences(6), "events": [
        _ev("業配廣告", 0, 2, "sponsor"),
        _ev("主持人閒聊", 3, 5, "chitchat"),
    ]}
    out = cluster_sentences(state)
    assert [c["section_topic"] for c in out["clustered_events"]] == ["主持人閒聊"]
    assert [s["segment_type"] for s in out["skipped_segments"]] == ["sponsor"]
