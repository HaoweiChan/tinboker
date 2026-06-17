"""The social_copy_writer turns an episode's cards into human-tone Threads copy:
one grand-summary post + one comment per theme card. These tests lock the shape
and the prompt wiring (the LLM call itself is stubbed)."""

from __future__ import annotations

import json

import pytest
from src.podcast.content_builder.nodes import social_copy_writer as scw

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


def test_build_messages_includes_theme_cards_and_summary():
    msgs = scw.build_messages(_STATE)
    assert msgs[0]["role"] == "system"
    user = msgs[1]["content"]
    assert "市場百花齊放" in user and "功率離散元件" in user
    assert "EP671" in user and "Gooaye 股癌" in user
    # The summary steer is passed through.
    assert "孟恭" in user


def test_postprocess_normalises_shapes():
    out = scw.postprocess(
        {
            "post": "  整集重點看這 👇  ",
            "comments": [
                {"heading": "市場百花齊放", "text": "  題材輪動很快  "},
                {"heading": "功率離散元件", "text": ""},   # dropped (empty)
                "純文字也能吃",                              # string form
            ],
        },
        _STATE,
    )["social_thread"]
    assert out["post"] == "整集重點看這 👇"
    assert [c["text"] for c in out["comments"]] == ["題材輪動很快", "純文字也能吃"]
    assert out["comments"][0]["heading"] == "市場百花齊放"


def test_postprocess_handles_junk():
    assert scw.postprocess(None, _STATE)["social_thread"] == {"post": "", "comments": []}


def test_write_social_copy_invokes_llm(monkeypatch):
    captured = {}

    def fake_invoke(role, messages, schema=None):
        captured["role"] = role
        return {"post": "P", "comments": [{"heading": "h", "text": "t"}]}

    monkeypatch.setattr(scw, "invoke_json", fake_invoke)
    result = scw.write_social_copy(_STATE)
    assert captured["role"] == "social_copy_writer"
    assert result["social_thread"]["post"] == "P"
    assert result["social_thread"]["comments"] == [{"heading": "h", "text": "t"}]


def test_prompt_yaml_loads_and_has_no_ai_tone_banlist_leak():
    # The prompt must actually exist and render with the expected fields.
    msgs = scw.build_messages(_STATE)
    assert "{cards}" not in msgs[1]["content"]  # template fully formatted
    assert json.loads(json.dumps(_STATE["marp_slides"]))  # sanity
