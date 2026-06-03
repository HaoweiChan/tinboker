"""
Admin API endpoints for managing followed content sources (podcast shows + news feeds).
Gated by Google OAuth + ADMIN_EMAILS whitelist (same as admin translations).
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from src.database.postgres import get_session
from src.services.content_source_service import ContentSourceService
from src.schemas.content_source import (
    ContentSourceCreate,
    ContentSourceUpdate,
    ContentSourceResponse,
    ContentSourceListResponse,
)
from src.auth.admin_auth import get_admin_access, AdminAccess

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ==================== Stats (before parameterized routes) ====================

@router.get("/sources/stats")
async def get_source_stats(
    db: Session = Depends(get_session),
    admin: AdminAccess = Depends(get_admin_access),
):
    """Get content-source statistics (counts by type + active)."""
    return ContentSourceService(db).get_stats()


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
    return {"success": True}
