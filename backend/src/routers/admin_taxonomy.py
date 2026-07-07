"""Admin API for sector taxonomy writes and audit reads."""

from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.auth.admin_auth import AdminAccess, get_admin_access
from src.cache.redis_client import cache_delete_pattern_all_envs
from src.database.models import (
    TagRegistry,
    TagRegistryAudit,
    TaxonomyChangelog,
    TaxonomyDraft,
    TaxonomyVersion,
)
from src.database.postgres import get_session
from src.services.taxonomy_validation import (
    TaxonomyValidationError,
    validate_taxonomy,
)
from src.tag_registry import KIND_SECTOR, TIER_HIDDEN, TIER_TRENDING

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/taxonomy", tags=["admin-taxonomy"])

BOT_ACTORS = {"bot:reasons-fill", "bot:import"}
SECTOR_COMPARE_FIELDS = (
    "display_name",
    "exposure_type",
    "icon_id",
    "color_hex",
    "description",
    "group",
    "aliases",
    "members",
    "tier",
)
STRUCTURAL_FIELDS = {"exposure_type", "group"}


class SectorPayload(BaseModel):
    exposure_id: str | None = Field(default=None, min_length=1, max_length=120)
    display_name: str | None = None
    exposure_type: str | None = None
    icon_id: str | None = None
    color_hex: str | None = None
    description: str | None = None
    group: str | None = None
    aliases: list[str] | None = None
    members: list[dict[str, Any]] | None = None
    tier: str | None = None
    redirect_to: str | None = None


class SingleSectorUpsert(BaseModel):
    display_name: str | None = None
    exposure_type: str | None = None
    icon_id: str | None = None
    color_hex: str | None = None
    description: str | None = None
    group: str | None = None
    aliases: list[str] | None = None
    members: list[dict[str, Any]] | None = None
    tier: str | None = None
    redirect_to: str | None = None
    changelog_entry: str | None = None
    rationale: str | None = None


class BulkTaxonomyRequest(BaseModel):
    """Bulk taxonomy draft.

    Drafts live in a dedicated table with a status column. This is smaller than
    putting draft rows into tag_registry because the public read table stays
    current-state-only and every hot read avoids status filtering.
    """

    sectors: list[SectorPayload] = Field(default_factory=list)
    redirects: dict[str, str] = Field(default_factory=dict)
    full: bool = False
    actor: str | None = None
    entry: str | None = None
    rationale: str | None = None


class DiffReport(BaseModel):
    added: int
    removed: int
    changed: int
    samples: list[dict[str, Any]] = Field(default_factory=list)


class DraftResponse(BaseModel):
    draft_id: int
    status: str
    actor: str
    diff: DiffReport


class PublishResponse(BaseModel):
    draft_id: int
    status: str
    actor: str
    diff: DiffReport
    skipped: list[dict[str, Any]] = Field(default_factory=list)
    version: int | None = None


class AuditResponse(BaseModel):
    items: list[dict[str, Any]]


def admin_actor(email: str) -> str:
    return f"admin:{email}"


