"""Admin API for managing the tag registry (view, create, update tier, delete, discover)."""

import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.auth.admin_auth import get_admin_access, AdminAccess
from src.cache.redis_client import cache_delete_pattern
from src.database.models import TagRegistry
from src.database.postgres import get_session
from src.services.firestore_service import FirestoreService
from src.services.podcast import PodcastService
from src.tag_registry import (
    KIND_SECTOR,
    KIND_TAG,
    TIER_TRENDING,
    VALID_TIERS,
    auto_register,
    seed_if_empty,
    sync_sectors,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

firestore = FirestoreService()
podcast_service = PodcastService()


class TagEntryResponse(BaseModel):
    id: int
    slug: str
    display_zh: str
    tier: str
    kind: str = KIND_TAG
    exposure_id: Optional[str] = None
    icon_id: Optional[str] = None
    color_hex: Optional[str] = None
    episode_count: Optional[int] = None
    updated_by: Optional[str] = None


class TagListResponse(BaseModel):
    tags: List[TagEntryResponse]
    total: int


class TagCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=100)
    display_zh: str = Field(..., min_length=1)
    tier: str = Field(default=TIER_TRENDING)


class TagUpdate(BaseModel):
    display_zh: Optional[str] = None
    tier: Optional[str] = None


class DiscoverResponse(BaseModel):
    discovered: int
    message: str


class SyncSectorsResponse(BaseModel):
    synced: int
    total: int
    message: str


async def _invalidate_tag_caches() -> None:
    """Bust Redis caches that depend on tag registry data."""
    for pattern in ("tags:*",):
        try:
            await cache_delete_pattern(pattern)
        except Exception as e:
            logger.warning("tag cache: Redis invalidation failed for %s: %s", pattern, e)


async def _count_episodes_for_slugs(slugs: list[str]) -> dict[str, int]:
    """Batch-count episodes per tag slug via Firestore subcollections."""
    sem = asyncio.Semaphore(12)

    async def _count(slug: str) -> tuple[str, int]:
        async with sem:
            try:
                count = await asyncio.to_thread(
                    firestore.count_subcollection_documents,
                    collection="tags", parent_doc_id=slug, subcollection="episodes",
                )
                return (slug, count or 0)
            except Exception:
                return (slug, 0)

    results = await asyncio.gather(*[_count(s) for s in slugs])
    return dict(results)


