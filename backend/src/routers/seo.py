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
from urllib.parse import quote
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from src.auth.admin_auth import AdminAccess, get_admin_access
from src.cache.redis_client import cache_get, cache_set
from src.config import settings
from src.database.postgres import get_session
from src.services.article_service import ArticleService
from src.services.podcast import PodcastService
from src.services.search_console_service import SearchConsoleService
from src.tag_registry import hidden_sector_exposure_ids, served_sector_exposure_ids

logger = logging.getLogger(__name__)

router = APIRouter(tags=["seo"])
# Admin-only SEO routes live on a separate router so main.py can skip mounting them in
# production (the dashboard is dev-only) while /sitemap.xml stays public everywhere.
admin_router = APIRouter(tags=["seo", "admin"])

podcast_service = PodcastService()

# Public top-level routes that should always be in the sitemap (mirrors the routes
# in frontend/src/App.tsx). Episodes are appended dynamically below.
MIN_TICKER_EPISODES = 2

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


def _date_from_ms(ms) -> str | None:
    if not ms:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()
    except (ValueError, OSError, OverflowError, TypeError):
        return None


def _lastmod(episode) -> str | None:
    ms = getattr(episode, "released_at_ms", None) or getattr(episode, "created_time", None)
    return _date_from_ms(ms)


@router.get("/sitemap.xml")
async def sitemap(
    limit: int = Query(default=1000, ge=1, le=5000, description="Max episodes to include"),
    db: Session = Depends(get_session),
):
    """Dynamic XML sitemap: static routes + episode / article / stock / podcaster /
    sector permalinks. Topic-tag pages are excluded on purpose — see below.

    Each content source is enumerated in its own try/except, so one failing source
    (Firestore hiccup, empty table) degrades to a partial sitemap rather than a 500
    to Googlebot. The assembled XML is cached in Redis for an hour; the per-source
    service calls are themselves cached, and the CDN edge caches the response.
    """
    cache_key = f"sitemap:xml:v5:{limit}"
    cached = await cache_get(cache_key)
    if cached:
        return Response(content=cached, media_type="application/xml",
                        headers={"Cache-Control": "public, max-age=3600"})

    base = settings.site_url.rstrip("/")
    entries = [_url_entry(f"{base}{path}", None, freq, prio) for path, prio, freq in STATIC_PATHS]

    # Episodes — get_recent_episodes already applies the release scoping
    # (RELEASE_PODCAST_LANGUAGES / RELEASE_EPISODE_MAX_AGE_DAYS), so we never list a
    # page that 404s for users. The canonical episode URL has no query string.
    # The same scoped list decides which /stock pages exist (below), so one fetch
    # serves both families and they can never disagree about the window.
    ticker_episodes: dict[str, int] = {}
    try:
        for ep in await podcast_service.get_recent_episodes(limit=limit, enrich_content=False):
            ep_id = getattr(ep, "id", None) or (ep.get("id") if isinstance(ep, dict) else None)
            if ep_id:
                entries.append(_url_entry(f"{base}/episode/{ep_id}", _lastmod(ep), "monthly", "0.7"))
            for tk in getattr(ep, "related_tickers", None) or []:
                ticker_episodes[str(tk)] = ticker_episodes.get(str(tk), 0) + 1
    except Exception as e:
        logger.warning("Sitemap episode enumeration failed: %s", e)

    # Published articles
    try:
        for art in ArticleService(db).list_articles(status="published", limit=1000):
            lastmod = art.published_at.date().isoformat() if art.published_at else None
            entries.append(_url_entry(f"{base}/article/{quote(art.slug)}", lastmod, "weekly", "0.6"))
    except Exception as e:
        logger.warning("Sitemap article enumeration failed: %s", e)

    # Podcaster channels — URL path is the (encoded) podcast name, matching the
    # frontend's /podcaster/${encodeURIComponent(name)} links.
    try:
        for pod in await podcast_service.get_all_podcasts(limit=500):
            entries.append(_url_entry(f"{base}/podcaster/{quote(pod.name)}",
                                      _date_from_ms(pod.updated_at), "weekly", "0.6"))
    except Exception as e:
        logger.warning("Sitemap podcaster enumeration failed: %s", e)

    # Topic tags are deliberately NOT listed. Measured on the live site, /topics/:tag
    # renders 7,304 characters of which 7,207 sit inside episode cards — 97 characters
    # are the page's own, and those are nav chrome plus one sentence
    # ("瀏覽所有關於「X」的 Podcast 摘要與市場討論 · N 集。") that is identical across all ~166
    # of them bar the tag name. A template plus a link list, 166 times over, is the
    # shape AdSense called "low value content" when it suspended tinboker.com.
    #
    # The pages stay — they are useful navigation — they are just not submitted for
    # indexing, and the crawler middleware serves them noindex. Sector pages are the
    # deliberate contrast: those carry a hand-written thesis, inclusion criteria and
    # per-constituent descriptions, so they stay in the sitemap.

    # Sector / theme pages. Each carries a hand-written zh-TW description and 100+
    # episodes, and none of them were in the sitemap at all — Google had no way to
    # discover 80-odd of the site's richest pages. Visibility filtering mirrors
    # GET /api/sectors exactly so the sitemap never lists a page that renders empty.
    try:
        sectors = await podcast_service.list_sectors()
        served = served_sector_exposure_ids(db)
        if served is None:  # bootstrap window: registry empty — fall back to blocklist
            hidden = hidden_sector_exposure_ids(db)
            visible = [s for s in sectors if s.get("exposure_id") not in hidden]
        else:
            visible = [s for s in sectors if s.get("exposure_id") in served]
        for sec in visible:
            sid = sec.get("exposure_id")
            if sid:
                entries.append(_url_entry(f"{base}/sector/{quote(str(sid))}", None, "weekly", "0.6"))
    except Exception as e:
        logger.warning("Sitemap sector enumeration failed: %s", e)

    # Stock pages: every ticker at least MIN_TICKER_EPISODES scoped episodes discuss.
    # Measured 2026-09-05: 514 tickers were mentioned inside the release window but only
    # the trending top-100 had a sitemap entry, so ~400 pages with real podcast content
    # were undiscoverable. The floor keeps single-mention pages (one thesis line) out.
    # Counting the scoped episode list, not trending_tickers, guarantees every listed
    # page has episodes to show — trending counts include out-of-window mentions.
    for tk in sorted(ticker_episodes):
        if ticker_episodes[tk] >= MIN_TICKER_EPISODES:
            entries.append(_url_entry(f"{base}/stock/{quote(tk)}", None, "daily", "0.6"))

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(entries)
        + "\n</urlset>\n"
    )
    try:
        await cache_set(cache_key, xml, 3600)
    except Exception:
        pass
    return Response(
        content=xml,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@admin_router.get("/api/admin/seo/overview")
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
        cached = None if refresh else SearchConsoleService.get_cached()
        # Force a refresh when the cache predates the per-day ``series`` field, so the
        # trend chart populates on first load after deploy without a manual refresh.
        if cached is not None and "series" not in cached:
            cached = None
        data = cached or await svc.refresh_cache(days=days)
        return {"configured": True, **data}
    except Exception as e:
        logger.exception("GSC overview failed")
        raise HTTPException(status_code=502, detail=f"Search Console query failed: {e}")


@admin_router.post("/api/admin/seo/refresh")
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
