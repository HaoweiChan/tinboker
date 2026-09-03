"""
Admin Analytics API - live traffic (Cloudflare), AdSense monetization, and daily
audience-growth snapshots.
"""
import asyncio
import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.auth.admin_auth import AdminAccess, get_admin_access, get_social_access
from src.cache.redis_client import cache_get, cache_set
from src.database.models import AnalyticsSnapshot, User
from src.database.postgres import get_session, session_scope
from src.services.cloudflare_analytics_service import CloudflareAnalyticsService
from src.services.adsense_service import AdSenseService
from src.services.facebook_insights_service import FacebookInsightsService
from src.services.postgres_mirror_service import content_read_service
from src.services.substack_insights_service import SubstackInsightsService
from src.services.threads_insights_service import ThreadsInsightsService
from src.services.vocus_insights_service import VocusInsightsService
from src.tag_registry import canonical_label, display_map

router = APIRouter(prefix="/api/admin/analytics", tags=["admin-analytics"])
logger = logging.getLogger(__name__)

# Ceiling for the vocus + Substack reads inside one snapshot call, chosen to leave the
# response well clear of Cloudflare's 100s edge timeout.
SYNDICATION_READ_TIMEOUT = 45.0


def _load_users() -> list[dict]:
    """Every member's aggregatable fields (~40 rows — no pagination needed).

    Selects columns rather than entities so the values survive the session close.
    """
    fields = (
        "created_at",
        "podcast_subscriptions",
        "tag_subscriptions",
        "watchlist",
        "episode_bookmarks",
    )
    with session_scope() as db:
        rows = db.query(*(getattr(User, f) for f in fields)).all()
    return [dict(zip(fields, row)) for row in rows]


def _to_dt(value) -> datetime | None:
    """Best-effort parse of a stored created_at into an aware UTC datetime."""
    if value is None:
        return None
    if hasattr(value, "timestamp"):  # datetime (Postgres timestamptz / SQLite)
        try:
            return datetime.fromtimestamp(value.timestamp(), tz=timezone.utc)
        except Exception:
            return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


