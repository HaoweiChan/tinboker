from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.routers import stock as stock_router
from src.services.trending import TrendingService


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return self._rows


class _FakeDb:
    def __init__(self, rows):
        self._rows = rows

    def query(self, _model):
        return _FakeQuery(self._rows)


@pytest.mark.asyncio
async def test_batch_summary_uses_translation_table_without_price_fetch():
    rows = [
        SimpleNamespace(
            ticker="2330",
            market="TW",
            name_en="Taiwan Semiconductor Manufacturing",
            name_zh_tw="台積電",
            brand_color="#E60012",
            name_preference="auto",
        ),
        SimpleNamespace(
            ticker="2454",
            market="TW",
            name_en="MediaTek",
            name_zh_tw="聯發科",
            brand_color="#F58220",
            name_preference="auto",
        ),
    ]

    with patch.object(
        stock_router.stock_service,
        "get_stock_basic_info_async",
        side_effect=AssertionError("batch-summary must not call live price APIs"),
    ):
        result = await stock_router.get_batch_summary(
            tickers="2330,2454.TW",
            db=_FakeDb(rows),
        )

    assert result == [
        {"ticker": "2330", "name": "台積電", "market": "TW", "brand_color": "#E60012"},
        {"ticker": "2454.TW", "name": "聯發科", "market": "TW", "brand_color": "#F58220"},
    ]


@pytest.mark.asyncio
@patch("src.services.trending.cache_get", new_callable=AsyncMock, return_value=None)
@patch("src.services.trending.cache_set", new_callable=AsyncMock)
async def test_recent_buzz_ticker_filter_returns_matching_count_and_sentiment(_cache_set, _cache_get):
    now = 1_800_000_000_000
    episodes = [
        SimpleNamespace(id="ep-bear-1", released_at_ms=now, created_time=now, related_tickers=["2454"]),
        SimpleNamespace(id="ep-bear-2", released_at_ms=now - 1_000, created_time=now - 1_000, related_tickers=["2454", "2330"]),
        SimpleNamespace(id="ep-bull", released_at_ms=now - 2_000, created_time=now - 2_000, related_tickers=["2330"]),
    ]
    podcast_service = SimpleNamespace(get_recent_episodes=AsyncMock(return_value=episodes))
    service = TrendingService(podcast_service=podcast_service)
    service._get_translations_batch = AsyncMock(return_value={"2454": "聯發科"})

    class _FakeSentimentService:
        async def get_sentiments(self, episode_ids):
            return {
                "ep-bear-1": {"2454": "BEARISH"},
                "ep-bear-2": {"2454": "BEARISH", "2330": "BULLISH"},
                "ep-bull": {"2330": "BULLISH"},
            }

    with patch("src.services.episode_sentiments.EpisodeSentimentService", _FakeSentimentService):
        result = await service.get_recent_buzz(days=30, limit=1, ticker="2454.TW")

    assert result["tickers"] == [
        {
            "ticker": "2454",
            "name": "聯發科",
            "count": 2,
            "sentiment_label": "BEARISH",
            "sentiment_counts": {"bull": 0, "neutral": 0, "bear": 2},
            "last_mentioned": now,
        }
    ]
