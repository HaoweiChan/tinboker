"""SEO: a dynamic episode sitemap + Google Search Console monitoring.

* ``GET /sitemap.xml`` — public, no auth. Lists the site's static routes plus every
  recent episode permalink so Google can discover episode pages. Submit this URL in
  Search Console (or proxy it at ``tinboker.com/sitemap.xml`` via Cloudflare) — it
  supersedes the hand-maintained static sitemap in ``frontend/public``.
* ``GET /api/admin/seo/overview`` / ``POST /api/admin/seo/refresh`` — admin-only,
  reads Search Analytics (clicks / impressions / CTR / position by query and page).
"""

import logging
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from src.auth.admin_auth import AdminAccess, get_admin_access
from src.config import settings
from src.services.podcast import PodcastService
from src.services.search_console_service import SearchConsoleService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["seo"])

podcast_service = PodcastService()

# Public top-level routes that should always be in the sitemap (mirrors the routes
# in frontend/src/App.tsx). Episodes are appended dynamically below.
STATIC_PATHS = [
    ("/", "1.0", "daily"),
    ("/podcaster", "0.8", "weekly"),
    ("/stock", "0.8", "weekly"),
    ("/topics", "0.8", "weekly"),
    ("/articles", "0.7", "weekly"),
    ("/about", "0.5", "monthly"),
    ("/contact", "0.5", "monthly"),
    ("/disclaimer", "0.3", "yearly"),
]


def _url_entry(loc: str, lastmod: str | None, changefreq: str, priority: str) -> str:
    parts = ["  <url>", f"    <loc>{escape(loc)}</loc>"]
    if lastmod:
        parts.append(f"    <lastmod>{lastmod}</lastmod>")
    parts.append(f"    <changefreq>{changefreq}</changefreq>")
    parts.append(f"    <priority>{priority}</priority>")
    parts.append("  </url>")
    return "\n".join(parts)


def _lastmod(episode) -> str | None:
    ms = getattr(episode, "released_at_ms", None) or getattr(episode, "created_time", None)
    if not ms:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()
    except (ValueError, OSError, OverflowError):
        return None


@router.get("/sitemap.xml")
async def sitemap(
    limit: int = Query(default=1000, ge=1, le=5000, description="Max episodes to include"),
):
    """Dynamic XML sitemap: static routes + recent episode permalinks."""
    base = settings.site_url.rstrip("/")
    entries = [_url_entry(f"{base}{path}", None, freq, prio) for path, prio, freq in STATIC_PATHS]

    try:
        episodes = await podcast_service.get_recent_episodes(limit=limit, enrich_content=False)
        for ep in episodes:
            ep_id = getattr(ep, "id", None) or (ep.get("id") if isinstance(ep, dict) else None)
            if not ep_id:
                continue
            entries.append(
                _url_entry(f"{base}/episode/{ep_id}", _lastmod(ep), "monthly", "0.7")
            )
    except Exception as e:
        # A sitemap with just the static routes still beats a 500 to Googlebot.
        logger.warning("Sitemap episode enumeration failed: %s", e)

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(entries)
        + "\n</urlset>\n"
    )
    return Response(
        content=xml,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/api/admin/seo/overview")
async def seo_overview(
    days: int = Query(default=28, ge=1, le=480),
    refresh: bool = Query(default=False, description="Pull live from GSC instead of cache"),
    _: AdminAccess = Depends(get_admin_access),
):
    """Search Console overview — cached by default, live when ``refresh=true``."""
    svc = SearchConsoleService()
    if not svc.is_configured:
        return {"configured": False, "detail": "Set GSC_SITE_URL to enable SEO monitoring."}
    try:
        data = await svc.refresh_cache(days=days) if refresh else (
            SearchConsoleService.get_cached() or await svc.refresh_cache(days=days)
        )
        return {"configured": True, **data}
    except Exception as e:
        logger.exception("GSC overview failed")
        raise HTTPException(status_code=502, detail=f"Search Console query failed: {e}")


@router.post("/api/admin/seo/refresh")
async def seo_refresh(
    days: int = Query(default=28, ge=1, le=480),
    _: AdminAccess = Depends(get_admin_access),
):
    """Force a fresh Search Console pull and cache it."""
    svc = SearchConsoleService()
    if not svc.is_configured:
        raise HTTPException(status_code=400, detail="Set GSC_SITE_URL to enable SEO monitoring.")
    try:
        return {"configured": True, **await svc.refresh_cache(days=days)}
    except Exception as e:
        logger.exception("GSC refresh failed")
        raise HTTPException(status_code=502, detail=f"Search Console refresh failed: {e}")