@router.get("/tags", response_model=TagListResponse)
async def list_tags(
    tier: Optional[str] = Query(None, description="Filter by tier"),
    kind: Optional[str] = Query(None, description="Filter by kind: 'tag' or 'sector'"),
    search: Optional[str] = Query(None, description="Search slug or display name"),
    admin: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    """List registry topics with episode counts (admin view — includes hidden).

    Covers both kinds: 'tag' counts come from Firestore tag subcollections; 'sector'
    counts come from the pipeline universe (list_sectors), since sectors are not stored
    in the 'tags' collection.
    """
    seed_if_empty(db)
    q = db.query(TagRegistry)
    if tier:
        q = q.filter(TagRegistry.tier == tier)
    if kind:
        q = q.filter(TagRegistry.kind == kind)
    if search:
        like = f"%{search}%"
        q = q.filter(
            TagRegistry.slug.ilike(like) | TagRegistry.display_zh.ilike(like)
        )
    q = q.order_by(TagRegistry.slug)
    rows = q.all()

    tag_rows = [r for r in rows if r.kind != KIND_SECTOR]
    sector_rows = [r for r in rows if r.kind == KIND_SECTOR]

    tag_counts = await _count_episodes_for_slugs([r.slug for r in tag_rows]) if tag_rows else {}
    sector_counts: dict[str, int] = {}
    if sector_rows:
        try:
            sectors = await podcast_service.list_sectors()
            sector_counts = {
                s["exposure_id"]: s.get("count", 0) for s in sectors if s.get("exposure_id")
            }
        except Exception as e:
            logger.warning("sector counts: list_sectors failed: %s", e)

    def _count_for(r: TagRegistry) -> int:
        if r.kind == KIND_SECTOR:
            return sector_counts.get(r.exposure_id or "", 0)
        return tag_counts.get(r.slug, 0)

    return TagListResponse(
        tags=[
            TagEntryResponse(
                id=r.id, slug=r.slug, display_zh=r.display_zh,
                tier=r.tier, kind=r.kind, exposure_id=r.exposure_id,
                icon_id=r.icon_id, color_hex=r.color_hex,
                episode_count=_count_for(r), updated_by=r.updated_by,
            )
            for r in rows
        ],
        total=len(rows),
    )


@router.post("/tags/discover", response_model=DiscoverResponse)
async def discover_tags(
    min_episodes: int = Query(default=3, ge=1, description="Minimum episodes to auto-register"),
    admin: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    """Scan Firestore for tags not yet in the registry and auto-register them as hidden."""
    all_firestore_slugs = await asyncio.to_thread(
        firestore.get_all_parent_documents, "tags"
    )
    if not all_firestore_slugs:
        return DiscoverResponse(discovered=0, message="No tags found in Firestore")
    existing = {r[0] for r in db.query(TagRegistry.slug).all()}
    unknown = [s for s in all_firestore_slugs if s not in existing]
    if not unknown:
        return DiscoverResponse(discovered=0, message="All Firestore tags are already registered")
    counts = await _count_episodes_for_slugs(unknown)
    qualifying = [s for s in unknown if counts.get(s, 0) >= min_episodes]
    if not qualifying:
        return DiscoverResponse(
            discovered=0,
            message=f"Found {len(unknown)} unknown tags but none had >= {min_episodes} episodes",
        )
    inserted = auto_register(db, qualifying)
    await _invalidate_tag_caches()
    return DiscoverResponse(
        discovered=inserted,
        message=f"Auto-registered {inserted} new tags as hidden (from {len(unknown)} unknown, {len(qualifying)} with >= {min_episodes} episodes)",
    )


@router.post("/tags/sync-sectors", response_model=SyncSectorsResponse)
async def sync_sectors_endpoint(
    admin: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    """Sync sector/theme exposures from the pipeline universe into the registry.

    New sectors are added as VISIBLE (trending); existing rows refresh their display
    name / visuals but keep their curated visibility. Admins then hide unwanted sectors.
    """
    try:
        sectors = await podcast_service.list_sectors()
    except Exception as e:
        raise HTTPException(500, f"Failed to read sectors from universe: {e}")
    new_count = sync_sectors(db, sectors)
    await _invalidate_tag_caches()
    return SyncSectorsResponse(
        synced=new_count,
        total=len(sectors),
        message=f"Synced {len(sectors)} sectors ({new_count} new, added as visible)",
    )


@router.post("/tags", response_model=TagEntryResponse, status_code=201)
async def create_tag(
    body: TagCreate,
    admin: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    """Add a new tag to the registry (tag kind only — sectors are synced, not authored)."""
    if body.tier not in VALID_TIERS:
        raise HTTPException(400, f"tier must be one of: {', '.join(VALID_TIERS)}")
    existing = db.query(TagRegistry).filter(TagRegistry.slug == body.slug).first()
    if existing:
        raise HTTPException(409, f"Tag '{body.slug}' already exists")
    row = TagRegistry(
        slug=body.slug, display_zh=body.display_zh,
        tier=body.tier, updated_by=admin.email,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    await _invalidate_tag_caches()
    return TagEntryResponse(
        id=row.id, slug=row.slug, display_zh=row.display_zh,
        tier=row.tier, updated_by=row.updated_by,
    )


@router.patch("/tags/{tag_id}", response_model=TagEntryResponse)
async def update_tag(
    tag_id: int,
    body: TagUpdate,
    admin: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    """Update a tag's display name or tier."""
    row = db.query(TagRegistry).filter(TagRegistry.id == tag_id).first()
    if not row:
        raise HTTPException(404, "Tag not found")
    if body.tier and body.tier not in VALID_TIERS:
        raise HTTPException(400, f"tier must be one of: {', '.join(VALID_TIERS)}")
    if body.display_zh is not None:
        row.display_zh = body.display_zh
    if body.tier is not None:
        row.tier = body.tier
    row.updated_by = admin.email
    db.commit()
    db.refresh(row)
    await _invalidate_tag_caches()
    return TagEntryResponse(
        id=row.id, slug=row.slug, display_zh=row.display_zh,
        tier=row.tier, updated_by=row.updated_by,
    )


@router.delete("/tags/{tag_id}", status_code=204)
async def delete_tag(
    tag_id: int,
    admin: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    """Remove a tag from the registry entirely (tag kind only).

    Sectors are synced from the pipeline universe; they cannot be hand-deleted (a
    re-sync would just re-add them). Hide them via PATCH tier='hidden' instead.
    """
    row = db.query(TagRegistry).filter(TagRegistry.id == tag_id).first()
    if not row:
        raise HTTPException(404, "Tag not found")
    if row.kind == KIND_SECTOR:
        raise HTTPException(400, "Sectors are synced, not deletable — hide it instead (tier='hidden')")
    db.delete(row)
    db.commit()
    await _invalidate_tag_caches()
