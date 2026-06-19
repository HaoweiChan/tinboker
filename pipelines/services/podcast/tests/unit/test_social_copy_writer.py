"""The social_copy_writer turns an episode's SUMMARY into human-tone Threads copy:
one grand-summary post + one comment per summary section (the ``##`` blocks). These
tests lock the section parsing, the prompt wiring, and the no-hardcoded-host rule
(the LLM call itself is stubbed)."""

from __future__ import annotations

import pytest
from src.podcast.content_builder.nodes import social_copy_writer as scw

# A legacy-shaped state: summary has no ``##`` sections, so topics fall back to the
# marp cards. Used to lock the fallback path + the summary-steer passthrough.
_STATE = {
    "source": "Gooaye 股癌",
    "episode_title": "EP671",
    "markdown_report": "# 標題\n\n孟恭談市場百花齊放與功率離散元件。",
    "marp_slides": {
        "title": "股癌",
        "slides": [
            {"heading": "市場百花齊放", "bullet_points": ["被動元件全面相信 [12:06]"], "start_time": 726000},
            {"heading": "功率離散元件", "bullet_points": ["制裁缺口被養出來 [18:05]"], "start_time": 1085000},
        ],
    },
    "key_insights": ["資金最終回流台積電"],
}

# The real shape: a sectioned markdown summary (what build_social_cards leaves in
# ``markdown_report``). Comments must come from these sections' bodies.
_SECTIONED = {
    "source": "財經一路發",
    "episode_title": "美日央行定調",
    "markdown_report": (
        "# 美日央行定調\n\n整體市場偏多，台股創高。\n\n"
        "## 聯準會新主席華許政策 (#time:20760)\n\n華許主張縮表並降息，市場解讀偏鷹。\n\n"
        "## 台灣央行維持利率\n\n台灣央行維持利率不變到年底，房市穩定。"
    ),
    "key_insights": ["華許主張縮表兼降息", "台灣央行維持利率"],
}


def test_summary_sections_parse_and_strip_time_anchor():
    sections = scw._summary_sections(_SECTIONED["markdown_report"])
    assert [s["heading"] for s in sections] == ["聯準會新主席華許政策", "台灣央行維持利率"]  # (#time:..) stripped
    assert "華許主張縮表並降息" in sections[0]["body"]


def test_summary_sections_empty_without_headings():
    assert scw._summary_sections("純文字，沒有任何段落標題。") == []
    assert scw._summary_sections("") == []


def test_summary_overview_is_intro_before_first_section():
    assert scw._summary_overview(_SECTIONED["markdown_report"]).startswith("美日央行定調")
    assert "整體市場偏多" in scw._summary_overview(_SECTIONED["markdown_report"])


def test_build_messages_feeds_section_bodies_not_just_titles():
    user = scw.build_messages(_SECTIONED)[1]["content"]
    assert "財經一路發" in user and "美日央行定調" in user
    # The real paragraph text is fed (the whole point of the fix), not only headings.
    assert "華許主張縮表並降息" in user
    assert "台灣央行維持利率不變到年底" in user
    assert "整體市場偏多" in user  # overview / intro


def test_build_messages_falls_back_to_cards_when_summary_unsectioned():
    user = scw.build_messages(_STATE)[1]["content"]
    assert "市場百花齊放" in user and "功率離散元件" in user  # card headings
    assert "EP671" in user and "Gooaye 股癌" in user
    assert "孟恭" in user  # the input summary still passes through as a steer


def test_prompt_has_no_hardcoded_host_name():
    # Regression: the old prompt example was 「孟恭覺得…」, which leaked the 股癌 host
    # into every show's copy. The prompt must not name any specific host.
    system = scw.load_prompt("social_copy_writer")["system"]
    assert "孟恭" not in system


def test_user_template_fully_formatted():
    content = scw.build_messages(_SECTIONED)[1]["content"]
    for placeholder in ("{sections}", "{overview}", "{source}", "{cards}", "{summary}"):
        assert placeholder not in content


def test_postprocess_normalises_shapes():
    out = scw.postprocess(
        {
            "post": "  整集重點看這 👇  ",
            "comments": [
                {"heading": "華許政策", "text": "  縮表又降息  "},
                {"heading": "央行利率", "text": ""},   # dropped (empty)
                "純文字也能吃",                          # string form
            ],
        },
        _SECTIONED,
    )["social_thread"]
    assert out["post"] == "整集重點看這 👇"
    assert [c["text"] for c in out["comments"]] == ["縮表又降息", "純文字也能吃"]
    assert out["comments"][0]["heading"] == "華許政策"


def test_postprocess_handles_junk():
    assert scw.postprocess(None, _SECTIONED)["social_thread"] == {"post": "", "comments": []}


def test_write_social_copy_invokes_llm(monkeypatch):
    captured = {}

    def fake_invoke(role, messages, schema=None):
        captured["role"] = role
        return {"post": "P", "comments": [{"heading": "h", "text": "t"}]}

    monkeypatch.setattr(scw, "invoke_json", fake_invoke)
    result = scw.write_social_copy(_SECTIONED)
    assert captured["role"] == "social_copy_writer"
    assert result["social_thread"]["post"] == "P"
    assert result["social_thread"]["comments"] == [{"heading": "h", "text": "t"}]
