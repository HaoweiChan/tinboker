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
    _iso_utc,
    build_episode_insight_docs,
    build_insight_doc,
    episode_publish_time,
    horizon_to_chinese,
    is_boilerplate_thesis,
    score_to_label,
)


def test_is_boilerplate_thesis_flags_templated_filler():
    assert is_boilerplate_thesis("台積電 具備良好的成長動能，在目前產業趨勢下值得長期追蹤。")
    assert is_boilerplate_thesis("NVDA當前面臨的產業環境具有挑戰，但長期結構性優勢仍在。")
    assert is_boilerplate_thesis("X近期表現受到市場關注，節目分析其短期動能與中長期基本面展望。")
    # A real, specific thesis must NOT be flagged.
    assert not is_boilerplate_thesis("台積電法說會前，台股多頭格局不變，挑戰前高機會大，但需留意結算風險。")
    assert not is_boilerplate_thesis(None)
    assert not is_boilerplate_thesis("")


def test_build_insight_doc_drops_boilerplate_thesis():
    doc = build_insight_doc(
        insight={"ticker": "NVDA", "bluf_thesis": "NVDA 具備良好的成長動能，在目前產業趨勢下值得長期追蹤。"},
        episode_id="e1", podcaster="P", podcast_launch_time=0,
    )
    assert doc is None


def test_iso_utc_coerces_epoch_ms():
    # Regression: an epoch-ms int (released_at_ms / created_time) used to fall
    # through to datetime.now(), stamping every backfilled insight with the run
    # date. It must now resolve to the real timestamp.
    ms = int(datetime(2025, 12, 23, 14, 0, tzinfo=timezone.utc).timestamp() * 1000)
    assert _iso_utc(ms) == "2025-12-23T14:00:00Z"
    # ISO strings and datetimes still pass through correctly.
    assert _iso_utc("2026-06-13T05:00:00Z") == "2026-06-13T05:00:00Z"
    assert _iso_utc(datetime(2026, 1, 2, tzinfo=timezone.utc)) == "2026-01-02T00:00:00Z"


def test_episode_publish_time_prefers_real_release_over_ingest():
    """The resolver every dict-based writer uses to stamp ``podcast_launch_time``.

    ``released_at_ms`` is the true mention date; ``created_time`` (ingest) is the last
    resort. Stamping insights with ``created_time`` collapses a whole back-catalogue
    onto the reprocessing date on /picks — the regression this guards.
    """
    # released_at_ms wins even when a (different) created_time is present.
    assert episode_publish_time(
        {"released_at_ms": 1700000000000, "created_time": "2026-06-17T20:22:12Z"}
    ) == 1700000000000
    # Spotify release datetime is preferred over ingest time.
    assert episode_publish_time(
        {"spotify_metadata": {"release_datetime": "2025-01-02T00:00:00Z"},
         "created_time": "2026-06-17T20:22:12Z"}
    ) == "2025-01-02T00:00:00Z"
    # spotify_release_date before created_time.
    assert episode_publish_time(
        {"spotify_release_date": "2025-03-04", "created_time": "2026-06-17T20:22:12Z"}
    ) == "2025-03-04"
    # created_time only as the last resort.
    assert episode_publish_time(
        {"created_time": "2026-06-17T20:22:12Z"}
    ) == "2026-06-17T20:22:12Z"
    # A zero/empty released_at_ms is ignored (must not stamp epoch 0), and an empty
    # spotify_metadata dict falls through.
    assert episode_publish_time({"released_at_ms": 0, "created_time": "x"}) == "x"
    assert episode_publish_time({"spotify_metadata": {}, "created_time": "x"}) == "x"
    # Nothing usable at all → None (the exporter's _iso_utc then stamps now()).
    assert episode_publish_time({}) is None


def test_build_insight_doc_uses_epoch_ms_launch_time():
    ms = int(datetime(2025, 12, 23, tzinfo=timezone.utc).timestamp() * 1000)
    doc = build_insight_doc(
        insight={"ticker": "NVDA", "sentiment_score": 0.7},
        episode_id="e1",
        podcaster="P",
        podcast_launch_time=ms,
    )
    assert doc["podcast_launch_time"] == "2025-12-23T00:00:00Z"


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
