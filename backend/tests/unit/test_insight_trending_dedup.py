"""Trending dedup: legacy `trending_tickers/{ticker}` and new `{ticker}.{market}`
docs can coexist (agents changed the doc-id scheme); get_trending must not
double-list the same ticker — it keeps the higher-count (then most recent) row.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.insight_service import InsightService


def _doc(ticker, count, last):
    return {
        "ticker": ticker,
        "count_30d": count, "count_90d": count, "count_all_time": count,
        "sentiment_label": "BULLISH",
        "last_mentioned": last,
    }


@pytest.mark.asyncio
async def test_get_trending_dedups_same_ticker_keeping_higher_count():
    svc = InsightService.__new__(InsightService)  # bypass __init__ (no Firestore connect)
    svc._fs = MagicMock()
    svc._fs.get_all_documents = MagicMock(return_value=[
        _doc("2330", 3, "2026-06-01T00:00:00Z"),   # legacy trending_tickers/2330
        _doc("2330", 7, "2026-06-10T00:00:00Z"),   # new trending_tickers/2330.TW
        _doc("NVDA", 5, "2026-06-05T00:00:00Z"),
    ])

    with (
        patch("src.services.insight_service.cache_get", new=AsyncMock(return_value=None)),
        patch("src.services.insight_service.cache_set", new=AsyncMock()),
    ):
        rows = await svc.get_trending(days=30, limit=100)

    tickers = [r["ticker"] for r in rows]
    assert tickers.count("2330") == 1, f"2330 double-listed: {tickers}"
    assert next(r for r in rows if r["ticker"] == "2330")["count"] == 7
    assert "NVDA" in tickers
