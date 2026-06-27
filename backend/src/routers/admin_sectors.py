"""Admin API for sector/theme curation — the theme-discovery queue.

Surfaces emerging market concepts (e.g. CPO) that the deterministic resolver saw in
episodes but could not map to any curated exposure, so an admin can promote recurring
ones into curated_themes.json. Gated by Google OAuth + ADMIN_EMAILS whitelist.
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.auth.admin_auth import get_admin_access, AdminAccess
from src.services.podcast import PodcastService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

podcast_service = PodcastService()


class ThemeCandidateExample(BaseModel):
    episode_title: str = ""
    context: str = ""


class ThemeCandidate(BaseModel):
    normalized_text: str
    mention_text: str
    count: int
    examples: List[ThemeCandidateExample] = []


class ThemeCandidatesResponse(BaseModel):
    candidates: List[ThemeCandidate]


@router.get("/sectors/theme-candidates", response_model=ThemeCandidatesResponse)
async def get_theme_candidates(
    threshold: int = Query(default=3, ge=2, le=20, description="Min recurrence to surface a candidate"),
    limit: int = Query(default=40, ge=1, le=100),
    admin: AdminAccess = Depends(get_admin_access),
):
    """Ranked emerging theme candidates from episodes' unresolved_market_trends."""
    try:
        items = await podcast_service.theme_candidates(threshold=threshold, limit=limit)
        return ThemeCandidatesResponse(candidates=[ThemeCandidate(**i) for i in items])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching theme candidates: {str(e)}")
