"""
Episodes API router for cross-podcast episode queries
"""
from fastapi import APIRouter, HTTPException, Path, Query, Response
from pydantic import BaseModel, Field
from typing import Optional
from src.services.podcast import EPISODE_DETAIL_CONTENT_FIELDS, PodcastService, episode_content_incomplete
from src.services.translation_discovery import schedule_ticker_discovery
from src.services.episode_sentiments import EpisodeSentimentService
from src.services.trending import TrendingService
from src.cache.cdn_cache import cdn_cached, cdn_cache_podcast, cdn_cache_trending

router = APIRouter(prefix="/api/episodes", tags=["episodes"])
CACHE_CONTROL_READ = "public, max-age=300, s-maxage=3600"

# Initialize services
podcast_service = PodcastService()
sentiment_service = EpisodeSentimentService()
trending_service = TrendingService(podcast_service=podcast_service)


class TickerSentimentsRequest(BaseModel):
    episode_ids: list[str] = Field(default_factory=list, max_length=80)


@router.get("/recent")
@cdn_cached(s_maxage=600, max_age=120, stale=300)
async def get_recent_episodes(
    limit: int = Query(default=20, ge=1, le=200, description="Maximum number of episodes to return (1-200)"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    podcast_name: Optional[str] = Query(default=None, description="Optional filter by podcast name"),
    include_content: bool = Query(default=False, description="Include heavy content fields (transcript, summary)")
):
    """
    Get recent episodes across all podcasts, sorted by created_time descending
    
    Query params:
    - limit: Maximum number of episodes to return (default: 20, max: 200)
    - offset: Pagination offset
    - podcast_name: Optional filter by podcast name
    
    CDN Cache: 30 minutes
    """
    try:
        episodes = await podcast_service.get_recent_episodes(
            limit=limit,
            offset=offset,
            podcast_name=podcast_name,
            enrich_content=include_content
        )

        # On-ingest discovery: ensure any newly-mentioned ticker gets a pending
        # stub row (non-blocking, throttled — see translation_discovery).
        schedule_ticker_discovery(episodes)

        # Calculate total and hasMore (we'd need total count for accurate hasMore)
        # For now, hasMore is true if we got exactly the limit
        has_more = len(episodes) == limit
        
        return {
            "episodes": episodes,
            "total": len(episodes),  # This is approximate without full count
            "hasMore": has_more
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching recent episodes: {str(e)}")


@router.post("/ticker-sentiments")
async def get_ticker_sentiments(body: TickerSentimentsRequest):
    """Per-(episode, ticker) sentiment for episode-card chips.

    POST (not GET) because episode ids are long unicode title strings. Returns
    `{ episode_id: { TICKER: "BULLISH"|"BEARISH"|"NEUTRAL" } }`. Maps are extracted
    from each episode's ticker_insights file and cached in Redis, so this is
    cheap after the first warm.
    """
    try:
        return await sentiment_service.get_sentiments(body.episode_ids)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching ticker sentiments: {str(e)}")


@router.get("/buzz")
@cdn_cache_trending
async def get_recent_buzz(
    days: int = Query(default=30, ge=1, le=90, description="Rolling window in days"),
    limit: int = Query(default=10, ge=1, le=200, description="Max tickers to return (rail uses 10; StockIndex uses 200)"),
):
    """Genuine 'what people are discussing lately' from the recent launch feed.

    Returns {tickers: [{ticker, count, sentiment_label, last_mentioned}], distinct_count,
    episode_count} computed from the recent (zh-TW-scoped, recency-filtered) episodes —
    NOT the all-time agents-precomputed trending_tickers. Powers the homepage right rail
    and the /stock index (所有個股) — both reflect real recent mention counts.
    """
    try:
        return await trending_service.get_recent_buzz(days=days, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching recent buzz: {str(e)}")


@router.get("/by-ticker/{ticker}")
@cdn_cache_podcast
async def get_episodes_by_ticker(
    ticker: str = Path(..., description="Stock ticker symbol"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum number of episodes to return (1-200)"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    include_content: bool = Query(default=False, description="Include heavy content fields (transcript, summary)")
):
    """
    Get episodes that mention a specific stock ticker
    
    Path params:
    - ticker: Stock ticker symbol (e.g., "NVDA", "AAPL")
    
    Query params:
    - limit: Maximum number of episodes to return (default: 50, max: 200)
    - offset: Pagination offset
    
    CDN Cache: 30 minutes
    """
    try:
        episodes = await podcast_service.get_episodes_by_ticker(
            ticker=ticker,
            limit=limit,
            offset=offset,
            enrich_content=include_content
        )
        
        return {
            "ticker": ticker.upper(),
            "episodes": episodes,
            "total": len(episodes)  # This is approximate without full count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching episodes by ticker: {str(e)}")


# NOTE: keep this LAST — a single-segment dynamic path must be registered after the
# static routes (/recent, /by-ticker/..., /ticker-sentiments) so they match first.
@router.get("/{episode_id}")
@cdn_cache_podcast
async def get_episode_by_id(
    response: Response,
    episode_id: str = Path(..., description="Episode ID"),
    include_heavy_content: bool = Query(
        default=False,
        description="Also hydrate transcript/ticker blobs. False returns the fast episode-detail payload.",
    ),
):
    """
    Get a single episode by ID alone, without the podcast name.

    Supports deep links / refreshes of /episode/{id} where the show name is not
    known client-side. Returns the same full Episode payload as
    GET /api/podcast/{podcast_name}/episodes/{episode_id}.

    CDN Cache: 30 minutes
    """
    try:
        fields = None if include_heavy_content else EPISODE_DETAIL_CONTENT_FIELDS
        episode = await podcast_service.get_episode_by_id_only(
            episode_id, content_fields=fields,
        )
        if not episode:
            raise HTTPException(status_code=404, detail=f"Episode '{episode_id}' not found")
        if episode_content_incomplete(episode, content_fields=fields):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        else:
            response.headers["Cache-Control"] = CACHE_CONTROL_READ
        return episode
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching episode: {str(e)}")