def create_taxonomy_draft(
    db: Session,
    body: BulkTaxonomyRequest,
    *,
    actor: str,
) -> tuple[TaxonomyDraft, DiffReport]:
    current, redirects = load_taxonomy_state(db)
    proposed, proposed_redirects = state_after_payload(current, redirects, body)
    _validate_or_422(proposed, proposed_redirects, previous=current)
    diff = diff_taxonomy(current, redirects, proposed, proposed_redirects)
    draft = TaxonomyDraft(
        status="draft",
        payload=body.model_dump(mode="json", exclude_unset=True),
        diff=diff.model_dump(mode="json"),
        actor=actor,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft, diff


def publish_taxonomy_draft(
    db: Session,
    draft_id: int,
    *,
    force: bool = False,
) -> PublishResponse:
    draft = db.get(TaxonomyDraft, draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    published_at = datetime.utcnow()
    if db.get_bind().dialect.name == "postgresql":
        result = db.execute(
            text(
                "UPDATE taxonomy_drafts "
                "SET status='published', published_at=now(), updated_at=now() "
                "WHERE id=:id AND status='draft'"
            ),
            {"id": draft_id},
        )
    else:
        result = db.execute(
            text(
                "UPDATE taxonomy_drafts "
                "SET status='published', published_at=:published_at, updated_at=:published_at "
                "WHERE id=:id AND status='draft'"
            ),
            {"id": draft_id, "published_at": published_at},
        )
    if result.rowcount != 1:
        raise HTTPException(status_code=409, detail="already published or publishing")

    body = BulkTaxonomyRequest.model_validate(draft.payload)
    current, redirects = load_taxonomy_state(db)
    proposed, proposed_redirects = state_after_payload(current, redirects, body)
    _validate_or_422(proposed, proposed_redirects, previous=current)
    diff = diff_taxonomy(current, redirects, proposed, proposed_redirects)
    structural = has_structural_change(current, redirects, proposed, proposed_redirects)

    _set_audit_context(db, draft.actor, f"taxonomy draft {draft.id} publish")
    try:
        skipped = apply_taxonomy_state(
            db,
            proposed,
            proposed_redirects,
            actor=draft.actor,
            force=force,
        )
    except ReasonsFillConflictError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "message": "reasons-fill draft conflicts with protected sector members",
                "conflicting_exposure_ids": exc.exposure_ids,
            },
        ) from exc

    version = None
    current_version = _taxonomy_version_number(db)
    if current_version < 1 or (structural and (diff.added or diff.removed or diff.changed)):
        version = bump_taxonomy_version(
            db,
            actor=draft.actor,
            entry=body.entry or f"Publish taxonomy draft {draft.id}",
            rationale=body.rationale,
        )

    draft.status = "published"
    draft.published_at = published_at
    draft.diff = diff.model_dump(mode="json")
    db.commit()
    return PublishResponse(
        draft_id=draft.id,
        status=draft.status,
        actor=draft.actor,
        diff=diff,
        skipped=skipped,
        version=version,
    )


