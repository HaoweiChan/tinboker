"""
Public read-only endpoint for the followed-content-source registry.

This is the Phase-2 activation surface: the tinboker-agents pipeline pulls the active
follow-list from here (instead of its local podcasts_*.json / feeds.json) at run start.
Open read — the follow-list is not sensitive and mirrors the agents repo's open GET /api/shows.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from src.database.postgres import get_session
from src.services.content_source_service import ContentSourceService
from src.schemas.content_source import (
    ContentSourcePublic,
    ContentSourcePublicListResponse,
)

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("", response_model=ContentSourcePublicListResponse)
async def list_public_sources(
    source_type: Optional[str] = Query(None, alias="type", description="podcast | news"),
    active: bool = Query(True, description="Only return active sources (default true)"),
    db: Session = Depends(get_session),
):
    """Return the active follow-list for the agents pipeline to pull."""
    service = ContentSourceService(db)
    if active:
        items = service.list_active_public(source_type=source_type)
    else:
        items, _ = service.list_sources(source_type=source_type, limit=500)
    return ContentSourcePublicListResponse(
        total=len(items),
        items=[ContentSourcePublic.model_validate(item) for item in items],
    )
