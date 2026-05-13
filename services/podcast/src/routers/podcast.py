"""Router for podcast-specific endpoints (show metadata + episode processing)."""

from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Security
from pydantic import BaseModel

from src.auth import verify_api_key
from src.routers.episode import run_episode_rerun

router = APIRouter(prefix="/api/podcast", tags=["podcast"])


class PodcastShowResponse(BaseModel):
    """Show-level metadata for a single podcast."""
    podcast_name: str
    thumbnail_url: Optional[str] = None
    thumbnails: List[str] = []
    publisher: Optional[str] = None
    description: Optional[str] = None
    spotify_show_id: Optional[str] = None
    spotify_show_url: Optional[str] = None
    language: Optional[str] = None
    total_episodes: Optional[int] = None


class EpisodeRegenerateResponse(BaseModel):
    """Response model for episode regeneration."""
    message: str
    episode_id: str
    podcast_name: str
    status: str


@router.get("/shows", response_model=List[PodcastShowResponse])
async def list_podcast_shows(
    api_key: str = Security(verify_api_key),
):
    """Return show-level metadata for all podcasts (thumbnails, publisher, etc.)."""
    from src.service.upload_to_firebase import FirebaseService
    fb = FirebaseService()
    shows = fb.get_all_podcast_shows()
    return [PodcastShowResponse(**s) for s in shows]


@router.get("/shows/{podcast_name}", response_model=PodcastShowResponse)
async def get_podcast_show(
    podcast_name: str,
    api_key: str = Security(verify_api_key),
):
    """Return show-level metadata for a single podcast by name."""
    from src.service.upload_to_firebase import FirebaseService
    fb = FirebaseService()
    show = fb.get_podcast_show(podcast_name)
    if not show:
        raise HTTPException(status_code=404, detail=f"Podcast show '{podcast_name}' not found")
    return PodcastShowResponse(**show)


@router.post("/{podcast_name}/episodes/{episode_id}/regenerate", response_model=EpisodeRegenerateResponse)
async def regenerate_episode(
    podcast_name: str,
    episode_id: str,
    background_tasks: BackgroundTasks,
    api_key: str = Security(verify_api_key)
):
    """
    Regenerate (rerun summarize) for a specific episode.

    The podcast_name parameter is included in the URL for organization but
    the actual processing uses only the episode_id.
    """
    if not episode_id or not episode_id.strip():
        raise HTTPException(status_code=400, detail="episode_id is required")
    if not podcast_name or not podcast_name.strip():
        raise HTTPException(status_code=400, detail="podcast_name is required")

    project_root = Path(__file__).parent.parent.parent
    background_tasks.add_task(run_episode_rerun, episode_id, project_root)

    return EpisodeRegenerateResponse(
        message=f"Episode regeneration job started for episode_id: {episode_id}",
        episode_id=episode_id,
        podcast_name=podcast_name,
        status="started"
    )