@router.put("/sectors/{exposure_id}")
async def upsert_sector(
    exposure_id: str,
    body: SingleSectorUpsert,
    admin: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    """Direct admin upsert for one published sector row."""
    actor = admin_actor(admin.email)
    current, redirects = load_taxonomy_state(db)
    payload = SectorPayload(
        exposure_id=exposure_id,
        **body.model_dump(exclude={"changelog_entry", "rationale"}, exclude_unset=True),
    )
    bulk = BulkTaxonomyRequest(sectors=[payload], full=False)
    proposed, proposed_redirects = state_after_payload(current, redirects, bulk)
    _validate_or_422(proposed, proposed_redirects, previous=current)
    structural = has_structural_change(current, redirects, proposed, proposed_redirects)

    _set_audit_context(db, actor, f"single-sector upsert {exposure_id}")
    skipped = apply_taxonomy_state(
        db,
        proposed,
        proposed_redirects,
        actor=actor,
        force=True,
    )
    version = None
    if structural:
        version = bump_taxonomy_version(
            db,
            actor=actor,
            entry=body.changelog_entry or f"Upsert sector {exposure_id}",
            rationale=body.rationale,
        )
    db.commit()
    await invalidate_taxonomy_caches()
    return {
        "exposure_id": exposure_id,
        "status": "published",
        "skipped": skipped,
        "version": version,
    }


@router.post("/bulk", response_model=DraftResponse)
async def create_bulk_draft(
    body: BulkTaxonomyRequest,
    admin: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    actor = resolve_bulk_actor(admin, body.actor)
    draft, diff = create_taxonomy_draft(db, body, actor=actor)
    return DraftResponse(
        draft_id=draft.id,
        status=draft.status,
        actor=draft.actor,
        diff=diff,
    )


@router.post("/bulk/{draft_id}/publish", response_model=PublishResponse)
async def publish_bulk_draft(
    draft_id: int,
    force: bool = Query(default=False),
    admin: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    _ = admin
    response = publish_taxonomy_draft(db, draft_id, force=force)
    await invalidate_taxonomy_caches()
    return response


@router.get("/audit", response_model=AuditResponse)
async def get_taxonomy_audit(
    exposure_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=5000),
    admin: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    _ = admin
    q = db.query(TagRegistryAudit)
    if exposure_id:
        q = q.filter(TagRegistryAudit.exposure_id == exposure_id)
    rows = q.order_by(TagRegistryAudit.at.desc(), TagRegistryAudit.id.desc()).limit(limit).all()
    return AuditResponse(items=[_audit_row(row) for row in rows])


@router.get("/snapshot")
async def get_taxonomy_snapshot(
    admin: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    _ = admin
    sectors, redirects = load_taxonomy_state(db)
    version = db.get(TaxonomyVersion, 1)
    changelog = (
        db.query(TaxonomyChangelog)
        .order_by(TaxonomyChangelog.version.desc(), TaxonomyChangelog.id.desc())
        .limit(100)
        .all()
    )
    return {
        "version": version.version if version else 0,
        "sectors": [sectors[k] for k in sorted(sectors)],
        "redirects": dict(sorted(redirects.items())),
        "changelog": [
            {
                "version": row.version,
                "entry": row.entry,
                "rationale": row.rationale,
                "actor": row.actor,
                "at": row.at.isoformat() if row.at else None,
            }
            for row in changelog
        ],
    }


def resolve_bulk_actor(admin: AdminAccess, requested: str | None) -> str:
    if not requested:
        return admin_actor(admin.email)
    if requested in BOT_ACTORS:
        return requested
    if requested.startswith("bot:"):
        raise HTTPException(status_code=403, detail=f"Bot actor not allowed: {requested}")
    return admin_actor(admin.email)


def load_taxonomy_state(db: Session) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    rows = db.query(TagRegistry).filter(TagRegistry.kind == KIND_SECTOR).all()
    sectors: dict[str, dict[str, Any]] = {}
    redirects: dict[str, str] = {}
    for row in rows:
        if not row.exposure_id:
            continue
        if row.redirect_to:
            redirects[str(row.exposure_id)] = str(row.redirect_to)
            continue
        sectors[str(row.exposure_id)] = row_to_sector(row)
    return sectors, redirects


def state_after_payload(
    current: dict[str, dict[str, Any]],
    redirects: dict[str, str],
    body: BulkTaxonomyRequest,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    proposed = {} if body.full else deepcopy(current)
    proposed_redirects = dict(body.redirects or {}) if body.full else dict(redirects)
    if not body.full:
        proposed_redirects.update(body.redirects or {})

    for item in body.sectors:
        raw = item.model_dump(exclude_unset=True)
        eid = str(raw.pop("exposure_id", "") or "").strip()
        if not eid:
            raise HTTPException(status_code=422, detail={"offenders": ["missing exposure_id"]})
        redirect_to = raw.pop("redirect_to", None)
        if redirect_to:
            proposed.pop(eid, None)
            proposed_redirects[eid] = str(redirect_to)
            continue

        base = deepcopy(proposed.get(eid, {}))
        base["exposure_id"] = eid
        if "display_name" not in base:
            base["display_name"] = eid
        if "tier" not in base:
            base["tier"] = TIER_TRENDING
        for key, value in raw.items():
            if key == "group":
                base["group"] = value
            else:
                base[key] = value
        proposed[eid] = base
        proposed_redirects.pop(eid, None)

    for old in list(proposed_redirects):
        proposed.pop(old, None)
    return proposed, proposed_redirects


def row_to_sector(row: TagRegistry) -> dict[str, Any]:
    return {
        "exposure_id": row.exposure_id,
        "display_name": row.display_zh,
        "exposure_type": row.exposure_type,
        "icon_id": row.icon_id,
        "color_hex": row.color_hex,
        "description": row.description,
        "group": row.parent_id,
        "aliases": row.aliases or [],
        "members": row.members or [],
        "tier": row.tier,
    }


def diff_taxonomy(
    current: dict[str, dict[str, Any]],
    redirects: dict[str, str],
    proposed: dict[str, dict[str, Any]],
    proposed_redirects: dict[str, str],
) -> DiffReport:
    before = _state_items(current, redirects)
    after = _state_items(proposed, proposed_redirects)
    before_keys = set(before)
    after_keys = set(after)
    added = sorted(after_keys - before_keys)
    removed = sorted(before_keys - after_keys)
    changed = sorted(k for k in before_keys & after_keys if before[k] != after[k])
    samples: list[dict[str, Any]] = []
    for key in added[:10]:
        samples.append({"key": key, "action": "added", "after": after[key]})
    for key in removed[: max(0, 10 - len(samples))]:
        samples.append({"key": key, "action": "removed", "before": before[key]})
    for key in changed[: max(0, 10 - len(samples))]:
        samples.append({"key": key, "action": "changed", "before": before[key], "after": after[key]})
    return DiffReport(
        added=len(added),
        removed=len(removed),
        changed=len(changed),
        samples=samples,
    )


def has_structural_change(
    current: dict[str, dict[str, Any]],
    redirects: dict[str, str],
    proposed: dict[str, dict[str, Any]],
    proposed_redirects: dict[str, str],
) -> bool:
    if set(current) != set(proposed):
        return True
    if redirects != proposed_redirects:
        return True
    for eid, before in current.items():
        after = proposed.get(eid) or {}
        if any(before.get(field) != after.get(field) for field in STRUCTURAL_FIELDS):
            return True
    return False


def apply_taxonomy_state(
    db: Session,
    proposed: dict[str, dict[str, Any]],
    redirects: dict[str, str],
    *,
    actor: str,
    force: bool,
) -> list[dict[str, Any]]:
    rows = {
        row.exposure_id: row
        for row in db.query(TagRegistry).filter(TagRegistry.kind == KIND_SECTOR).all()
        if row.exposure_id
    }
    skipped: list[dict[str, Any]] = []
    reasons_fill_conflicts: list[str] = []

    for eid, row in list(rows.items()):
        if eid in proposed or eid in redirects:
            continue
        protected = _admin_owned_fields(row)
        if _bot_actor(actor) and not force and protected:
            skipped.append({"exposure_id": eid, "fields": protected})
            continue
        db.delete(row)

    for eid, sector in proposed.items():
        row = rows.get(eid)
        if row is None:
            row = TagRegistry(
                slug=eid,
                display_zh="",
                kind=KIND_SECTOR,
                exposure_id=eid,
            )
            db.add(row)
        skipped_fields, reasons_fill_conflict = _apply_sector_fields(
            row,
            sector,
            actor,
            force=force,
        )
        if reasons_fill_conflict:
            reasons_fill_conflicts.append(eid)
        if skipped_fields:
            skipped.append({"exposure_id": eid, "fields": skipped_fields})

    if reasons_fill_conflicts:
        raise ReasonsFillConflictError(reasons_fill_conflicts)

    for old, new in redirects.items():
        row = rows.get(old)
        if row is None:
            row = TagRegistry(
                slug=old,
                display_zh="",
                kind=KIND_SECTOR,
                exposure_id=old,
            )
            db.add(row)
        skipped_fields = _apply_redirect_fields(row, new, actor, force=force)
        if skipped_fields:
            skipped.append({"exposure_id": old, "fields": skipped_fields})
    return skipped


def bump_taxonomy_version(
    db: Session,
    *,
    actor: str,
    entry: str,
    rationale: str | None,
) -> int:
    version = db.get(TaxonomyVersion, 1)
    if version is None:
        version = TaxonomyVersion(id=1, version=0)
        db.add(version)
        db.flush()
    version.version += 1
    version.updated_by = actor
    changelog = TaxonomyChangelog(
        version=version.version,
        entry=entry,
        rationale=rationale,
        actor=actor,
    )
    db.add(changelog)
    return version.version


def _taxonomy_version_number(db: Session) -> int:
    version = db.get(TaxonomyVersion, 1)
    return version.version if version else 0


def _state_items(
    sectors: dict[str, dict[str, Any]],
    redirects: dict[str, str],
) -> dict[str, Any]:
    out: dict[str, Any] = {
        f"sector:{eid}": _compare_sector(sector)
        for eid, sector in sectors.items()
    }
    out.update({f"redirect:{old}": {"to": new} for old, new in redirects.items()})
    return out


def _compare_sector(sector: dict[str, Any]) -> dict[str, Any]:
    out = {"exposure_id": sector.get("exposure_id")}
    for field in SECTOR_COMPARE_FIELDS:
        value = sector.get(field)
        if field in {"aliases", "members"}:
            value = value or []
        out[field] = value
    return out


OWNED_FIELDS = (
    "members",
    "aliases",
    "display_zh",
    "description",
    "icon_id",
    "color_hex",
    "exposure_type",
    "parent_id",
    "redirect_to",
    "tier",
)


class ReasonsFillConflictError(RuntimeError):
    def __init__(self, exposure_ids: list[str]) -> None:
        self.exposure_ids = exposure_ids
        super().__init__("reasons-fill draft no longer matches protected members")


def _apply_sector_fields(
    row: TagRegistry,
    sector: dict[str, Any],
    actor: str,
    *,
    force: bool,
) -> tuple[list[str], bool]:
    changed = _sector_field_values(sector)
    changed.update({
        "redirect_to": None,
        "tier": sector.get("tier") or TIER_TRENDING,
    })
    changed_fields: list[str] = []
    owner_fields: list[str] = []
    skipped_fields: list[str] = []
    reasons_fill_conflict = False

    row.slug = str(sector.get("exposure_id") or row.exposure_id or row.slug)
    row.kind = KIND_SECTOR
    row.exposure_id = str(sector.get("exposure_id") or row.exposure_id or row.slug)
    for field, value in changed.items():
        current = _normal_field_value(getattr(row, field))
        proposed = _normal_field_value(value)
        if current == proposed:
            continue
        if _field_protected(row, field, actor, force):
            if field == "members" and actor == "bot:reasons-fill":
                merged = _merge_reason_fill_only(row.members or [], value or [])
                if merged is not None:
                    row.members = merged
                    changed_fields.append(field)
                    continue
                reasons_fill_conflict = True
            skipped_fields.append(field)
            continue
        setattr(row, field, value)
        changed_fields.append(field)
        owner_fields.append(field)

    if changed_fields:
        _record_field_owners(row, actor, owner_fields)
        row.updated_by = actor
    return skipped_fields, reasons_fill_conflict


def _apply_redirect_fields(
    row: TagRegistry,
    redirect_to: str,
    actor: str,
    *,
    force: bool,
) -> list[str]:
    row.slug = str(row.exposure_id or row.slug)
    row.display_zh = row.display_zh or row.slug
    row.kind = KIND_SECTOR
    row.exposure_id = str(row.exposure_id or row.slug)
    changed = {
        "tier": TIER_HIDDEN,
        "redirect_to": redirect_to,
        "members": None,
        "parent_id": None,
    }
    changed_fields: list[str] = []
    skipped_fields: list[str] = []
    for field, value in changed.items():
        current = _normal_field_value(getattr(row, field))
        proposed = _normal_field_value(value)
        if current == proposed:
            continue
        if _field_protected(row, field, actor, force):
            skipped_fields.append(field)
            continue
        setattr(row, field, value)
        changed_fields.append(field)

    if changed_fields:
        _record_field_owners(row, actor, changed_fields)
        row.updated_by = actor
    return skipped_fields


def _sector_field_values(sector: dict[str, Any]) -> dict[str, Any]:
    return {
        "display_zh": str(sector.get("display_name") or sector.get("exposure_id") or ""),
        "exposure_type": sector.get("exposure_type"),
        "icon_id": sector.get("icon_id"),
        "color_hex": sector.get("color_hex"),
        "description": sector.get("description"),
        "parent_id": sector.get("group"),
        "aliases": sector.get("aliases") or [],
        "members": sector.get("members") or [],
    }


def _record_field_owners(row: TagRegistry, actor: str, fields: list[str]) -> None:
    owners = dict(row.field_owners or {})
    for field in fields:
        if field in OWNED_FIELDS:
            owners[field] = actor
    row.field_owners = owners


def _field_owner(row: TagRegistry, field: str) -> str | None:
    owners = row.field_owners or {}
    if field in owners:
        owner = owners.get(field)
        return str(owner) if owner else None
    if owners:
        return None
    return str(row.updated_by) if row.updated_by else None


def _field_protected(row: TagRegistry, field: str, actor: str, force: bool) -> bool:
    if force or not _bot_actor(actor):
        return False
    owner = _field_owner(row, field)
    return bool(owner and owner.startswith("admin:"))


def _admin_owned_fields(row: TagRegistry) -> list[str]:
    owners = row.field_owners or {}
    fields = [
        field
        for field in OWNED_FIELDS
        if str(owners.get(field) or "").startswith("admin:")
    ]
    if not fields and row.updated_by and str(row.updated_by).startswith("admin:"):
        fields = list(OWNED_FIELDS)
    return fields


def _bot_actor(actor: str) -> bool:
    return actor in BOT_ACTORS or actor.startswith("bot:")


def _normal_field_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, list):
        return value or []
    return value


def _member_key(member: dict[str, Any]) -> tuple[str, str]:
    return (str(member.get("ticker") or "").upper(), str(member.get("market") or "").upper())


def _without_reason(member: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in member.items() if key != "reason"}


def _merge_reason_fill_only(
    existing_members: list[dict[str, Any]],
    incoming_members: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    if len(existing_members) != len(incoming_members):
        return None
    merged: list[dict[str, Any]] = []
    filled_any = False
    for existing, incoming in zip(existing_members, incoming_members, strict=True):
        if _member_key(existing) != _member_key(incoming):
            return None
        if _without_reason(existing) != _without_reason(incoming):
            return None
        existing_reason = existing.get("reason")
        incoming_reason = incoming.get("reason")
        if existing_reason:
            if incoming_reason and incoming_reason != existing_reason:
                return None
            merged.append(dict(existing))
            continue
        item = dict(existing)
        if incoming_reason:
            item["reason"] = incoming_reason
            filled_any = True
        merged.append(item)
    return merged if filled_any else None


def _validate_or_422(
    sectors: dict[str, dict[str, Any]],
    redirects: dict[str, str],
    *,
    previous: dict[str, dict[str, Any]] | None = None,
) -> None:
    try:
        validate_taxonomy(
            list(sectors.values()),
            redirects,
            enforce=True,
            previous_sectors=list((previous or {}).values()),
        )
    except TaxonomyValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": exc.rule, "offenders": exc.offenders},
        ) from exc


def _set_audit_context(db: Session, actor: str, note: str | None = None) -> None:
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return
    db.execute(text("SET LOCAL app.taxonomy_actor = :actor"), {"actor": actor})
    db.execute(text("SET LOCAL app.taxonomy_note = :note"), {"note": note or ""})


def _audit_row(row: TagRegistryAudit) -> dict[str, Any]:
    return {
        "id": row.id,
        "tag_registry_id": row.tag_registry_id,
        "exposure_id": row.exposure_id,
        "action": row.action,
        "actor": row.actor,
        "note": row.note,
        "before": row.before,
        "after": row.after,
        "at": row.at.isoformat() if row.at else None,
    }


async def invalidate_taxonomy_caches() -> None:
    try:
        from src.data.sector_reasons import invalidate_reasons_cache
        from src.data.sector_visuals import _metadata

        invalidate_reasons_cache()
        _metadata.cache_clear()
    except Exception as exc:  # noqa: BLE001
        logger.warning("taxonomy cache: local invalidation failed: %s", exc)
    for pattern in ("sector:*", "sectors:*", "tags:*"):
        try:
            await cache_delete_pattern_all_envs(pattern)
        except Exception as exc:  # noqa: BLE001
            logger.warning("taxonomy cache: Redis invalidation failed for %s: %s", pattern, exc)
