"""Unit tests for the ticker_insights exporter translation logic.

These tests cover the spec-compliant transformations in
``services/podcast/src/podcast/exporters/ticker_insights.py``:
score → 5-tier label, English → Chinese time horizon, severity normalization,
duplicate-ticker tie-breaking, and tolerance of the legacy LLM wrapper key.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from src.podcast.exporters.ticker_insights import (
    SCHEMA_VERSION,
    build_episode_insight_docs,
    build_insight_doc,
    horizon_to_chinese,
    score_to_label,
)


@pytest.mark.parametrize(
    "score, label",
    [
        (0.95, "STRONG_BULLISH"),
        (0.80, "STRONG_BULLISH"),
        (0.79, "BULLISH"),
        (0.60, "BULLISH"),
        (0.59, "NEUTRAL"),
        (0.40, "NEUTRAL"),
        (0.39, "BEARISH"),
        (0.20, "BEARISH"),
        (0.19, "STRONG_BEARISH"),
        (0.00, "STRONG_BEARISH"),
        (None, "NEUTRAL"),
    ],
)
def test_score_to_label_matches_spec_cutoffs(score, label):
    assert score_to_label(score) == label


@pytest.mark.parametrize(
    "horizon, chinese",
    [
        ("SHORT_TERM", "短期"),
        ("MEDIUM_TERM", "中期"),
        ("LONG_TERM", "長期"),
        ("short_term", "短期"),
        ("", "中期"),
        (None, "中期"),
        ("中期", "中期"),
    ],
)
def test_horizon_to_chinese(horizon, chinese):
    assert horizon_to_chinese(horizon) == chinese


def test_build_insight_doc_carries_locations_and_drops_critical_severity():
    doc = build_insight_doc(
        insight={
            "ticker": "nvda",
            "sentiment": "BULLISH",
            "sentiment_score": 0.78,
            "time_horizon": "MEDIUM_TERM",
            "bluf_thesis": "AI capex strong",
            "reasons": [
                {
                    "title": "capex",
                    "description": "hyperscaler 2026 guidance",
                    "category": "fundamental",
                    "start_time": 1235000,
                    "end_time": 1305000,
                    "start_index": 4210,
                    "end_index": 4480,
                }
            ],
            "risks": [
                {
                    "title": "export controls",
                    "description": "china",
                    "severity": "CRITICAL",  # legacy 4-tier → collapses to HIGH
                    "start_time": 1820000,
                    "end_time": 1880000,
                    "start_index": 5630,
                    "end_index": 5790,
                }
            ],
        },
        episode_id="ep_abc",
        podcaster="股癌",
        podcast_launch_time=datetime(2026, 5, 12, 8, 30, tzinfo=timezone.utc),
    )

    assert doc is not None
    assert doc["schema_version"] == SCHEMA_VERSION
    assert doc["ticker"] == "NVDA"  # canonicalized
    assert doc["time_horizon"] == "中期"
    assert doc["sentiment_label"] == "BULLISH"
    assert doc["sentiment_score"] == 0.78
    assert doc["podcast_launch_time"] == "2026-05-12T08:30:00Z"
    assert doc["risks"][0]["severity"] == "HIGH"  # CRITICAL collapsed
    reason = doc["reasons"][0]
    for key in ("start_time", "end_time", "start_index", "end_index"):
        assert reason[key] is not None


def test_build_insight_doc_returns_none_without_ticker():
    assert (
        build_insight_doc(
            insight={"bluf_thesis": "ghost"},
            episode_id="ep",
            podcaster="x",
            podcast_launch_time=None,
        )
        is None
    )


def test_build_episode_insight_docs_tolerates_legacy_wrapper_key():
    raw = {
        "ticker_recommendations": [  # legacy LLM wrapper inner key
            {"ticker": "NVDA", "sentiment_score": 0.85, "bluf_thesis": "go"},
            {"ticker": "AMD", "sentiment_score": 0.10, "bluf_thesis": "no"},
        ]
    }
    docs = build_episode_insight_docs(
        raw_payload=raw,
        episode_id="ep_1",
        podcaster="股癌",
        podcast_launch_time="2026-05-12T08:30:00Z",
    )
    assert set(docs) == {"NVDA", "AMD"}
    assert docs["NVDA"]["sentiment_label"] == "STRONG_BULLISH"
    assert docs["AMD"]["sentiment_label"] == "STRONG_BEARISH"


def test_build_episode_insight_docs_tiebreaks_by_conviction():
    # Two rows for the same ticker: the one farther from 0.5 wins.
    raw = [
        {"ticker": "NVDA", "sentiment_score": 0.55, "bluf_thesis": "soft bullish"},
        {"ticker": "NVDA", "sentiment_score": 0.95, "bluf_thesis": "strong bullish"},
    ]
    docs = build_episode_insight_docs(
        raw_payload=raw,
        episode_id="ep_1",
        podcaster="x",
        podcast_launch_time=None,
    )
    assert docs["NVDA"]["bluf_thesis"] == "strong bullish"
