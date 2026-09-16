"""Admin: see and send the 每日一集 (one episode summary a day to 方格子).

Non-production only (mounted under the ``is_production`` gate, like every
``/api/admin/*`` router).

  GET  /api/admin/daily-pick/{day}                — which episode tonight would send, and why
  POST /api/admin/daily-pick/{day}/publish-vocus  — dry_run=true by default; publish=true
                                                    goes public, same as the nightly loop

The nightly loop (``services.daily_pick.run_periodic_daily_pick``) sends on its own; this
is for a re-run, a backfill, or checking the pick before 20:40.
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from src.auth.admin_auth import AdminAccess, get_admin_access
from src.services.daily_pick import build_daily_pick, publish_daily_pick

router = APIRouter(prefix="/api/admin/daily-pick", tags=["syndication", "admin"])


def _day(day: str) -> date:
    try:
        return date.fromisoformat(day)
    except ValueError:
        raise HTTPException(status_code=400, detail="day must look like 2026-09-12")


@router.get("/{day}")
async def preview_daily_pick(day: str, _: AdminAccess = Depends(get_admin_access)) -> dict:
    return await build_daily_pick(_day(day))


@router.post("/{day}/publish-vocus")
async def publish_pick(
    day: str,
    dry_run: bool = Query(True, description="Convert and report; nothing reaches vocus"),
    publish: bool = Query(False, description="Go public instead of leaving a vocus draft"),
    _: AdminAccess = Depends(get_admin_access),
) -> dict:
    return await publish_daily_pick(_day(day), dry_run=dry_run, publish=publish)
