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

import asyncio
import logging
from contextlib import contextmanager
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Optional

import httpx
from sqlalchemy import text

from src.config import settings
from src.database.models import SocialPostLedger, ThreadsInsightsSyncState, ThreadsPostInsightSnapshot
from src.database import postgres
from src.database.postgres import session_scope
from src.services import social_ledger
from src.services import threads_publisher

logger = logging.getLogger(__name__)


class ThreadsAPIError(RuntimeError):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code

    @property
    def retryable(self) -> bool:
        return self.status_code == 429 or self.status_code >= 500

# Account-level metrics. followers_count is a lifetime total and must be queried
# WITHOUT a since/until window (Threads rejects the combination), so it's fetched
# separately from the time-bound engagement metrics below.
ACCOUNT_TIME_METRICS = ["views", "likes", "replies", "reposts", "quotes"]
# Per-post metrics (media-level insights). ``shares`` is what carried every breakout
# post so far (Aug–Sep 2026), so it is the one number the format report must not miss.
POST_METRICS = ["views", "likes", "replies", "reposts", "quotes", "shares"]


def _metric_value(item: dict) -> Optional[int]:
    """Pull a reported number; absent/invalid provider data is not a zero sample."""
    tv = item.get("total_value")
    if isinstance(tv, dict):
        if tv.get("value") is None:
            return None
        try:
            return int(tv["value"])
        except (TypeError, ValueError):
            return None
    values = item.get("values") or []
    if not values:
        return None
    total = 0
    found = False
    for v in values:
        if (v or {}).get("value") is None:
            continue
        try:
            total += int(v["value"])
            found = True
        except (TypeError, ValueError):
            continue
    return total if found else None


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
        # Clicks on the link each post carried, and what share of the format's views
        # they are. The link sits in reply 0, so this is small by construction (0.1% in
        # Sep 2026) — it is here to compare formats against each other, not to look good.
        line["link_clicks"] = sum(int(r.get("link_clicks") or 0) for r in rows)
        line["link_ctr_pct"] = round(line["link_clicks"] / line["views_total"] * 100, 3) if line["views_total"] else 0.0
        out.append(line)
    return sorted(out, key=lambda x: -x["posts"])


def base_url(url: Optional[str]) -> str:
    """A link without its query or trailing slash — the ledger stores the bare URL, the
    posted link carries UTM tags, and Threads reports whichever was posted."""
    return (url or "").split("?", 1)[0].split("#", 1)[0].rstrip("/")


def parse_link_clicks(payload: dict) -> dict[str, int]:
    """``{bare url: clicks}`` from an account ``clicks`` insight (``link_total_values``)."""
    out: dict[str, int] = defaultdict(int)
    for item in payload.get("data") or []:
        for link in item.get("link_total_values") or []:
            if link.get("link_url"):
                out[base_url(link["link_url"])] += int(link.get("value") or 0)
    return dict(out)


def _parse_metrics(payload: dict) -> dict:
    """Map a ``{"data": [{name, total_value/values}, ...]}`` response to ``{name: int}``."""
    out: dict[str, int] = {}
    for item in (payload.get("data") or []):
        name = item.get("name")
        if name:
            value = _metric_value(item)
            if value is not None:
                out[name] = value
    return out


def _save_metric_snapshot(media_id: str, metrics: dict) -> bool:
    if not metrics:
        return False
    now = datetime.now(timezone.utc)
    with session_scope() as db:
        row = (
            db.query(ThreadsPostInsightSnapshot)
            .filter_by(media_id=media_id, captured_day=now.date())
            .first()
        )
        if row is None:
            row = ThreadsPostInsightSnapshot(
                media_id=media_id, captured_day=now.date(), captured_at=now, metrics=metrics
            )
            db.add(row)
        else:
            # Keep the first successful sample for the UTC day; failed requests never
            # reserve the unique day and a later retry can still create the sample.
            return False
    return True


def _has_successful_snapshot_today(media_id: str) -> bool:
    with session_scope() as db:
        row = (
            db.query(ThreadsPostInsightSnapshot.id)
            .filter_by(media_id=media_id, captured_day=datetime.now(timezone.utc).date())
            .first()
        )
    return row is not None


