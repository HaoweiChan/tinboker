"""
Admin API endpoints for managing stock translations.
Requires JWT authentication.
"""

import csv
import io
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from src.database.postgres import get_session
from src.services.translation_service import TranslationService
from src.schemas.translation import (
    TranslationCreate,
    TranslationUpdate,
    TranslationResponse,
    TranslationListResponse,
    BulkImportItem,
    BulkImportResponse,
    MissingTranslation,
    MissingTranslationsResponse,
)
from src.auth.admin_auth import (
    get_admin_access,
    get_translation_access,
    AdminAccess,
)

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"]
)


@router.get("/auth/check")
async def check_admin_access(admin: AdminAccess = Depends(get_admin_access)):
    """Check if the current Google-authenticated user has admin access."""
    return {"has_access": True, "email": admin.email}


# ==================== Reports & Stats (must be before parameterized routes) ====================

@router.get("/translations/stats")
async def get_translation_stats(
    db: Session = Depends(get_session),
    admin: AdminAccess = Depends(get_admin_access)
):
    """Get translation statistics."""
    service = TranslationService(db)
    return service.get_stats()


@router.get("/translations/missing", response_model=MissingTranslationsResponse)
async def get_missing_translations(
    market: Optional[str] = Query(None, description="Filter by market"),
    limit: int = Query(100, ge=1, le=500, description="Max items to return"),
    db: Session = Depends(get_session),
    admin: AdminAccess = Depends(get_admin_access)
):
    """Get translations without ZH-TW name."""
    service = TranslationService(db)
    items = service.get_missing_translations(market=market, limit=limit)
    return MissingTranslationsResponse(
        total=len(items),
        items=[
            MissingTranslation(
                ticker=item.ticker,
                market=item.market,
                name_en=item.name_en
            )
            for item in items
        ]
    )


@router.post("/translations/autofill")
async def autofill_pending_translations(
    market: Optional[str] = Query(None, description="Limit to a market (e.g. TW/US)"),
    limit: int = Query(100, ge=1, le=500, description="Max stubs to resolve this run"),
    db: Session = Depends(get_session),
    admin: AdminAccess = Depends(get_admin_access),
):
    """Resolve names for missing/pending stubs from market data (FinMind TW / Massive US).

    Drains the existing backlog on demand — the same autofill that runs automatically on
    ingest. Only fills non-approved rows lacking the market-appropriate name; writes
    ``status='auto'`` (a human approval still wins).
    """
    from src.services.translation_autofill import autofill_names_for_rows

    service = TranslationService(db)
    rows = service.get_missing_translations(market=market, limit=limit)
    filled = autofill_names_for_rows(db, rows)
    return {"attempted": len(rows), "filled": filled}


@router.post("/translations/cleanup-unresolvable")
async def cleanup_unresolvable_translations(
    stale_days: int = Query(7, ge=1, le=365, description="Mark stubs older than this many days as unresolvable"),
    dry_run: bool = Query(False, description="Count affected rows without writing"),
    db: Session = Depends(get_session),
    admin: AdminAccess = Depends(get_admin_access),
):
    """Mark long-lived, name-less PENDING stubs as ``unresolvable``.

    Targets stubs that were auto-created by ingest discovery (``last_updated_by =
    'ingest_discovery'``) but have no name from FinMind or Massive after ``stale_days``
    days.  These are typically junk strings (country names, index codes, non-listed
    companies) that slipped through ticker extraction.  Marking them ``unresolvable``
    removes them from the active pending queue without deleting history.
    """
    from src.services.translation_autofill import mark_unresolvable_stubs

    marked = mark_unresolvable_stubs(db, stale_days=stale_days, dry_run=dry_run)
    return {"marked": marked, "stale_days": stale_days, "dry_run": dry_run}


# ==================== Translations CRUD ====================

@router.get("/translations", response_model=TranslationListResponse)
async def list_translations(
    market: Optional[str] = Query(None, description="Filter by market"),
    status: Optional[str] = Query(None, description="Filter by translation status"),
    search: Optional[str] = Query(None, description="Search in ticker/name"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_session),
    admin: AdminAccess = Depends(get_translation_access)
):
    """
    List translations with optional filters and pagination.
    Accepts an admin JWT or the TINBOKER_WRITE_TOKEN (backfill agent work queue).
    """
    service = TranslationService(db)
    items, total = service.list_translations(
        market=market,
        status=status,
        search=search,
        page=page,
        limit=limit
    )
    return TranslationListResponse(
        total=total,
        page=page,
        limit=limit,
        items=[TranslationResponse.model_validate(item) for item in items]
    )


