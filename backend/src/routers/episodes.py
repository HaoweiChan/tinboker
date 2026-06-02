"""
Episodes API router for cross-podcast episode queries
"""
from fastapi import APIRouter, HTTPException, Path, Query
from typing import Optional
from src.services.podcast import PodcastService
from src.services.translation_discovery import schedule_ticker_discovery
from src.cache.cdn_cache import cdn_cache_podcast

router = APIRouter(prefix="/api/episodes", tags=["episodes"])

# Initialize service
podcast_service = PodcastService()


@router.get("/recent")
@cdn_cache_podcast
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


