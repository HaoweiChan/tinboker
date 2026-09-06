"""Admin: preview and publish the paid weekly to 方格子.

Non-production only (mounted under the ``is_production`` gate in main.py, like every
``/api/admin/*`` router). Two calls:

  GET  /api/admin/weekly/{week}/paid                  — the rendered issue, for review
  POST /api/admin/weekly/{week}/publish-vocus         — dry_run=true by default;
                                                        as_draft=true leaves it in the
                                                        wizard, paid is always on

Publishing goes through the same claim-then-publish ledger as episode syndication
(``routers.social._syndicate_once``) under the key ``weekly:{week}``, so a second
call — or a second environment — cannot mint a duplicate article.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from src.auth.admin_auth import AdminAccess, get_admin_access
from src.config import settings
from src.routers.social import _syndicate_once
from src.routers.weekly import week_bounds
from src.services import vocus_publisher
from src.services.paid_weekly import build_paid_weekly

router = APIRouter(prefix="/api/admin/weekly", tags=["weekly", "admin"])

VOCUS_TAGS = ["台股", "Podcast", "週報", "聽播客"]


async def _issue_or_404(week: str) -> dict:
    try:
        week_bounds(week)
    except ValueError:
        raise HTTPException(status_code=400, detail="week must look like 2026-W36")
    issue = await build_paid_weekly(week)
    if issue is None:
        raise HTTPException(status_code=404, detail=f"no episodes in {week}")
    return issue


@router.get("/{week}/paid")
async def preview_paid_weekly(week: str, _: AdminAccess = Depends(get_admin_access)) -> dict:
    return await _issue_or_404(week)


@router.post("/{week}/publish-vocus")
async def publish_paid_weekly(
    week: str,
    dry_run: bool = Query(True, description="Convert and report; nothing reaches vocus"),
    as_draft: bool = Query(True, description="Leave the article in the vocus publish wizard"),
    _: AdminAccess = Depends(get_admin_access),
) -> dict:
    issue = await _issue_or_404(week)
    key = f"weekly:{week}"
    result = await _syndicate_once("vocus", key, lambda: vocus_publisher.publish_markdown(
        key, issue["title"], issue["markdown"],
        canonical_url=f"{settings.site_url.rstrip('/')}/weekly/{week}",
        abstract=issue["excerpt"], tags=VOCUS_TAGS,
        as_draft=as_draft, dry_run=dry_run, paid=True,
    ), dry_run)
    return {**result, "week": week, "stats": issue["stats"]}