def metric_snapshot_history(media_ids: list[str], limit_per_post: int = 30) -> dict[str, list[dict]]:
    if not media_ids:
        return {}
    with session_scope() as db:
        rows = (
            db.query(ThreadsPostInsightSnapshot.media_id,
                     ThreadsPostInsightSnapshot.captured_at,
                     ThreadsPostInsightSnapshot.metrics)
            .filter(ThreadsPostInsightSnapshot.media_id.in_(media_ids))
            .order_by(ThreadsPostInsightSnapshot.media_id, ThreadsPostInsightSnapshot.captured_at.desc())
            .all()
        )
    history: dict[str, list[dict]] = defaultdict(list)
    for media_id, captured_at, metrics in rows:
        samples = history[media_id]
        if len(samples) < limit_per_post:
            if captured_at and captured_at.tzinfo is None:
                captured_at = captured_at.replace(tzinfo=timezone.utc)
            samples.append({
                "captured_at": captured_at.isoformat() if captured_at else None,
                "metrics": metrics or {},
            })
    return dict(history)


def _sync_state() -> Optional[ThreadsInsightsSyncState]:
    with session_scope() as db:
        row = db.get(ThreadsInsightsSyncState, "account")
        if row is None:
            return None
        return {
            "backfill_cursor": row.backfill_cursor,
            "backfill_complete": row.backfill_complete,
            "daily_cursor": row.daily_cursor,
            "daily_window_since": row.daily_window_since,
            "daily_synced_at": row.daily_synced_at,
            "updated_at": row.updated_at,
        }


def history_sync_status() -> dict:
    with session_scope() as db:
        state = db.get(ThreadsInsightsSyncState, "account")
        tracked = db.query(SocialPostLedger.media_id).filter(
            SocialPostLedger.platform == "threads", SocialPostLedger.media_id.isnot(None)
        ).count()
        samples = db.query(ThreadsPostInsightSnapshot.id).count()
        latest = db.query(ThreadsPostInsightSnapshot.captured_at).order_by(
            ThreadsPostInsightSnapshot.captured_at.desc()
        ).first()
        return {
            "tracked_posts": tracked,
            "metric_snapshots": samples,
            "latest_sample_at": latest[0].isoformat() if latest and latest[0] else None,
            "backfill_complete": bool(state and state.backfill_complete),
            "backfill_has_cursor": bool(state and state.backfill_cursor),
            "daily_cursor_active": bool(state and state.daily_cursor),
            "daily_synced_at": state.daily_synced_at.isoformat() if state and state.daily_synced_at else None,
        }


def _write_backfill_cursor(cursor: Optional[str], complete: bool) -> None:
    with session_scope() as db:
        row = db.get(ThreadsInsightsSyncState, "account")
        if row is None:
            row = ThreadsInsightsSyncState(key="account")
            db.add(row)
        row.backfill_cursor = cursor
        row.backfill_complete = complete
        row.updated_at = datetime.now(timezone.utc)


def _write_daily_cursor(cursor: Optional[str], window_since: Optional[datetime], at: datetime) -> None:
    with session_scope() as db:
        row = db.get(ThreadsInsightsSyncState, "account")
        if row is None:
            row = ThreadsInsightsSyncState(key="account")
            db.add(row)
        row.daily_cursor = cursor
        row.daily_window_since = window_since
        row.daily_synced_at = at
        row.updated_at = at


