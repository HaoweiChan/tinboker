"""Regression: the summarize service must carry social_cards from the content-builder
workflow output into its result dict.

It was extracting marp_markdown / ticker_insights / key_insights etc. but silently
dropping social_cards, so the render step had nothing to rasterize and episodes were
written to Firestore without card images (text-only social posts).
"""

from __future__ import annotations

from unittest.mock import patch

from src.summarize.service import SummarizeService

_API_OUT = {
    "markdown_report": "看好 [輝達](#ticker:NVDA) 的後市。",
    "key_insights": ["重點一", "重點二"],
    "social_cards": [
        {"kind": "cover", "title": "封面", "bullets": ["重點一"], "image_url": None},
        {"kind": "theme", "title": "主題A", "bullets": ["細節 [01:23]"], "image_url": None},
    ],
    "related_tickers": ["NVDA"],
}


def test_generate_summary_carries_social_cards():
    with patch("src.summarize.service.is_workflow_api_available", return_value=True), \
         patch("src.summarize.service.analyze_transcript_with_workflow_api", return_value=_API_OUT):
        svc = SummarizeService(use_external=True)
        result = svc.generate_summary_from_text("a transcript", podcast_name="Gooaye", episode_title="EP")
    assert result["social_cards"] == _API_OUT["social_cards"]


def test_generate_summary_social_cards_defaults_empty_when_absent():
    api_out = {k: v for k, v in _API_OUT.items() if k != "social_cards"}
    with patch("src.summarize.service.is_workflow_api_available", return_value=True), \
         patch("src.summarize.service.analyze_transcript_with_workflow_api", return_value=api_out):
        svc = SummarizeService(use_external=True)
        result = svc.generate_summary_from_text("a transcript", podcast_name="Gooaye", episode_title="EP")
    assert result["social_cards"] == []
