"""The on-page episode deck (``convert_marp``) must render the SAME branded card
design as the PNG social cards, with the theme inlined so the browser's marp-core
can render it. These tests lock that contract (it silently diverged once before)."""

from __future__ import annotations

import re

from src.podcast.content_builder.card_deck import ACCENT_YELLOW
from src.podcast.content_builder.nodes.marp_converter import convert_marp, convert_marp_ticker

_MARP_SLIDES = {
    "title": "股癌",
    "slides": [
        {
            "heading": "Computex 整體觀察",
            "bullet_points": [
                "一般民眾大量湧入，業內人抱怨無效溝通 [01:07]",
                "黃仁勳已是不折不扣的超級巨星 [02:44]",
            ],
            "start_time": 67000,
        },
        {
            "heading": "Enterprise AI 硬體",
            "bullet_points": ["超級電容實物現身，ASP 漲近 100 倍 [06:40]"],
            "start_time": 400000,
        },
    ],
}

_STATE = {
    "marp_slides": _MARP_SLIDES,
    "key_insights": ["黃仁勳把 Computex 變成自己的演唱會"],
    "episode_title": "EP671",
    "source": "股癌",
    "released_at_ms": 1781677762000,
}


def test_convert_marp_emits_inline_card_deck_design():
    md = convert_marp(_STATE)["marp_markdown"]
    # Exactly one inline <style> (kept small; the frontend hoists it per slide).
    assert md.count("<style>") == 1 and md.count("</style>") == 1
    # The brand-yellow accent + the card-deck visual markers are present.
    assert ACCENT_YELLOW[0] in md
    assert 'content: "▍"' in md          # the yellow bullet marker
    assert "section.cover" in md and "section.theme" in md
    # Cover + one slide per (bulleted) theme, via spot-directive classes.
    assert "_class: cover" in md
    assert md.count("_class: theme") == 2
    # Square deck must use the size-declaring theme + 1:1 size so marp-core emits
    # a 1080² SVG viewBox (else it letterboxes inside the square frame).
    assert "theme: tinboker-cards" in md
    assert re.search(r"size:\s*1:1", md)


def test_convert_marp_has_no_doubled_separators():
    md = convert_marp(_STATE)["marp_markdown"]
    # The old converter produced `---\n\n---`, i.e. blank slides between content.
    assert "---\n\n---" not in md


def test_convert_marp_preserves_per_bullet_timestamps():
    md = convert_marp(_STATE)["marp_markdown"]
    # Per-point [MM:SS] stamps are wrapped (not doubled with the slide stamp).
    assert md.count('class="ts"') == 3
    # The slide-level 67000ms -> [01:07] is not appended a second time.
    assert md.count("[01:07]") == 1


def test_convert_marp_empty_when_no_content():
    assert convert_marp({"marp_slides": {}})["marp_markdown"] == ""


def test_convert_marp_ticker_builds_deterministic_deck():
    # The ticker deck is built straight from ticker_insights (no LLM slides) —
    # an overview grid + focus-analysis cards, blue accent, wide size.
    md = convert_marp_ticker({
        "ticker_insights": {"ticker_insights": [
            {"ticker": "2330", "sentiment_score": 0.85,
             "risks": [{"severity": "MEDIUM"}],
             "reasons": [{"title": "AI 需求", "description": "資料中心拉貨。", "start_time": 10000}]},
        ]},
        "source": "股癌",
    })["ticker_marp_markdown"]
    assert "#5b8dff" in md                          # ACCENT_BLUE
    assert "theme: tinboker-cards" in md
    assert re.search(r"size:\s*wide", md)           # named size the theme declares
    assert "width: 1240px; height: 780px;" in md
    assert "_class: ticker-table" in md and "_class: analysis" in md
    assert "標的聚焦：台積電 2330" in md             # registry-resolved name


def test_convert_marp_ticker_empty_when_no_insights():
    assert convert_marp_ticker({"ticker_insights": {}})["ticker_marp_markdown"] == ""
