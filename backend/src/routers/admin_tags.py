"""Admin API for managing the tag registry (view, create, update tier, delete, discover)."""

import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.auth.admin_auth import get_admin_access, AdminAccess
from src.cache.redis_client import cache_delete_pattern_all_envs
from src.database.models import TagRegistry
from src.database.postgres import get_session
from src.services.firestore_service import FirestoreService
from src.services.podcast import PodcastService
from src.tag_registry import (
    KIND_SECTOR,
    KIND_TAG,
    TIER_HIDDEN,
    TIER_TRENDING,
    VALID_TIERS,
    auto_register,
    canonical_label,
    canonical_tag_slugs,
    normalize_tag_slug,
    seed_if_empty,
    sync_sectors,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

firestore = FirestoreService()
podcast_service = PodcastService()


class TagEntryResponse(BaseModel):
    # id is None for VIRTUAL rows — tags that appear in episodes (so they auto-surface
    # on /topics) but have no registry row yet. Surfacing them here lets admins hide
    # them; hiding creates the registry row (see the frontend toggle).
    id: Optional[int] = None
    slug: str
    display_zh: str
    tier: str
    kind: str = KIND_TAG
    registered: bool = True
    exposure_id: Optional[str] = None
    # 'sector' (industry) vs 'theme' for sector-kind rows; None for plain tags. Lets the
    # admin table distinguish 產業 from 題材 even though both share kind='sector'.
    exposure_type: Optional[str] = None
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
    """Bust Redis caches that depend on tag registry data (all envs share the DB)."""
    for pattern in ("tags:*",):
        try:
            await cache_delete_pattern_all_envs(pattern)
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
    """List topics with episode counts (admin view — includes hidden).

    Returns the full curatable set so nothing that can surface on /topics is
    unmanageable:
      • registry rows (tags + synced sectors), and
      • VIRTUAL tag rows — Firestore tags with no registry row yet. They auto-surface
        on /topics by volume, so they're shown here (visible-by-default, registered=
        False) and can be hidden; hiding creates the registry row.
    Tag counts come from Firestore tag subcollections; sector counts from the universe.
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

    # ── Virtual tags: unregistered tags shown so they're curatable. Two flavors:
    #   1. Vocabulary tags with no registry row → VISIBLE by default (they auto-surface
    #      on /topics). Bounded (<=168), no Firestore call, shown regardless of search.
    #   2. Off-vocabulary Firestore tags with no registry row → HIDDEN by default (gated
    #      off /topics). The collection holds thousands, so only computed when SEARCHING
    #      and capped — lets an admin find a legit off-vocab topic and "show" (promote)
    #      it (promotion = a trending registry row, which the trending gate honors).
    # Hiding/showing a virtual row creates its registry row. Excluded for the sector kind.
    OFFVOCAB_CAP = 200
    virtual: list[dict] = []
    if kind != KIND_SECTOR:
        # Dedupe against ALL registry tag rows (normalized), not just the filtered page,
        # so a registered tag never reappears as a virtual row.
        registered_norm = {
            normalize_tag_slug(s)
            for (s,) in db.query(TagRegistry.slug).filter(TagRegistry.kind != KIND_SECTOR).all()
        }
        canon = canonical_tag_slugs()
        needle = search.lower() if search else None

        if tier != TIER_HIDDEN:  # vocab virtual rows are visible-by-default
            for norm in sorted(canon):
                if norm in registered_norm:
                    continue
                label = canonical_label(norm)
                if needle and needle not in norm and needle not in label.lower():
                    continue
                virtual.append({"slug": norm, "display_zh": label, "tier": TIER_TRENDING})

        if needle and tier != TIER_TRENDING:  # off-vocab virtual rows are hidden-by-default
            try:
                fs_slugs = await asyncio.to_thread(firestore.get_all_parent_documents, "tags")
            except Exception as e:
                logger.warning("virtual off-vocab tags: Firestore listing failed: %s", e)
                fs_slugs = []
            seen = set(registered_norm)
            offvocab = 0
            for s in fs_slugs:
                n = normalize_tag_slug(s)
                if n in canon or n in seen or needle not in s.lower():
                    continue
                seen.add(n)
                virtual.append({"slug": s, "display_zh": s, "tier": TIER_HIDDEN})
                offvocab += 1
                if offvocab >= OFFVOCAB_CAP:
                    break

    # Count ONLY registry tag rows (a bounded ~dozens). Virtual tags are NOT counted —
    # there can be hundreds of Firestore tags and one subcollection count each blows past
    # the gateway timeout (caused a 524). Virtual rows show episode_count=None ("—").
    tag_counts = await _count_episodes_for_slugs([r.slug for r in tag_rows]) if tag_rows else {}
    sector_counts: dict[str, int] = {}
    sector_types: dict[str, str] = {}
    if sector_rows:
        try:
            sectors = await podcast_service.list_sectors()
            sector_counts = {
                s["exposure_id"]: s.get("count", 0) for s in sectors if s.get("exposure_id")
            }
            sector_types = {
                s["exposure_id"]: s.get("exposure_type") for s in sectors if s.get("exposure_id")
            }
        except Exception as e:
            logger.warning("sector counts: list_sectors failed: %s", e)

    def _count_for(r: TagRegistry) -> int:
        if r.kind == KIND_SECTOR:
            return sector_counts.get(r.exposure_id or "", 0)
        return tag_counts.get(r.slug, 0)

    entries = [
        TagEntryResponse(
            id=r.id, slug=r.slug, display_zh=r.display_zh,
            tier=r.tier, kind=r.kind, registered=True, exposure_id=r.exposure_id,
            exposure_type=sector_types.get(r.exposure_id or "") if r.kind == KIND_SECTOR else None,
            icon_id=r.icon_id, color_hex=r.color_hex,
            episode_count=_count_for(r), updated_by=r.updated_by,
        )
        for r in rows
    ]
    entries += [
        TagEntryResponse(
            id=None, slug=v["slug"], display_zh=v["display_zh"],
            tier=v["tier"], kind=KIND_TAG, registered=False,
            episode_count=None,  # not counted — see note above (avoids the 524 timeout)
        )
        for v in virtual
    ]
    entries.sort(key=lambda e: (e.kind, e.slug.lower()))
    return TagListResponse(tags=entries, total=len(entries))


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
