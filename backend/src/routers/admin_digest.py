"""Admin: preview and publish the 每日精選 to 方格子.

Non-production only (mounted under the ``is_production`` gate, like every
``/api/admin/*`` router).

  GET  /api/admin/digest/{day}                 — the rendered digest, for review
  POST /api/admin/digest/{day}/publish-vocus   — dry_run=true by default; as_draft=false
                                                 goes public, same as the nightly loop

The nightly loop (``services.daily_digest.run_periodic_daily_digest``) publishes on its
own; this endpoint is for a re-run, a backfill, or reading what tonight will say.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from src.auth.admin_auth import AdminAccess, get_admin_access
from src.services.daily_digest import build_daily_digest, publish_daily_digest

router = APIRouter(prefix="/api/admin/digest", tags=["digest", "admin"])


def _day(day: str) -> date:
    try:
        return date.fromisoformat(day)
    except ValueError:
        raise HTTPException(status_code=400, detail="day must look like 2026-09-12")


@router.get("/{day}")
async def preview_digest(day: str, _: AdminAccess = Depends(get_admin_access)) -> dict:
    digest = await build_daily_digest(_day(day))
    if digest is None:
        raise HTTPException(status_code=404, detail=f"no episodes on {day}")
    return digest


@router.post("/{day}/publish-vocus")
async def publish_digest(
    day: str,
    dry_run: bool = Query(True, description="Convert and report; nothing reaches vocus"),
    as_draft: bool = Query(False, description="Leave the article in the vocus publish wizard"),
    _: AdminAccess = Depends(get_admin_access),
) -> dict:
    return await publish_daily_digest(_day(day), dry_run=dry_run, as_draft=as_draft)
