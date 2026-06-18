from __future__ import annotations

from datetime import datetime, timezone

from scripts.backfill_ticker_insights_from_postgres import (
    build_episode_docs_from_legacy_rows,
    normalize_legacy_score,
)


def test_normalize_legacy_score_accepts_legacy_ranges_and_sentiment_fallback():
    assert normalize_legacy_score(0.82) == 0.82
    assert normalize_legacy_score(8.2) == 0.82
    assert normalize_legacy_score(82) == 0.82
    assert normalize_legacy_score("bad", "bearish") == 0.3
    assert normalize_legacy_score(None, "STRONG_BULLISH") == 0.9


def test_build_episode_docs_quantizes_score_and_includes_market_namespace():
    rows = [
        {
            "episode_id": "ep_1",
            "podcaster": "股癌",
            "podcast_launch_time": datetime(2026, 5, 12, 8, 30, tzinfo=timezone.utc),
            "ticker": "2330",
            "bluf_thesis": "先進製程需求強",
            "time_horizon": "LONG_TERM",
            "sentiment_score": 8.0,
            "reasons": [{"title": "AI", "description": "需求延續"}],
            "risks": [{"title": "匯率", "description": "台幣波動", "severity": "LOW"}],
            "created_at": datetime(2026, 5, 12, 9, 0, tzinfo=timezone.utc),
        },
        {
            "episode_id": "ep_1",
            "podcaster": "股癌",
            "podcast_launch_time": datetime(2026, 5, 12, 8, 30, tzinfo=timezone.utc),
            "ticker": "nvda",
            "bluf_thesis": "AI capex remains strong",
            "time_horizon": "MEDIUM_TERM",
            "sentiment_score": 0.79,
            "reasons": [],
            "risks": [],
        },
    ]

    episode_docs, skipped = build_episode_docs_from_legacy_rows(rows)

    assert skipped == []
    assert set(episode_docs["ep_1"]) == {"2330", "NVDA"}
    tw_doc = episode_docs["ep_1"]["2330"]
    us_doc = episode_docs["ep_1"]["NVDA"]
    assert tw_doc["market"] == "TW"
    assert tw_doc["sentiment_score"] == 0.8
    assert tw_doc["sentiment_label"] == "STRONG_BULLISH"
    assert tw_doc["time_horizon"] == "長期"
    assert tw_doc["created_at"] == "2026-05-12T09:00:00Z"
    assert us_doc["market"] == "US"
    assert us_doc["sentiment_label"] == "BULLISH"


def test_build_episode_docs_skips_unkeyable_rows_and_tiebreaks_duplicates():
    rows = [
        {
            "episode_id": "ep_2",
            "ticker": "NVDA",
            "sentiment_score": 0.55,
            "bluf_thesis": "soft bullish",
        },
        {
            "episode_id": "ep_2",
            "ticker": "NVDA",
            "sentiment_score": 0.95,
            "bluf_thesis": "strong bullish",
        },
        {
            "episode_id": "",
            "ticker": "AMD",
            "sentiment_score": 0.7,
        },
        {
            "episode_id": "ep_3",
            "ticker": "not-a-ticker",
            "sentiment_score": 0.7,
        },
    ]

    episode_docs, skipped = build_episode_docs_from_legacy_rows(rows)

    assert episode_docs["ep_2"]["NVDA"]["bluf_thesis"] == "strong bullish"
    assert len(skipped) == 2
