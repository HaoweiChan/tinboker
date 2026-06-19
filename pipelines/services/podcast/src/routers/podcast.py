"""Router for podcast-specific endpoints (show metadata + episode processing)."""

import asyncio
from pathlib import Path
from typing import Any, List, Optional

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


# ── On-demand social copy (Threads/Facebook post + per-theme comments) ─────────


class SocialCopyComment(BaseModel):
    """One conversational comment, mapped to a theme card."""
    heading: str = ""
    text: str = ""


class SocialCopyResponse(BaseModel):
    """The freshly generated human-tone social copy for an episode."""
    episode_id: str
    post: str
    comments: List[SocialCopyComment]


def _generate_social_copy(episode_id: str) -> dict[str, Any]:
    """Load the episode and run the social_copy_writer LLM node.

    Read-only against Firestore: it pulls the episode's stored ``social_cards`` +
    ``summary_content`` and returns the generated ``social_thread``. Persistence
    (and cache invalidation) is the platform backend's job via its
    ``set_social_thread`` write path — this endpoint never writes.
    """
    from src.podcast.content_builder.nodes.social_copy_writer import write_social_copy
    from src.service.firestore_service import FirestoreService

    doc = FirestoreService().get_document("episodes", episode_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Episode '{episode_id}' not found")

    # The writer reads cards + the summary steer from a minimal pipeline state; the
    # field names mirror what the live pipeline seeds (markdown_report == the
    # episode's summary_content; source == podcast_name).
    state: dict[str, Any] = {
        "social_cards": doc.get("social_cards") or [],
        "key_insights": doc.get("key_insights") or [],
        "episode_title": doc.get("episode_title") or doc.get("title") or "Episode",
        "source": doc.get("podcast_name") or "Podcast",
        "markdown_report": doc.get("summary_content") or "",
    }
    return write_social_copy(state).get("social_thread") or {}


@router.post("/episodes/{episode_id}/social-copy", response_model=SocialCopyResponse)
async def generate_social_copy(
    episode_id: str,
    api_key: str = Security(verify_api_key),
):
    """Generate the human-tone social copy (a grand-summary post + one comment per
    theme card) for an existing episode, on demand.

    The platform backend has no LLM, so its admin Social page proxies here to
    (re-)author copy — e.g. for episodes that predate the pipeline's
    social_copy_writer node. Returns the generated copy; the caller persists it.
    """
    if not episode_id or not episode_id.strip():
        raise HTTPException(status_code=400, detail="episode_id is required")

    try:
        thread = await asyncio.to_thread(_generate_social_copy, episode_id)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — surface LLM/Firestore failures as 502
        raise HTTPException(status_code=502, detail=f"Social copy generation failed: {e}")

    post = (thread.get("post") or "").strip()
    comments = [
        SocialCopyComment(heading=(c or {}).get("heading", ""), text=(c or {}).get("text", ""))
        for c in (thread.get("comments") or [])
        if (c or {}).get("text")
    ]
    if not post and not comments:
        raise HTTPException(
            status_code=502,
            detail="Social copy generation produced no content (empty post + comments).",
        )

    return SocialCopyResponse(episode_id=episode_id, post=post, comments=comments)
