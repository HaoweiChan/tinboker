"""Admin: the 週報素材 (structured fact base) a paid weekly issue is written from.

Non-production only (mounted under the ``is_production`` gate, like every
``/api/admin/*`` router).

  GET /api/admin/weekly-brief/{week}            — JSON: topics, observations, movers, episodes
  GET /api/admin/weekly-brief/{week}.md         — the same as the markdown a writer works from

Data only. The prose is written from this by a model or a person, fact-checked against
it, and published by hand.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse

from src.auth.admin_auth import AdminAccess, get_admin_access
from src.routers.weekly import week_bounds
from src.services.weekly_brief import build_weekly_brief

router = APIRouter(prefix="/api/admin/weekly-brief", tags=["weekly", "admin"])


async def _brief_or_404(week: str) -> dict:
    try:
        week_bounds(week)
    except ValueError:
        raise HTTPException(status_code=400, detail="week must look like 2026-W37")
    brief = await build_weekly_brief(week)
    if brief is None:
        raise HTTPException(status_code=404, detail=f"no episodes in {week}")
    return brief


@router.get("/{week}.md", response_class=PlainTextResponse)
async def weekly_brief_markdown(week: str, _: AdminAccess = Depends(get_admin_access)) -> str:
    return (await _brief_or_404(week))["markdown"]


@router.get("/{week}")
async def weekly_brief(week: str, _: AdminAccess = Depends(get_admin_access)) -> dict:
    return await _brief_or_404(week)
