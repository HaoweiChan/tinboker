"""Unit tests for the key_insights extractor + sanitizer + Firestore field.

Covers the contract's hard formatting rules (plain text, no markdown / #ticker /
#tag / #time markers / quotes / bullets), the extractor's tolerance of the
alternate ``insights`` key and its best-effort failure behavior, the LangGraph
node wiring, and the merge-safe Firestore write on ``PodcastEpisode``.
"""

from __future__ import annotations

from datetime import datetime

from src.models.podcast_models import PodcastEpisode
from src.podcast.content_builder.nodes import key_insights_extractor as kx

# ---------------------------------------------------------------------------
# sanitize_key_insights
# ---------------------------------------------------------------------------

def test_sanitizer_unwraps_links_and_strips_anchor_markers():
    raw = ["[台積電](#ticker:2330)法說會釋出樂觀展望 (#time:123456)"]
    assert kx.sanitize_key_insights(raw) == ["台積電法說會釋出樂觀展望"]


def test_sanitizer_strips_tag_links_and_keeps_label():
    raw = ["關注[降息](#tag:rate_cut)時點"]
    assert kx.sanitize_key_insights(raw) == ["關注降息時點"]


def test_sanitizer_removes_list_markers_and_emphasis():
    raw = [
        "- **國安基金退場**，台股回歸市場自主動能",
        "1. 外資資金輪動轉向傳產",
        "> 引用某段話",
        "* `code` 風格項目",
    ]
    assert kx.sanitize_key_insights(raw) == [
        "國安基金退場，台股回歸市場自主動能",
        "外資資金輪動轉向傳產",
        "引用某段話",
        "code 風格項目",
    ]


def test_sanitizer_strips_surrounding_quotes_ascii_and_cjk():
    raw = ['"市場急漲後勿追高"', "「分批佈局良機」", "『聯準會降息』"]
    assert kx.sanitize_key_insights(raw) == [
        "市場急漲後勿追高",
        "分批佈局良機",
        "聯準會降息",
    ]


def test_sanitizer_dedupes_preserving_order():
    raw = ["甲觀點", "乙觀點", "甲觀點"]
    assert kx.sanitize_key_insights(raw) == ["甲觀點", "乙觀點"]


def test_sanitizer_caps_at_eight():
    raw = [f"洞察{i}" for i in range(12)]
    assert len(kx.sanitize_key_insights(raw)) == 8


def test_sanitizer_drops_empty_nonstring_and_overlong():
    raw = ["   ", None, 42, "x" * 200, "有效洞察"]
    assert kx.sanitize_key_insights(raw) == ["有效洞察"]


def test_sanitizer_non_list_returns_empty():
    assert kx.sanitize_key_insights(None) == []
    assert kx.sanitize_key_insights("not a list") == []


def test_sanitized_items_carry_no_forbidden_markers():
    raw = ["[台積電](#ticker:2330) (#time:9) **強** > q"]
    for item in kx.sanitize_key_insights(raw):
        for marker in ("#ticker:", "#tag:", "#time:", "](", "**", "`"):
            assert marker not in item
        assert item == item.strip()
        assert not item.startswith(("-", "*", '"', "'", "「"))


# ---------------------------------------------------------------------------
# extract_key_insights_from_markdown
# ---------------------------------------------------------------------------

def test_extractor_empty_markdown_short_circuits(monkeypatch):
    # Must not call the LLM at all for empty/blank input.
    def boom(*a, **k):  # pragma: no cover - should never run
        raise AssertionError("invoke_json should not be called for empty markdown")

    monkeypatch.setattr(kx, "invoke_json", boom)
    assert kx.extract_key_insights_from_markdown("") == []
    assert kx.extract_key_insights_from_markdown("   \n ") == []


def test_extractor_parses_key_insights_key(monkeypatch):
    monkeypatch.setattr(
        kx, "invoke_json",
        lambda *a, **k: {"key_insights": ["[台積電](#ticker:2330)展望佳", "降息在即"]},
    )
    out = kx.extract_key_insights_from_markdown("# 摘要\n內容")
    assert out[:2] == ["台積電展望佳", "降息在即"]
    assert len(out) >= 3


def test_extractor_tolerates_alternate_insights_key(monkeypatch):
    monkeypatch.setattr(kx, "invoke_json", lambda *a, **k: {"insights": ["甲", "乙"]})
    out = kx.extract_key_insights_from_markdown("內容")
    assert out[:2] == ["甲", "乙"]
    assert len(out) >= 3


