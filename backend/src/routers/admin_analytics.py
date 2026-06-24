"""
Admin Analytics API - Fetches live traffic analytics from Cloudflare.
"""
import asyncio
import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.auth.admin_auth import AdminAccess, get_admin_access
from src.cache.redis_client import cache_get, cache_set
from src.database.postgres import get_session
from src.services.cloudflare_analytics_service import CloudflareAnalyticsService
from src.services.firestore_service import FirestoreService
from src.tag_registry import canonical_label, display_map

router = APIRouter(prefix="/api/admin/analytics", tags=["admin-analytics"])
logger = logging.getLogger(__name__)


def _to_dt(value) -> datetime | None:
    """Best-effort parse of a Firestore created_at into an aware UTC datetime."""
    if value is None:
        return None
    if hasattr(value, "timestamp"):  # Firestore Timestamp / datetime
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
    """Registered-member analytics from first-party data (the `users` collection).

    Complements GA4 (which is anonymous): GA can't tell which signed-in members saved
    what. This aggregates their watchlists / subscriptions / bookmarks / tag follows
    into "what our members are into", plus signup growth. Cached 5 min.
    """
    cache_key = f"admin:member_analytics:top{top}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return json.loads(cached)

    fs = FirestoreService()
    users = await asyncio.to_thread(fs.get_all_documents, "users")

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
        docs = await asyncio.to_thread(fs.get_documents_batch, "episodes", top_ep_ids)
        ep_titles = {d["id"]: (d.get("title") or d["id"]) for d in docs}

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