@contextmanager
def _sync_lock():
    """One importer across staging-admin requests and the production scheduler."""
    if not settings.use_postgres:
        yield True
        return
    postgres.init_engine()
    conn = postgres.engine.connect()
    key = "threads-insights-sync"
    acquired = bool(conn.execute(
        text("SELECT pg_try_advisory_lock(hashtext(:key))"), {"key": key}
    ).scalar())
    try:
        yield acquired
    finally:
        if acquired:
            conn.execute(text("SELECT pg_advisory_unlock(hashtext(:key))"), {"key": key})
        conn.close()


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
            message = str(err.get("message", err) if isinstance(err, dict) else err)[:300]
            raise ThreadsAPIError(message, resp.status_code or 400)
        return payload

    async def _provider_replies(self, client: httpx.AsyncClient, media_id: str) -> tuple[list[dict], bool]:
        payload = await self._get(client, f"{media_id}/replies", {
            "fields": "id,text,timestamp,permalink,username,is_reply,is_reply_owned_by_me,root_post,replied_to",
            "reverse": "false", "limit": 100,
        })
        owned = [r for r in payload.get("data") or [] if r.get("is_reply_owned_by_me") is True]
        return owned, bool((payload.get("paging") or {}).get("next"))

    async def _capture_posts(
        self, client: httpx.AsyncClient, posts: list[dict], *, capture_replies: bool
    ) -> dict:
        from src.services import social_ledger

        imported = already_present = skipped_replies = replies_saved = 0
        metrics_saved = errors = unavailable_metrics = unusable_timestamps = 0
        for post in posts:
            media_id = str(post.get("id") or "")
            if not media_id:
                errors += 1
                continue
            if post.get("is_reply") is True:
                skipped_replies += 1
                continue
            sampled_today = await asyncio.to_thread(_has_successful_snapshot_today, media_id)
            if sampled_today and not capture_replies:
                continue
            owner_id = (post.get("owner") or {}).get("id")
            if owner_id and str(owner_id) != str(self._user_id):
                errors += 1
                continue
            try:
                social_ledger.parse_threads_timestamp(post.get("timestamp"))
            except ValueError:
                # Do not invent a publication time for incomplete provider records.
                unusable_timestamps += 1
                continue

            owned_replies = None
            replies_truncated = False
            if capture_replies and post.get("has_replies"):
                try:
                    owned_replies, replies_truncated = await self._provider_replies(client, media_id)
                    replies_saved += len(owned_replies)
                except ThreadsAPIError as exc:
                    if exc.retryable:
                        raise
                    logger.info("Threads reply history unavailable for %s (HTTP %d)", media_id, exc.status_code)
                    owned_replies = None
                    errors += 1
            try:
                _, created = await asyncio.to_thread(
                    social_ledger.import_threads_post, post, owned_replies, replies_truncated=replies_truncated
                )
            except Exception:
                logger.exception("Threads history import failed for one media item")
                # Do not move the page cursor if the ledger did not durably accept this post.
                raise
            imported += int(created)
            already_present += int(not created)

            if sampled_today or await asyncio.to_thread(_has_successful_snapshot_today, media_id):
                continue
            try:
                payload = await self._get(client, f"{media_id}/insights", {"metric": ",".join(POST_METRICS)})
                metrics = _parse_metrics(payload)
                metrics_saved += int(await asyncio.to_thread(_save_metric_snapshot, media_id, metrics))
                unavailable_metrics += int(not metrics)
            except ThreadsAPIError as exc:
                if exc.retryable:
                    raise
                # The media itself is imported, but unsupported/unavailable metrics stay missing.
                logger.info("Threads post insights unavailable for %s (HTTP %d)", media_id, exc.status_code)
                unavailable_metrics += 1
                errors += 1
        return {
            "imported": imported, "already_present": already_present,
            "skipped_replies": skipped_replies, "owned_replies_saved": replies_saved,
            "metrics_captured": metrics_saved, "unavailable_metrics": unavailable_metrics,
            "unusable_timestamps": unusable_timestamps, "errors": errors,
        }

    async def backfill_page(self, *, dry_run: bool = False, page_size: int = 5) -> dict:
        if dry_run:
            return await self._backfill_page(dry_run=True, page_size=page_size)
        with _sync_lock() as acquired:
            if not acquired:
                return {"available": True, "busy": True, "detail": "Another Threads sync is running."}
            return await self._backfill_page(dry_run=False, page_size=page_size)

    async def _backfill_page(self, *, dry_run: bool, page_size: int) -> dict:
        """Read/import one provider page; cursor only advances after a durable page."""
        if not self.is_configured:
            return {"available": False, "detail": "Threads API is not configured."}
        state = _sync_state() or {}
        if state.get("backfill_complete"):
            return {"available": True, "complete": True, "processed": 0, "detail": "History is already imported."}
        cursor = state.get("backfill_cursor")
        params = {
            "fields": "id,media_product_type,media_type,media_url,permalink,owner,username,text,timestamp,shortcode,children,has_replies,is_reply,root_post,replied_to",
            "limit": max(1, min(page_size, 5)),
        }
        if cursor:
            params["after"] = cursor
        async with httpx.AsyncClient(timeout=8.0) as client:
            payload = await self._get(client, f"{self._user_id}/threads", params)
            posts = payload.get("data") or []
            paging = payload.get("paging") or {}
            has_next = bool(paging.get("next"))
            next_cursor = (paging.get("cursors") or {}).get("after")
            if has_next and (not next_cursor or next_cursor == cursor):
                raise RuntimeError("Threads pagination returned an invalid next cursor")
            if dry_run:
                roots = [p for p in posts if p.get("is_reply") is not True]
                insight_names: list[str] = []
                insight_error = None
                if roots:
                    try:
                        check = await self._get(client, f"{roots[0]['id']}/insights", {"metric": ",".join(POST_METRICS)})
                        insight_names = sorted(_parse_metrics(check))
                    except Exception as exc:
                        insight_error = type(exc).__name__
                known = {
                    r.get("media_id") for r in await asyncio.to_thread(social_ledger.list_posted, "threads", 10000)
                    if r.get("media_id")
                }
                return {
                    "available": True, "dry_run": True, "listed": len(posts),
                    "root_posts": len(roots), "reply_entries": len(posts) - len(roots),
                    "already_tracked": sum(str(p.get("id")) in known for p in roots),
                    "would_import": sum(str(p.get("id")) not in known for p in roots),
                    "insights_available": bool(insight_names), "insight_metrics": insight_names,
                    "insight_error": insight_error, "more_pages": has_next,
                    "complete": False,
                }
            counts = await self._capture_posts(client, posts, capture_replies=True)
        complete = not has_next
        await asyncio.to_thread(_write_backfill_cursor, None if complete else next_cursor, complete)
        return {"available": True, "dry_run": False, "listed": len(posts),
                "complete": complete, "more_pages": has_next, **counts}

    async def sync_recent_posts(self, days: int = 30, limit: int = 5) -> dict:
        """Hourly bounded pagination; each post's first successful UTC-day sample is kept."""
        if not self.is_configured:
            return {"available": False, "detail": "Threads API is not configured."}
        state = _sync_state() or {}
        now = datetime.now(timezone.utc)
        window_since = state.get("daily_window_since") or (now - timedelta(days=max(1, days)))
        if window_since.tzinfo is None:
            window_since = window_since.replace(tzinfo=timezone.utc)
        cursor = state.get("daily_cursor")
        params = {
            "fields": "id,media_product_type,media_type,media_url,permalink,owner,username,text,timestamp,shortcode,children,has_replies,is_reply,root_post,replied_to",
            "limit": max(1, min(limit, 5)), "since": int(window_since.timestamp()),
        }
        if cursor:
            params["after"] = cursor
        async with httpx.AsyncClient(timeout=8.0) as client:
            payload = await self._get(client, f"{self._user_id}/threads", params)
            posts = payload.get("data") or []
            counts = await self._capture_posts(client, posts, capture_replies=False)
        paging = payload.get("paging") or {}
        has_next = bool(paging.get("next"))
        next_cursor = (paging.get("cursors") or {}).get("after")
        if has_next and (not next_cursor or next_cursor == cursor):
            raise RuntimeError("Threads daily pagination returned an invalid next cursor")
        await asyncio.to_thread(
            _write_daily_cursor,
            next_cursor if has_next else None,
            window_since if has_next else None,
            now,
        )
        return {"available": True, "listed": len(posts), "more_pages": has_next, **counts}

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
        # Pre-publish claims have no provider media ID yet; they are not published posts.
        posted = [
            row for row in threads_publisher.list_posted(limit=limit, days=days)
            if row.get("media_id")
        ]
        if not posted:
            return []

        histories = metric_snapshot_history([str(row["media_id"]) for row in posted if row.get("media_id")])
        results: list[dict] = []
        async with httpx.AsyncClient(timeout=30.0) as client:
            clicks: dict[str, int] = {}
            try:
                now = datetime.now(timezone.utc)
                clicks = parse_link_clicks(await self._get(client, f"{self._user_id}/threads_insights", {
                    "metric": "clicks", "until": int(now.timestamp()),
                    "since": int((now - timedelta(days=max(1, days or 28))).timestamp())}))
            except Exception as e:  # noqa: BLE001 — clicks are a bonus column, never a blocker
                logger.info("Threads link clicks unavailable: %s", e)
            for row in posted:
                media_id = row.get("media_id")
                base = {
                    "episode_id": row.get("episode_id"),
                    "media_id": media_id,
                    "url": row.get("url") or None,
                    "permalink": row.get("permalink"),
                    "format": row.get("format"),
                    "origin": row.get("origin", "unknown"),
                    "delivery": row.get("delivery"),
                    "post_snapshot": row.get("post_snapshot") or {},
                    "provider_snapshot": row.get("provider_snapshot") or {},
                    "metric_history": histories.get(str(media_id), []),
                    "tracking_error": row.get("tracking_error"),
                    "posted_at": row.get("posted_at"),
                    "link_clicks": clicks.get(base_url(row.get("url")), 0),
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


async def run_periodic_threads_insights(interval_seconds: float = 600.0) -> None:
    """Production-only single-writer scan of recent account posts, one small page per tick."""
    while True:
        if settings.is_production and settings.use_postgres:
            try:
                with _sync_lock() as acquired:
                    if acquired:
                        result = await ThreadsInsightsService().sync_recent_posts(days=30, limit=5)
                        if result.get("listed"):
                            logger.info(
                                "Threads insight snapshot page: listed=%d sampled=%d next=%s",
                                result["listed"], result.get("metrics_captured", 0), result.get("more_pages"),
                            )
            except Exception as exc:
                logger.warning("Threads insights sync cycle failed (%s)", type(exc).__name__)
        await asyncio.sleep(interval_seconds)
