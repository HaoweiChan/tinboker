"""
Admin API endpoints for managing followed content sources (podcast shows + news feeds).
Gated by Google OAuth + ADMIN_EMAILS whitelist (same as admin translations).
"""

import logging
from typing import Optional
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, Query

from src.services.podcast import PodcastService
from src.database.postgres import get_session
from src.cache import cache_delete_pattern_all_envs, purge_cdn_cache
from src.auth.admin_auth import get_admin_access, AdminAccess
from src.services.content_source_service import ContentSourceService
from src.schemas.content_source import (
    ContentSourceCreate,
    ContentSourceUpdate,
    ContentSourceResponse,
    ContentSourceListResponse,
    SourceRunStatus,
    SourceRunStatusResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

# Reused for the Firestore-derived run-status (cached podcast aggregation).
podcast_service = PodcastService()

# All API + frontend hosts that may cache content-source-derived responses.
# Since all environments share the same Postgres and Redis, a content-source
# change from any env must invalidate ALL envs' CDN caches immediately.
_ALL_API_HOSTS = [
    "api.tinboker.com",
    "staging-api.tinboker.com",
    "dev-api.tinboker.com",
]
_ALL_FRONTEND_HOSTS = [
    "tinboker.com",
    "www.tinboker.com",
    "staging.tinboker.com",
    "dev.tinboker.com",
]


async def _invalidate_source_caches() -> None:
    """Bust the caches a content-source change affects so an admin edit (e.g. toggling a
    source active/inactive) shows up on the public site promptly, instead of waiting out
    the Redis (origin) and Cloudflare (edge) TTLs.

    All environments share the same Postgres and Redis, so a change made from any env's
    admin page must purge ALL envs' CDN caches — otherwise the other envs serve stale
    edge-cached responses until the TTL expires (up to 1h + stale-while-revalidate).

    Best-effort: every failure is logged, never raised — the admin write has already
    committed, so a cache hiccup must not turn a successful edit into a 500.
    """
    # Redis (origin). The release allowlist and the podcast/episode/news lists are all
    # derived from content_sources, so clear them and let the next request recompute.
    for pattern in (
        "release:allowed_podcasts:*",
        "podcast:*",
        "episode:*",
        "episodes:*",
        "news:*",
    ):
        try:
            await cache_delete_pattern_all_envs(pattern)
        except Exception as e:
            logger.warning("source cache: Redis invalidation failed for %s: %s", pattern, e)

    # Cloudflare (edge). Purge ALL environments' API and frontend hosts in one call.
    # All envs share the same DB/Redis, so a source change from any admin page must
    # be reflected everywhere. One batched host purge is cheaper than per-env calls.
    all_hosts = _ALL_API_HOSTS + _ALL_FRONTEND_HOSTS
    try:
        await purge_cdn_cache(hosts=all_hosts)
    except Exception as e:
        logger.warning("source cache: CDN purge failed for hosts %s: %s", all_hosts, e)


# ==================== Stats (before parameterized routes) ====================

@router.get("/sources/stats")
async def get_source_stats(
    db: Session = Depends(get_session),
    admin: AdminAccess = Depends(get_admin_access),
):
    """Get content-source statistics (counts by type + active)."""
    return ContentSourceService(db).get_stats()


@router.get("/sources/run-status", response_model=SourceRunStatusResponse)
async def get_sources_run_status(
    admin: AdminAccess = Depends(get_admin_access),
):
    """Per-podcast last-ingested status, derived from the (cached) Firestore episode
    aggregation. v1 covers podcasts only; news sources have no entry. Registered before
    /sources/{source_id} so "run-status" isn't captured as a source id.
    """
    podcasts = await podcast_service.get_all_podcasts(limit=100000)
    items = [
        SourceRunStatus(
            name=p.name,
            last_ingested_at=(
                datetime.fromtimestamp(p.updated_at / 1000, tz=timezone.utc).isoformat()
                if p.updated_at
                else None
            ),
            episode_count=p.episode_count,
        )
        for p in podcasts
    ]
    return SourceRunStatusResponse(items=items)


# ==================== Content sources CRUD ====================

@router.get("/sources", response_model=ContentSourceListResponse)
async def list_sources(
    source_type: Optional[str] = Query(None, alias="type", description="Filter by source type (podcast|news)"),
    region: Optional[str] = Query(None, description="Filter by region (news)"),
    language: Optional[str] = Query(None, description="Filter by language (podcast)"),
    active: Optional[bool] = Query(None, description="Filter by active flag"),
    search: Optional[str] = Query(None, description="Search in name/slug/feed_url"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=200, description="Items per page"),
    db: Session = Depends(get_session),
    admin: AdminAccess = Depends(get_admin_access),
):
    """List content sources with optional filters and pagination."""
    service = ContentSourceService(db)
    items, total = service.list_sources(
        source_type=source_type,
        region=region,
        language=language,
        active=active,
        search=search,
        page=page,
        limit=limit,
    )
    return ContentSourceListResponse(
        total=total,
        page=page,
        limit=limit,
        items=[ContentSourceResponse.model_validate(item) for item in items],
    )


@router.get("/sources/{source_id}", response_model=ContentSourceResponse)
async def get_source(
    source_id: int,
    db: Session = Depends(get_session),
    admin: AdminAccess = Depends(get_admin_access),
):
    """Get a single content source by ID."""
    source = ContentSourceService(db).get_by_id(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Content source not found")
    return ContentSourceResponse.model_validate(source)


@router.post("/sources", response_model=ContentSourceResponse, status_code=201)
async def create_source(
    data: ContentSourceCreate,
    db: Session = Depends(get_session),
    admin: AdminAccess = Depends(get_admin_access),
):
    """Create a new content source."""
    source = ContentSourceService(db).create(data, updated_by=admin.email)
    await _invalidate_source_caches()
    return ContentSourceResponse.model_validate(source)


@router.put("/sources/{source_id}", response_model=ContentSourceResponse)
async def update_source(
    source_id: int,
    data: ContentSourceUpdate,
    db: Session = Depends(get_session),
    admin: AdminAccess = Depends(get_admin_access),
):
    """Update an existing content source."""
    source = ContentSourceService(db).update(source_id, data, updated_by=admin.email)
    if not source:
        raise HTTPException(status_code=404, detail="Content source not found")
    await _invalidate_source_caches()
    return ContentSourceResponse.model_validate(source)


@router.delete("/sources/{source_id}")
async def delete_source(
    source_id: int,
    db: Session = Depends(get_session),
    admin: AdminAccess = Depends(get_admin_access),
):
    """Delete a content source."""
    if not ContentSourceService(db).delete(source_id):
        raise HTTPException(status_code=404, detail="Content source not found")
    await _invalidate_source_caches()
    return {"success": True}
