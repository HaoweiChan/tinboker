"""
Ticker insights router.

Firestore-backed replacement for /api/recommendations/*.
Contract: docs/firestore-contract.md §§ 4–5.
"""
import asyncio
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.cache.cdn_cache import cdn_cache_trending
from src.database.postgres import get_session
from src.routers.stock import WINDOW_DAYS, _window_returns
from src.services.insight_service import InsightService

router = APIRouter(prefix="/api/ticker-insights", tags=["ticker-insights"])
insight_service = InsightService()

# Sentiment labels grouped by direction for hit-rate scoring (spec § 4.2).
_BULLISH_LABELS = {"STRONG_BULLISH", "BULLISH"}
_BEARISH_LABELS = {"STRONG_BEARISH", "BEARISH"}


def _iso_to_ms(iso_str: str) -> Optional[int]:
    """Parse an ISO 8601 timestamp to Unix ms; None when unparseable."""
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except (ValueError, TypeError):
        return None


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


@router.get("/podcaster-scorecard/{podcaster_name}")
@cdn_cache_trending
async def get_podcaster_scorecard(
    podcaster_name: str,
    window: int = Query(default=30, description="Scoring window in days: 7 | 30 | 90"),
    start_date: Optional[str] = Query(default=None, description="ISO date; default: today − 180 days"),
    end_date: Optional[str] = Query(default=None, description="ISO date; default: today"),
    db: Session = Depends(get_session),
) -> dict:
    """命中率 (hit-rate) for a podcaster's picks over a forward window.

    A pick is *scored* only once its window has fully elapsed. A *hit* = the price
    moved in the direction of the host's sentiment (bullish & up, or bearish & down).
    Neutral picks are excluded from scoring. Returns the aggregate stat only; the
    per-pick feed is rendered client-side via /api/stocks/batch-prices-windows.

    CDN Cache: 5 minutes.
    """
    if window not in WINDOW_DAYS:
        window = 30
    # Wide default range so there's enough completed-window history to score.
    start = start_date or (date.today() - timedelta(days=180)).isoformat()
    end = end_date or date.today().isoformat()

    picks = await insight_service.get_by_podcaster(
        podcaster=podcaster_name, start_date=start, end_date=end,
    )

    # Keep only directional picks with a parseable mention date.
    scored: List[tuple[str, int, int]] = []  # (ticker, reference_ms, direction)
    for p in picks:
        label = p.get("sentiment_label")
        direction = 1 if label in _BULLISH_LABELS else (-1 if label in _BEARISH_LABELS else 0)
        if direction == 0:
            continue
        ms = _iso_to_ms(p.get("podcast_launch_time") or "")
        ticker = p.get("ticker")
        if ms is None or not ticker:
            continue
        scored.append((ticker, ms, direction))

    async def _safe_window(ticker: str, ms: int) -> dict:
        try:
            return await asyncio.wait_for(_window_returns(ticker, ms, None, db), timeout=15)
        except (asyncio.TimeoutError, Exception):
            return {}

    window_results = await asyncio.gather(*[_safe_window(t, ms) for t, ms, _ in scored])

    field = f"d{window}"
    n_hit = 0
    returns: List[float] = []
    for (_, _, direction), wr in zip(scored, window_results):
        ret = wr.get(field)
        if ret is None:
            continue  # window not complete / no price data → unscored
        returns.append(ret)
        if (direction > 0 and ret > 0) or (direction < 0 and ret < 0):
            n_hit += 1

    n_scored = len(returns)
    return {
        "podcaster": podcaster_name,
        "window": window,
        "n_picks": len(picks),
        "n_scored": n_scored,
        "n_hit": n_hit,
        "hit_rate": round(n_hit / n_scored, 4) if n_scored else None,
        "avg_return": round(sum(returns) / len(returns), 2) if returns else None,
    }
