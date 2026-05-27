"""
Recommendation API: by-ticker, by-podcaster, and buzz.
Data comes from podcast_db (prepared elsewhere). Default timeframe: today − 7 days → today.

NOTE: /api/recommendations/buzz is deprecated as of 2026-05-14. Use
/api/ticker-insights/trending instead. Spec: docs/firestore-contract.md § 4.4.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from src.cache.cdn_cache import cdn_cache_trending
from src.services.recommendation_service import RecommendationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])
recommendation_service = RecommendationService()


_DEPRECATION_HEADERS = {
    "Deprecation": "true",
    "Link": '</api/ticker-insights/>; rel="successor-version"',
}


@router.get("/by-ticker/{ticker}", deprecated=True)
@cdn_cache_trending
async def get_recommendations_by_ticker(
    ticker: str,
    start_date: Optional[str] = Query(default=None, description="ISO date (YYYY-MM-DD); default: today − 7 days"),
    end_date: Optional[str] = Query(default=None, description="ISO date (YYYY-MM-DD); default: today"),
) -> JSONResponse:
    """
    DEPRECATED — use GET /api/ticker-insights/by-ticker/{ticker}.

    Returns the legacy Postgres-backed recommendation shape. Soft-deprecated
    per spec § 4.4; will be removed one release after the new endpoint soaks
    (Phase B6).

    CDN Cache: 5 minutes
    """
    logger.warning(
        "Deprecated endpoint hit: /api/recommendations/by-ticker/%s — clients should migrate to /api/ticker-insights/by-ticker/%s",
        ticker,
        ticker,
    )
    data = await recommendation_service.get_recommendations_by_ticker(
        ticker=ticker,
        start_date=start_date,
        end_date=end_date,
    )
    return JSONResponse(content=data, headers=_DEPRECATION_HEADERS)


@router.get("/by-podcaster/{podcaster_name}", deprecated=True)
@cdn_cache_trending
async def get_recommendations_by_podcaster(
    podcaster_name: str,
    start_date: Optional[str] = Query(default=None, description="ISO date (YYYY-MM-DD); default: today − 7 days"),
    end_date: Optional[str] = Query(default=None, description="ISO date (YYYY-MM-DD); default: today"),
    podcast_slug: Optional[str] = Query(default=None, description="Optional slug; also matches episode_id ILIKE %slug%"),
) -> JSONResponse:
    """
    DEPRECATED — use GET /api/ticker-insights/by-podcaster/{name}.

    Returns the legacy Postgres-backed recommendation shape. Soft-deprecated
    per spec § 4.4; will be removed one release after the new endpoint soaks
    (Phase B6).

    CDN Cache: 5 minutes
    """
    logger.warning(
        "Deprecated endpoint hit: /api/recommendations/by-podcaster/%s — clients should migrate to /api/ticker-insights/by-podcaster/%s",
        podcaster_name,
        podcaster_name,
    )
    data = await recommendation_service.get_recommendations_by_podcaster(
        podcaster=podcaster_name,
        start_date=start_date,
        end_date=end_date,
        podcast_slug=podcast_slug,
    )
    return JSONResponse(content=data, headers=_DEPRECATION_HEADERS)


@router.get("/buzz", deprecated=True)
@cdn_cache_trending
async def get_buzz(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to look back"),
    limit: int = Query(default=10, ge=1, le=100, description="Max number of tickers to return"),
) -> JSONResponse:
    """
    DEPRECATED — use GET /api/ticker-insights/trending.

    Returns ticker, count, sentiment_score (avg), last_mentioned from the
    Postgres `ticker_insights` table. Soft-deprecated per spec § 4.4:
    response carries `Deprecation: true` and a successor-version `Link`
    header; this path will be removed one release after the new endpoint
    soaks (Phase B6).

    CDN Cache: 5 minutes
    """
    logger.warning(
        "Deprecated endpoint hit: /api/recommendations/buzz — clients should migrate to /api/ticker-insights/trending"
    )
    data = await recommendation_service.get_most_discussed_tickers(
        days=days,
        limit=limit,
    )
    # Returning JSONResponse here lets the cdn_cache_trending decorator
    # preserve our headers (its non-Response branch builds a fresh response
    # and drops anything we'd set via dependency injection).
    return JSONResponse(
        content=data,
        headers={
            "Deprecation": "true",
            "Link": '</api/ticker-insights/trending>; rel="successor-version"',
        },
    )
