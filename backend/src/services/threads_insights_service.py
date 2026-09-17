"""Read engagement insights from the Meta Threads Graph API.

The counterpart to :mod:`threads_publisher` (which *writes* posts): this *reads* the
account- and post-level insights Threads exposes — views, likes, replies, reposts,
quotes, plus follower count. Credentials are the same long-lived access token + numeric
user id already configured for publishing (``THREADS_ACCESS_TOKEN`` / ``THREADS_USER_ID``).

Docs: https://developers.facebook.com/docs/threads/insights

Read-only and credential-gated: with no token/user id (or any API error) the methods
return ``available: False`` with a reason instead of raising, so the admin UI degrades
to "not connected" rather than 500-ing.
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Optional

import httpx

from src.config import settings
from src.services import threads_publisher

logger = logging.getLogger(__name__)

# Account-level metrics. followers_count is a lifetime total and must be queried
# WITHOUT a since/until window (Threads rejects the combination), so it's fetched
# separately from the time-bound engagement metrics below.
ACCOUNT_TIME_METRICS = ["views", "likes", "replies", "reposts", "quotes"]
# Per-post metrics (media-level insights). ``shares`` is what carried every breakout
# post so far (Aug–Sep 2026), so it is the one number the format report must not miss.
POST_METRICS = ["views", "likes", "replies", "reposts", "quotes", "shares"]


def _metric_value(item: dict) -> int:
    """Pull a single number from one insights entry (total_value or summed series)."""
    tv = item.get("total_value")
    if isinstance(tv, dict) and tv.get("value") is not None:
        try:
            return int(tv["value"])
        except (TypeError, ValueError):
            return 0
    total = 0
    for v in item.get("values", []) or []:
        try:
            total += int((v or {}).get("value", 0) or 0)
        except (TypeError, ValueError):
            continue
    return total


def group_by_format(posts: list[dict]) -> list[dict]:
    """Roll per-post rows (``format`` + ``metrics``) up into one line per format. Pure.

    Median views, not mean: the account is power-law (top 4 posts were 51% of views), so
    a mean says which format got lucky once, a median says which one readers open.
    Rows with no metrics (insights call failed) are counted but excluded from the stats,
    so a bad week for the API does not read as a bad week for a format.
    """
    buckets: dict[str, list[dict]] = defaultdict(list)
    for p in posts:
        buckets[p.get("format") or "unknown"].append(p)
    out = []
    for fmt, rows in buckets.items():
        measured = [r["metrics"] for r in rows if r.get("metrics")]
        views = [m.get("views", 0) for m in measured]
        line = {"format": fmt, "posts": len(rows), "measured": len(measured),
                "views_median": int(median(views)) if views else 0, "views_total": sum(views)}
        for k in POST_METRICS[1:]:
            line[k] = sum(m.get(k, 0) for m in measured)
        out.append(line)
    return sorted(out, key=lambda x: -x["posts"])


def _parse_metrics(payload: dict) -> dict:
    """Map a ``{"data": [{name, total_value/values}, ...]}`` response to ``{name: int}``."""
    out: dict[str, int] = {}
    for item in (payload.get("data") or []):
        name = item.get("name")
        if name:
            out[name] = _metric_value(item)
    return out


class ThreadsInsightsService:
    """Read-only client for Threads account and per-post insights."""

    def __init__(
        self,
        access_token: Optional[str] = None,
        user_id: Optional[str] = None,
        api_base: Optional[str] = None,
    ):
        self._token = access_token if access_token is not None else settings.threads_access_token
        self._user_id = user_id if user_id is not None else settings.threads_user_id
        self._base = (api_base or settings.threads_api_base).rstrip("/")

    @property
    def is_configured(self) -> bool:
        return bool(self._token and self._user_id)

    async def _get(self, client: httpx.AsyncClient, path: str, params: dict) -> dict:
        params = {**params, "access_token": self._token}
        resp = await client.get(f"{self._base}/{path}", params=params)
        payload = resp.json()
        if resp.status_code >= 400 or "error" in payload:
            err = payload.get("error", payload)
            raise RuntimeError(str(err.get("message", err) if isinstance(err, dict) else err)[:300])
        return payload

    async def account_summary(self, days: int = 28) -> dict:
        """Account-wide engagement totals over ``days`` + lifetime follower count.

        Returns ``{configured, available, metrics, followers, range, ...}``. Never
        raises — degradation is reported via ``available: False`` + ``detail``.
        """
        if not self.is_configured:
            return {
                "configured": False,
                "available": False,
                "detail": "Set THREADS_ACCESS_TOKEN and THREADS_USER_ID to enable Threads insights.",
            }

        now = datetime.now(timezone.utc)
        since = int((now - timedelta(days=max(1, days))).timestamp())
        until = int(now.timestamp())
        metrics: dict[str, int] = {}
        followers: Optional[int] = None
        detail: Optional[str] = None

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Time-bound engagement metrics.
                try:
                    payload = await self._get(
                        client,
                        f"{self._user_id}/threads_insights",
                        {"metric": ",".join(ACCOUNT_TIME_METRICS), "since": since, "until": until},
                    )
                    metrics = _parse_metrics(payload)
                except Exception as e:
                    detail = f"Engagement metrics failed: {e}"
                    logger.warning("Threads account insights failed: %s", e)

                # Lifetime follower count (no window).
                try:
                    fpayload = await self._get(
                        client, f"{self._user_id}/threads_insights", {"metric": "followers_count"}
                    )
                    fmetrics = _parse_metrics(fpayload)
                    followers = fmetrics.get("followers_count")
                except Exception as e:
                    logger.info("Threads followers_count unavailable: %s", e)
        except Exception as e:  # client construction / unexpected
            return {"configured": True, "available": False, "detail": f"Request failed: {e}"}

        available = bool(metrics) or followers is not None
        return {
            "configured": True,
            "available": available,
            "range": {"days": days},
            "metrics": metrics,
            "followers": followers,
            **({"detail": detail} if detail and not available else {}),
        }

    async def format_report(self, days: int = 28) -> dict:
        """Engagement per post format over the window — the yardstick for which formats
        to keep. ``unknown`` is rows recorded before the ledger stored a format."""
        posts = await self.recent_post_insights(limit=200, days=days)
        return {"configured": self.is_configured, "range": {"days": days},
                "formats": group_by_format(posts)}

    async def recent_post_insights(self, limit: int = 5, days: Optional[int] = None) -> list[dict]:
        """Per-post insights for the most recently published episodes (best-effort).

        Reads locally-recorded posts (``social_posts`` ledger) and fetches media-level
        insights for each. Posts whose insights call fails are returned with the error
        rather than dropped, so the admin can see which ones lack data.
        """
        if not self.is_configured:
            return []
        posted = threads_publisher.list_posted(limit=limit, days=days)
        if not posted:
            return []

        results: list[dict] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            for row in posted:
                media_id = row.get("media_id")
                base = {
                    "episode_id": row.get("episode_id"),
                    "media_id": media_id,
                    "url": row.get("url"),
                    "format": row.get("format"),
                    "posted_at": row.get("posted_at"),
                }
                if not media_id:
                    results.append({**base, "metrics": {}, "error": "no_media_id"})
                    continue
                try:
                    payload = await self._get(
                        client, f"{media_id}/insights", {"metric": ",".join(POST_METRICS)}
                    )
                    results.append({**base, "metrics": _parse_metrics(payload)})
                except Exception as e:
                    results.append({**base, "metrics": {}, "error": str(e)})
        return results