def test_extractor_falls_back_on_llm_failure(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(kx, "invoke_json", boom)
    out = kx.extract_key_insights_from_markdown("# 台股展望\n台積電法說會釋出樂觀展望。")
    assert len(out) >= 3


def test_extractor_falls_back_on_unexpected_shape(monkeypatch):
    monkeypatch.setattr(kx, "invoke_json", lambda *a, **k: {"something_else": 1})
    out = kx.extract_key_insights_from_markdown("# 台股展望\n聯準會降息時點仍是市場焦點。")
    assert len(out) >= 3


# ---------------------------------------------------------------------------
# placeholder-summary guard
# ---------------------------------------------------------------------------

def test_is_placeholder_summary_detects_pipeline_templates():
    placeholder = (
        "# Podcast Episode Summary\n\n"
        "This is a placeholder summary of the podcast episode.\n"
        "*Note: This is a placeholder summary. Actual AI-generated summary coming soon.*"
    )
    assert kx.is_placeholder_summary(placeholder) is True


def test_is_placeholder_summary_false_for_real_zh_summary():
    real = "# 台股展望\n\n台積電法說會釋出樂觀展望，聯準會降息在即。"
    assert kx.is_placeholder_summary(real) is False
    assert kx.is_placeholder_summary("") is False


def test_extractor_skips_placeholder_without_calling_llm(monkeypatch):
    def boom(*a, **k):  # pragma: no cover - should never run
        raise AssertionError("invoke_json must not run on a placeholder summary")

    monkeypatch.setattr(kx, "invoke_json", boom)
    placeholder = "# Episode Summary\nPlaceholder content - real summary generation pending."
    assert kx.extract_key_insights_from_markdown(placeholder) == []


# ---------------------------------------------------------------------------
# extract_key_insights node
# ---------------------------------------------------------------------------

def test_node_reads_markdown_report_and_returns_key_insights(monkeypatch):
    monkeypatch.setattr(kx, "invoke_json", lambda *a, **k: {"key_insights": ["甲", "乙", "丙"]})
    state = {"markdown_report": "# 摘要\n內容", "source": "P", "episode_title": "T"}
    assert kx.extract_key_insights(state) == {"key_insights": ["甲", "乙", "丙"]}


def test_node_empty_markdown_returns_empty_list(monkeypatch):
    monkeypatch.setattr(kx, "invoke_json", lambda *a, **k: {"key_insights": ["x"]})
    assert kx.extract_key_insights({"markdown_report": ""}) == {"key_insights": []}


# ---------------------------------------------------------------------------
# PodcastEpisode Firestore field (merge-safe write)
# ---------------------------------------------------------------------------

def _episode(**kw) -> PodcastEpisode:
    base = dict(
        mp3_url="gs://b/a.mp3", transcript_url="", summary_url="gs://b/s.md",
        summary_image_url="", created_time=datetime(2026, 6, 1),
        episode_title="T", podcast_name="P",
    )
    base.update(kw)
    return PodcastEpisode(**base)


def test_to_firestore_dict_includes_key_insights_when_set():
    d = _episode(key_insights=["甲", "乙", "丙"]).to_firestore_dict()
    assert d["key_insights"] == ["甲", "乙", "丙"]


def test_to_firestore_dict_normalizes_spotify_release_date_and_retracted_at():
    d = _episode(
        spotify_release_date="2026-06-01T08:30:00Z",
        retracted_at=1_781_234_567_000,
    ).to_firestore_dict()
    assert d["spotify_release_date"] == "2026-06-01"
    assert d["retracted_at"] == 1_781_234_567_000


def test_to_firestore_dict_defaults_retracted_at_to_null():
    assert _episode().to_firestore_dict()["retracted_at"] is None


def test_to_firestore_dict_omits_key_insights_when_empty():
    # Omitting the field on update() means an empty extraction can't clobber a
    # previously-populated value.
    assert "key_insights" not in _episode().to_firestore_dict()


def test_firestore_dict_roundtrip_preserves_key_insights():
    d = _episode(key_insights=["甲", "乙"]).to_firestore_dict()
    assert PodcastEpisode.from_firestore_dict(d).key_insights == ["甲", "乙"]
