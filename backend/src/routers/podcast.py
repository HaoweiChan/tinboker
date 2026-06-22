"""
Podcast API router
"""
from fastapi import APIRouter, HTTPException, Path, Query, Body, BackgroundTasks, Response, Depends
from fastapi.responses import RedirectResponse
from typing import List, Optional
from src.services.podcast import (
    EPISODE_DETAIL_CONTENT_FIELDS,
    PodcastService,
    episode_content_incomplete,
    poll_regeneration_status,
)
from src.models.podcast import Podcast, Episode
from src.auth.admin_auth import get_content_write_access, AdminAccess
from src.config import settings
from src.cache.cdn_cache import cdn_cache_podcast
import httpx
import logging

router = APIRouter(prefix="/api/podcast", tags=["podcast"])

# Cache control settings for Cloudflare edge caching
# s-maxage: tells Cloudflare how long to cache at the edge
# max-age: tells browsers how long to cache locally
CACHE_CONTROL_READ = "public, max-age=300, s-maxage=3600"  # 5min browser, 1hr edge
CACHE_CONTROL_LIST = "public, max-age=60, s-maxage=1800"   # 1min browser, 30min edge

# Initialize service
podcast_service = PodcastService()
logger = logging.getLogger(__name__)


@router.get("", response_model=List[Podcast])
@cdn_cache_podcast
async def get_sorted_podcasts(
    response: Response,
    sort_by: str = Query(default="name", description="Sort field (name, episode_count, created_at, updated_at, popularity)"),
    order: str = Query(default="asc", description="Sort order (asc, desc)"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum number of podcasts to return (1-200)"),
    offset: int = Query(default=0, ge=0, description="Pagination offset")
):
    """
    Get sorted podcasts list

    Query params:
    - sort_by: Sort field (name, episode_count, created_at, updated_at, popularity).
      "popularity" orders by Apple Podcasts TW top-chart rank (unranked shows last).
    - order: Sort order (asc, desc)
    - limit: Maximum number of podcasts to return (1-200)
    - offset: Pagination offset
    
    CDN Cache: 30 minutes
    """
    response.headers["Cache-Control"] = CACHE_CONTROL_LIST
    try:
        podcasts = await podcast_service.get_all_podcasts(
            sort_by=sort_by,
            order=order,
            limit=limit,
            offset=offset
        )
        return podcasts
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching podcasts: {str(e)}")


@router.get("/{podcast_name}", response_model=Podcast)
@cdn_cache_podcast
async def get_podcast_by_name(
    response: Response,
    podcast_name: str = Path(..., description="Podcast name")
):
    """
    Get podcast by name
    
    Returns podcast metadata including episode count and timestamps
    
    CDN Cache: 30 minutes
    """
    response.headers["Cache-Control"] = CACHE_CONTROL_READ
    try:
        podcast = await podcast_service.get_podcast_by_name(podcast_name)
        if not podcast:
            raise HTTPException(status_code=404, detail=f"Podcast '{podcast_name}' not found")
        return podcast
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching podcast: {str(e)}")


@router.get("/{podcast_name}/episodes", response_model=List[Episode])
@cdn_cache_podcast
async def get_podcast_episodes(
    response: Response,
    podcast_name: str = Path(..., description="Podcast name"),
    sort_by: str = Query(default="created_time", description="Sort field (created_time, episode_number, episode_title)"),
    order: str = Query(default="desc", description="Sort order (asc, desc)"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum number of episodes to return (1-200)"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    include_content: bool = Query(default=False, description="Include heavy content fields (transcript, summary)")
):
    """
    Get episodes for a podcast
    
    Query params:
    - sort_by: Sort field (created_time, episode_number, episode_title)
    - order: Sort order (asc, desc)
    - limit: Maximum number of episodes to return (1-200)
    - offset: Pagination offset
    
    CDN Cache: 30 minutes
    """
    response.headers["Cache-Control"] = CACHE_CONTROL_LIST
    try:
        # Verify podcast exists first
        podcast = await podcast_service.get_podcast_by_name(podcast_name)
        if not podcast:
            raise HTTPException(status_code=404, detail=f"Podcast '{podcast_name}' not found")
        
        episodes = await podcast_service.get_episodes_by_podcast(
            podcast_name=podcast_name,
            sort_by=sort_by,
            order=order,
            limit=limit,
            offset=offset,
            enrich_content=include_content
        )
        return episodes
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching episodes: {str(e)}")


@router.get("/{podcast_name}/episodes/{episode_id}", response_model=Episode)
@cdn_cache_podcast
async def get_episode_by_id(
    response: Response,
    podcast_name: str = Path(..., description="Podcast name"),
    episode_id: str = Path(..., description="Episode ID"),
    include_heavy_content: bool = Query(
        default=False,
        description="Also hydrate transcript/ticker blobs. False returns the fast episode-detail payload.",
    )
):
    """
    Get specific episode by ID
    
    Returns complete episode data including transcript, summary, and related tickers
    
    CDN Cache: 30 minutes
    """
    try:
        fields = None if include_heavy_content else EPISODE_DETAIL_CONTENT_FIELDS
        episode = await podcast_service.get_episode_by_id(
            podcast_name, episode_id, content_fields=fields,
        )
        if not episode:
            raise HTTPException(
                status_code=404,
                detail=f"Episode '{episode_id}' not found for podcast '{podcast_name}'"
            )
        if episode_content_incomplete(episode, content_fields=fields):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        else:
            response.headers["Cache-Control"] = CACHE_CONTROL_READ
        return episode
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching episode: {str(e)}")


@router.get("/{podcast_name}/episodes/{episode_id}/audio")
async def get_episode_audio(
    podcast_name: str = Path(..., description="Podcast name"),
    episode_id: str = Path(..., description="Episode ID"),
):
    """
    Redirect to a short-lived signed URL for the episode's MP3.

    Used by the web player when an episode has no Spotify URI. Never cached:
    the signed URL expires, so each playback session gets a fresh one.
    """
    try:
        signed_url = await podcast_service.get_episode_audio_signed_url(podcast_name, episode_id)
    except Exception as e:
        # A broken/missing GCS object or signing failure is a "no audio" condition
        # for the player, not a server fault — surface it as 404 so the UI can fall
        # back gracefully instead of showing an error.
        logger.warning(f"Failed to resolve audio for {podcast_name}/{episode_id}: {e}")
        signed_url = None
    if not signed_url:
        raise HTTPException(
            status_code=404,
            detail=f"No audio available for episode '{episode_id}'"
        )
    return RedirectResponse(
        url=signed_url,
        status_code=302,
        headers={"Cache-Control": "no-store"},
    )


@router.put("/{podcast_name}/episodes/{episode_id}/summary", response_model=Episode)
async def update_episode_summary(
    podcast_name: str = Path(..., description="Podcast name"),
    episode_id: str = Path(..., description="Episode ID"),
    content: str = Body(..., embed=True, description="Modified summary markdown content"),
    modified_by: Optional[str] = Body(None, embed=True, description="User identifier (email or ID)"),
    _admin: AdminAccess = Depends(get_content_write_access),
):
    """
    Update episode summary with modified content
    
    Note: This endpoint is always available on the backend, but the frontend 
    only exposes it when VITE_STAGE != PRODUCTION
    
    Args:
        podcast_name: Podcast name
        episode_id: Episode ID
        content: Modified summary markdown content
        modified_by: Optional user identifier (email or ID)
    
    Returns:
        Updated Episode object
        
    Raises:
        HTTPException(404): If episode not found
        HTTPException(500): If GCS or Firestore operation fails
    """
    try:
        episode = await podcast_service.save_modified_summary(
            podcast_name, episode_id, content, modified_by
        )
        return episode
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save modified summary: {str(e)}")


@router.delete("/{podcast_name}/episodes/{episode_id}/summary")
async def delete_episode_summary(
    podcast_name: str = Path(..., description="Podcast name"),
    episode_id: str = Path(..., description="Episode ID"),
    _admin: AdminAccess = Depends(get_content_write_access),
):
    """
    Delete modified episode summary and revert to original
    
    Note: This endpoint is always available on the backend, but the frontend 
    only exposes it when VITE_STAGE != PRODUCTION
    
    Args:
        podcast_name: Podcast name
        episode_id: Episode ID
    
    Returns:
        Success message
        
    Raises:
        HTTPException(404): If episode not found
        HTTPException(500): If GCS or Firestore operation fails
    """
    try:
        success = await podcast_service.delete_modified_summary(podcast_name, episode_id)
        return {"success": success, "message": "Reverted to original summary"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete modified summary: {str(e)}")


@router.patch("/{podcast_name}/episodes/{episode_id}", response_model=Episode)
async def patch_episode(
    podcast_name: str = Path(..., description="Podcast name"),
    episode_id: str = Path(..., description="Episode ID"),
    updates: dict = Body(..., description="Partial update: summary_content, key_insights, related_tickers, tags"),
    _admin: AdminAccess = Depends(get_content_write_access),
):
    """Patch allowed episode fields directly in Firestore (admin/content-writer only)."""
    try:
        return await podcast_service.patch_episode_fields(podcast_name, episode_id, updates)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to patch episode: {str(e)}")


@router.post("/{podcast_name}/episodes/{episode_id}/regenerate")
async def regenerate_episode_summary(
    background_tasks: BackgroundTasks,
    podcast_name: str = Path(..., description="Podcast name"),
    episode_id: str = Path(..., description="Episode ID"),
    _admin: AdminAccess = Depends(get_content_write_access),
):
    """
    Trigger episode summary regeneration.
    
    - Calls external API to start regeneration
    - Spawns background task to poll status and clear cache
    - Returns immediately so user can navigate away
    
    Args:
        podcast_name: Podcast name
        episode_id: Episode ID
    
    Returns:
        Status message indicating regeneration has started
        
    Raises:
        HTTPException(500): If external API call fails
    """
    api_url = settings.netcup_api_url
    api_key = settings.podcast_api_key
    
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="PODCAST_API_KEY not configured. Cannot trigger regeneration."
        )
    
    try:
        # Call external API to trigger regeneration
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{api_url}/api/episodes/rerun-summarize",
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": api_key
                },
                json={"episode_id": episode_id},
                timeout=30.0
            )
            response.raise_for_status()
        
        # Add background task for polling
        background_tasks.add_task(
            poll_regeneration_status,
            podcast_name,
            episode_id
        )
        
        return {
            "status": "started",
            "message": "Regeneration started. New summary will be available in a few minutes."
        }
        
    except httpx.HTTPStatusError as e:
        logger.error(f"External API error triggering regeneration: {e.response.status_code} - {e.response.text}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger regeneration: {e.response.status_code}"
        )
    except httpx.RequestError as e:
        logger.error(f"Request error triggering regeneration: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to connect to external API: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error triggering regeneration: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger regeneration: {str(e)}"
        )