@router.get("/translations/{translation_id}", response_model=TranslationResponse)
async def get_translation(
    translation_id: int,
    db: Session = Depends(get_session),
    admin: AdminAccess = Depends(get_admin_access)
):
    """Get a single translation by ID."""
    service = TranslationService(db)
    translation = service.get_by_id(translation_id)
    if not translation:
        raise HTTPException(status_code=404, detail="Translation not found")
    return TranslationResponse.model_validate(translation)


@router.post("/translations", response_model=TranslationResponse, status_code=201)
async def create_translation(
    data: TranslationCreate,
    db: Session = Depends(get_session),
    admin: AdminAccess = Depends(get_admin_access)
):
    """Create a new translation."""
    service = TranslationService(db)
    # Check if already exists
    existing = service.get_by_ticker_market(data.ticker, data.market)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Translation for {data.ticker}/{data.market} already exists"
        )
    translation = service.create(data, updated_by="admin")
    return TranslationResponse.model_validate(translation)


@router.put("/translations/{translation_id}", response_model=TranslationResponse)
async def update_translation(
    translation_id: int,
    data: TranslationUpdate,
    db: Session = Depends(get_session),
    admin: AdminAccess = Depends(get_admin_access)
):
    """Update an existing translation."""
    service = TranslationService(db)
    try:
        translation = service.update(translation_id, data, updated_by="admin")
    except ValueError as e:
        # Market change would collide with an existing (ticker, market) row.
        raise HTTPException(status_code=409, detail=str(e))
    if not translation:
        raise HTTPException(status_code=404, detail="Translation not found")
    return TranslationResponse.model_validate(translation)


@router.delete("/translations/{translation_id}")
async def delete_translation(
    translation_id: int,
    db: Session = Depends(get_session),
    admin: AdminAccess = Depends(get_admin_access)
):
    """Delete a translation."""
    service = TranslationService(db)
    if not service.delete(translation_id):
        raise HTTPException(status_code=404, detail="Translation not found")
    return {"success": True}


# ==================== Bulk Operations ====================

@router.post("/translations/bulk-import", response_model=BulkImportResponse)
async def bulk_import_translations(
    file: UploadFile = File(..., description="CSV file with translations"),
    db: Session = Depends(get_session),
    admin: AdminAccess = Depends(get_admin_access)
):
    """
    Bulk import translations from CSV file.
    Expected columns: ticker, market, name_en, name_zh_tw
    Optional column: translation_status (defaults to 'auto')
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")
    content = await file.read()
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            decoded = content.decode("utf-8-sig")  # Handle BOM
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="Invalid CSV encoding")
    reader = csv.DictReader(io.StringIO(decoded))
    # Validate headers
    required_headers = {"ticker", "market"}
    if not required_headers.issubset(set(reader.fieldnames or [])):
        raise HTTPException(
            status_code=400,
            detail=f"CSV must have columns: {required_headers}"
        )
    items: List[BulkImportItem] = []
    for row in reader:
        try:
            item = BulkImportItem(
                ticker=row["ticker"].strip(),
                market=row["market"].strip(),
                name_en=row.get("name_en", "").strip() or None,
                name_zh_tw=row.get("name_zh_tw", "").strip() or None,
                translation_status=row.get("translation_status", "auto").strip() or "auto"
            )
            items.append(item)
        except Exception:
            pass  # Skip invalid rows
    if not items:
        raise HTTPException(status_code=400, detail="No valid items in CSV")
    service = TranslationService(db)
    imported, updated, errors = service.bulk_import(items, updated_by="admin")
    return BulkImportResponse(imported=imported, updated=updated, errors=errors)


@router.post("/translations/bulk-json", response_model=BulkImportResponse)
async def bulk_import_json(
    items: List[BulkImportItem],
    db: Session = Depends(get_session),
    admin: AdminAccess = Depends(get_translation_access)
):
    """Bulk import translations from JSON array.
    Accepts an admin JWT or the TINBOKER_WRITE_TOKEN (backfill agent writes)."""
    if not items:
        raise HTTPException(status_code=400, detail="No items provided")
    service = TranslationService(db)
    imported, updated, errors = service.bulk_import(items, updated_by="admin")
    return BulkImportResponse(imported=imported, updated=updated, errors=errors)


