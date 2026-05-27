"""
Ticker insights router.

Firestore-backed replacement for /api/recommendations/*.
Contract: docs/firestore-contract.md §§ 4–5.
"""
from typing import List, Optional

from fastapi import APIRouter, Query

from src.cache.cdn_cache import cdn_cache_trending
from src.services.insight_service import InsightService

router = APIRouter(prefix="/api/ticker-insights", tags=["ticker-insights"])
insight_service = InsightService()


@router.get("/trending")
@cdn_cache_trending
async def get_trending(
    days: int = Query(default=30, description="Rolling window: 30 | 90 | 0 (all-time)"),
    limit: int = Query(default=100, ge=1, le=200, description="Max tickers to return"),
) -> List[dict]:
    """
    Trending tickers from Firestore trending_tickers/*.

    Replaces /api/recommendations/buzz. Returns TickerTrending[] per spec § 5.3:
    `{ ticker, count, sentiment_label, last_mentioned }`.

    CDN Cache: 5 minutes.
    """
    if days not in (0, 30, 90):
        days = 30
    return await insight_service.get_trending(days=days, limit=limit)


@router.get("/by-ticker/{ticker}")
@cdn_cache_trending
async def get_by_ticker(
    ticker: str,
    start_date: Optional[str] = Query(default=None, description="ISO date (YYYY-MM-DD); default: today − 7 days"),
    end_date: Optional[str] = Query(default=None, description="ISO date (YYYY-MM-DD); default: today"),
) -> List[dict]:
    """
    TickerInsight[] for the given ticker in the date range. Default: last 7 days.

    Replaces /api/recommendations/by-ticker/{ticker}. Spec § 4.3 / § 4.4.
    Reads from ticker_insights/{episode_id}/tickers/{ticker} (collection group).

    CDN Cache: 5 minutes.
    """
    return await insight_service.get_by_ticker(
        ticker=ticker,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("/by-podcaster/{podcaster_name}")
@cdn_cache_trending
async def get_by_podcaster(
    podcaster_name: str,
    start_date: Optional[str] = Query(default=None, description="ISO date (YYYY-MM-DD); default: today − 7 days"),
    end_date: Optional[str] = Query(default=None, description="ISO date (YYYY-MM-DD); default: today"),
) -> List[dict]:
    """
    TickerInsight[] from the given podcaster in the date range. Default: last 7 days.

    Replaces /api/recommendations/by-podcaster/{name}. Spec § 4.3 / § 4.4.

    CDN Cache: 5 minutes.
    """
    return await insight_service.get_by_podcaster(
        podcaster=podcaster_name,
        start_date=start_date,
        end_date=end_date,
    )
