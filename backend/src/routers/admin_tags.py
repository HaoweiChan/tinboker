"""Admin API for managing the tag registry (view, create, update tier, delete)."""

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.auth.admin_auth import get_admin_access, AdminAccess
from src.cache.redis_client import cache_delete_pattern
from src.database.models import TagRegistry
from src.database.postgres import get_session
from src.tag_registry import seed_if_empty

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


class TagEntryResponse(BaseModel):
    id: int
    slug: str
    display_zh: str
    tier: str
    updated_by: Optional[str] = None


class TagListResponse(BaseModel):
    tags: List[TagEntryResponse]
    total: int


class TagCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=100)
    display_zh: str = Field(..., min_length=1)
    tier: str = Field(default="trending")


class TagUpdate(BaseModel):
    display_zh: Optional[str] = None
    tier: Optional[str] = None


async def _invalidate_tag_caches() -> None:
    """Bust Redis caches that depend on tag registry data."""
    for pattern in ("tags:*",):
        try:
            await cache_delete_pattern(pattern)
        except Exception as e:
            logger.warning("tag cache: Redis invalidation failed for %s: %s", pattern, e)


@router.get("/tags", response_model=TagListResponse)
async def list_tags(
    tier: Optional[str] = Query(None, description="Filter by tier"),
    search: Optional[str] = Query(None, description="Search slug or display name"),
    admin: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    """List all tags in the registry (admin view — includes suppressed)."""
    seed_if_empty(db)
    q = db.query(TagRegistry)
    if tier:
        q = q.filter(TagRegistry.tier == tier)
    if search:
        like = f"%{search}%"
        q = q.filter(
            TagRegistry.slug.ilike(like) | TagRegistry.display_zh.ilike(like)
        )
    q = q.order_by(TagRegistry.slug)
    rows = q.all()
    return TagListResponse(
        tags=[
            TagEntryResponse(
                id=r.id, slug=r.slug, display_zh=r.display_zh,
                tier=r.tier, updated_by=r.updated_by,
            )
            for r in rows
        ],
        total=len(rows),
    )


@router.post("/tags", response_model=TagEntryResponse, status_code=201)
async def create_tag(
    body: TagCreate,
    admin: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    """Add a new tag to the registry."""
    if body.tier not in ("trending", "valid", "suppressed"):
        raise HTTPException(400, "tier must be trending, valid, or suppressed")
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
    if body.tier and body.tier not in ("trending", "valid", "suppressed"):
        raise HTTPException(400, "tier must be trending, valid, or suppressed")
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
    """Remove a tag from the registry entirely."""
    row = db.query(TagRegistry).filter(TagRegistry.id == tag_id).first()
    if not row:
        raise HTTPException(404, "Tag not found")
    db.delete(row)
    db.commit()
    await _invalidate_tag_caches()