@router.get("/members")
async def get_member_analytics(
    top: int = Query(default=10, ge=1, le=50, description="Rows per top-list"),
    admin: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    """Registered-member analytics from first-party data (the `users` table).

    Complements GA4 (which is anonymous): GA can't tell which signed-in members saved
    what. This aggregates their watchlists / subscriptions / bookmarks / tag follows
    into "what our members are into", plus signup growth. Cached 5 min.
    """
    cache_key = f"admin:member_analytics:top{top}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return json.loads(cached)

    users = await asyncio.to_thread(_load_users)

    podcasters: Counter = Counter()
    tags: Counter = Counter()
    tickers: Counter = Counter()
    episodes: Counter = Counter()
    for u in users:
        podcasters.update(u.get("podcast_subscriptions") or [])
        tags.update(u.get("tag_subscriptions") or [])
        tickers.update(u.get("watchlist") or [])
        episodes.update(u.get("episode_bookmarks") or [])

    # Signup growth: weekly counts for the last 8 ISO weeks (oldest → newest).
    now = datetime.now(timezone.utc)
    week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    buckets = [week_start - timedelta(weeks=i) for i in range(7, -1, -1)]
    signups = {b.strftime("%m-%d"): 0 for b in buckets}
    for u in users:
        dt = _to_dt(u.get("created_at"))
        if not dt:
            continue
        wk = (dt - timedelta(days=dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        key = wk.strftime("%m-%d")
        if key in signups:
            signups[key] += 1

    # Resolve bookmarked-episode titles in one batched read (top N only).
    top_ep_ids = [eid for eid, _ in episodes.most_common(top)]
    ep_titles: dict[str, str] = {}
    if top_ep_ids:
        # Content read — goes through the same seam as every other content read
        # (Postgres mirror, not Firestore). ponytail: titles are cosmetic, so a
        # lookup failure degrades to episode ids instead of blanking the panel.
        try:
            svc = content_read_service()
            docs = await asyncio.to_thread(svc.get_documents_batch, "episodes", top_ep_ids)
            ep_titles = {
                d["id"]: (d.get("episode_title") or d.get("title") or d["id"]) for d in docs
            }
        except Exception as e:
            logger.warning("member analytics: episode title lookup failed: %s", e)

    tag_labels = display_map(db)

    def _label_tag(slug: str) -> str:
        return tag_labels.get(slug) or canonical_label(slug)

    payload = {
        "total_users": len(users),
        "signups": [{"week": k, "count": v} for k, v in signups.items()],
        "top_podcasters": [{"name": n, "count": c} for n, c in podcasters.most_common(top)],
        "top_tags": [{"slug": s, "label": _label_tag(s), "count": c} for s, c in tags.most_common(top)],
        "top_tickers": [{"ticker": t, "count": c} for t, c in tickers.most_common(top)],
        "top_episodes": [
            {"episode_id": e, "title": ep_titles.get(e, e), "count": c}
            for e, c in episodes.most_common(top)
        ],
    }
    await cache_set(cache_key, json.dumps(payload), ttl=300)
    return payload


def _snapshot_dict(r: AnalyticsSnapshot) -> dict:
    return {
        "day": r.day,
        "threads_followers": r.threads_followers,
        "fb_followers": r.fb_followers,
        "fb_fans": r.fb_fans,
        "vocus_reads": r.vocus_reads,
        "vocus_articles": r.vocus_articles,
        "substack_reads": r.substack_reads,
        "substack_posts": r.substack_posts,
    }


@router.get("/overview")
async def get_analytics_overview(
    days: int = Query(default=7, ge=1, le=90),
    admin: AdminAccess = Depends(get_admin_access),
):
    """
    Cloudflare zone analytics overview — requests / page views / visits over ``days``.

    Returns live numbers when ``CLOUDFLARE_API_TOKEN`` (with Analytics:Read) and
    ``CLOUDFLARE_ZONE_TAG`` are set; otherwise ``available: false`` with a reason, so
    the admin UI falls back to the Cloudflare dashboard link. Always 200 (never raises
    on an upstream/permission error). Requires admin authentication.
    """
    cf = CloudflareAnalyticsService()
    data = await cf.overview(days=days)
    return {
        **data,
        "dashboards": {
            # Account-level Web Analytics (the :account token is resolved by the
            # Cloudflare dashboard to the signed-in account).
            "cloudflare": "https://dash.cloudflare.com/?to=/:account/web-analytics",
            "googleAnalytics": "https://analytics.google.com",
        },
    }



@router.get("/adsense")
async def get_adsense_overview(
    days: int = Query(default=28, ge=1, le=365),
    admin: AdminAccess = Depends(get_admin_access),
):
    """AdSense monetization overview — earnings, RPM, fill rate, viewability.

    Always 200: returns ``configured``/``available`` flags with a ``detail`` when the
    credential or upstream is missing, so the admin UI falls back to the AdSense
    dashboard link. Cached 30 min — AdSense report data only settles a few times a day,
    and every call costs an OAuth token refresh.
    """
    cache_key = f"admin:adsense:{days}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return json.loads(cached)

    data = await AdSenseService().overview(days=days)
    if data.get("available"):
        await cache_set(cache_key, json.dumps(data), ttl=1800)
    return data


@router.post("/snapshot")
async def record_snapshot(
    _: AdminAccess = Depends(get_social_access),
    db: Session = Depends(get_session),
):
    """Record today's audience numbers (one row per UTC day).

    Threads/Facebook followers and fans, plus the lifetime read totals on vocus and
    Substack. All four platforms expose only a *current* value and no history, so the
    growth chart is built from these daily rows; a day's reading is the difference
    between two of them.

    Auth accepts the TINBOKER_SOCIAL_TOKEN service token so a daily cron can call it.
    Idempotent per day (upsert); a transient failure never clobbers a good value —
    every field is written only when its source reported real data this run.
    """
    th = await ThreadsInsightsService().account_summary(days=1)
    fb = await FacebookInsightsService().account_summary(days=1)
    # Independent of Meta and of each other: one platform being down (or its read-count
    # field having moved) must not cost the day's row for the others. Both are paged
    # reads against undocumented APIs, and the cron calls this through Cloudflare, whose
    # edge gives up at 100s — so the whole syndication half is bounded well inside that.
    # Losing today's read counts is a gap in one chart; losing the response is the row.
    try:
        vo, su = await asyncio.wait_for(
            asyncio.gather(
                VocusInsightsService().account_summary(),
                SubstackInsightsService().account_summary(),
                return_exceptions=True,
            ),
            timeout=SYNDICATION_READ_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("analytics snapshot: syndication reads timed out; recording followers only")
        vo, su = {}, {}
    vo = vo if isinstance(vo, dict) else {}
    su = su if isinstance(su, dict) else {}
    day = datetime.now(timezone.utc).date().isoformat()

    row = db.query(AnalyticsSnapshot).filter(AnalyticsSnapshot.day == day).first()
    if row is None:
        row = AnalyticsSnapshot(day=day)
        db.add(row)
    if th.get("followers") is not None:
        row.threads_followers = th["followers"]
    if fb.get("followers") is not None:
        row.fb_followers = fb["followers"]
    if fb.get("fans") is not None:
        row.fb_fans = fb["fans"]
    # `available` is the gate, not the presence of a number: an unmapped read-count
    # field yields a 0 that would flatten the chart and read as "nobody opened it".
    if vo.get("available"):
        row.vocus_reads = vo.get("reads")
        row.vocus_articles = vo.get("articles")
    if su.get("available"):
        row.substack_reads = su.get("views")
        row.substack_posts = su.get("posts")
    row.captured_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    logger.info("analytics snapshot %s: th=%s fb=%s fans=%s vocus=%s substack=%s",
                row.day, row.threads_followers, row.fb_followers, row.fb_fans,
                row.vocus_reads, row.substack_reads)
    return _snapshot_dict(row)


@router.get("/history")
def get_analytics_history(
    days: int = Query(default=90, ge=1, le=365),
    admin: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    """Daily audience snapshots over ``days`` (oldest first) for the growth chart."""
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
    rows = (
        db.query(AnalyticsSnapshot)
        .filter(AnalyticsSnapshot.day >= cutoff)
        .order_by(AnalyticsSnapshot.day.asc())
        .all()
    )
    return {"snapshots": [_snapshot_dict(r) for r in rows]}
