"""
Notification producer — turns newly-ingested episodes into user notifications.

Everything else already existed: the notification model + Firestore storage, the
/api/notifications endpoints, and the bell dropdown UI. The only missing piece was a
producer. This background loop polls the episode mirror on the same ~10-min cadence
as ingestion and, for each genuinely new episode, fans out notifications to:
  - users subscribed to that podcaster      -> NEW_EPISODE
  - users holding a mentioned ticker        -> STOCK_MENTION
  - users following a mentioned tag/topic   -> TOPIC_MENTION

Dedup is a Redis high-water mark on firestore_mirror.episodes.first_seen_at — the
DB-default timestamp of the row's first mirror insert, never updated on re-ingest.
Unlike created_time (the publish date), it is monotonic in ingestion order, so an
episode ingested late with an old publish date still lands above the mark.
NB: re-dumping the mirror into an empty table resets every first_seen_at — delete
the Redis key first so the cold-start guard re-arms instead of blasting the backlog.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import text

from src.cache import cache_get, cache_set
from src.config import settings
from src.services.notification_service import (
    notify_new_episode,
    notify_stock_mention,
    notify_topic_mention,
)
from src.services.podcast import PodcastService
from src.services.postgres_mirror_service import EPISODES, mirror_session

logger = logging.getLogger(__name__)

_MARKER_KEY = "notif:last_seen_first_seen_at"
# Marker only needs to outlive the cadence. If it expires/is lost, the cold-start guard
# below skips one batch and re-establishes it. ponytail: 30d TTL is plenty of headroom.
_MARKER_TTL = 30 * 24 * 3600
# Rows per cycle. Ordered oldest-first above the mark, so a burst of >50 catches up
# over the next cycles instead of dropping the oldest.
_SCAN_LIMIT = 50

_podcast_service = PodcastService()


def _fetch_new_rows(mark: str | None):
    """(max first_seen_at, [(episode_id, first_seen_at, doc), ...]) above the mark,
    oldest first. mark=None (cold start) returns just the table's max and no rows."""
    with mirror_session() as db:
        if mark is None:
            row = db.execute(text(f"SELECT max(first_seen_at) FROM {EPISODES}")).first()
            return (row[0] if row else None), []
        rows = db.execute(
            text(
                f"SELECT episode_id, first_seen_at, doc FROM {EPISODES} "
                "WHERE first_seen_at > CAST(:mark AS timestamptz) "
                "ORDER BY first_seen_at ASC LIMIT :lim"
            ),
            {"mark": mark, "lim": _SCAN_LIMIT},
        ).fetchall()
        return (rows[-1][1] if rows else None), rows


def _notify_for_episodes(episodes) -> int:
    """Sync fan-out for a batch of episode docs. Runs in a thread (Firestore is blocking)."""
    count = 0
    for ep in episodes:
        eid = ep["id"]
        title = ep.get("episode_title") or eid
        podcast = ep.get("podcast_name") or ""
        try:
            count += len(notify_new_episode(podcast, eid, title))
            for ticker in ep.get("related_tickers") or []:
                count += len(notify_stock_mention(ticker, ticker, eid, podcast))
            for tag in ep.get("tags") or []:
                count += len(notify_topic_mention(tag, eid, podcast, title))
        except Exception as e:
            logger.warning(f"notify: fan-out failed for episode {eid}: {e}")
    return count


async def scan_and_notify() -> int:
    """One pass: mirror rows first seen after the high-water mark, oldest first."""
    if not settings.use_postgres:
        return 0  # firestore_mirror only exists in podcast_db Postgres (no-op in SQLite dev)

    raw = await cache_get(_MARKER_KEY)
    max_seen, rows = await asyncio.to_thread(_fetch_new_rows, raw)

    # Cold start (first run, or marker lost): record the mark, don't blast the backlog.
    if raw is None:
        if max_seen is not None:
            await cache_set(_MARKER_KEY, max_seen.isoformat(), _MARKER_TTL)
            logger.info("notify: cold start, marker set to %s (no notifications sent).", max_seen)
        return 0
    if not rows:
        return 0

    # Same visibility rules as the public feed (_scope_episodes): out-of-scope shows and
    # content-empty placeholders don't notify. The mark still advances past them.
    # ponytail: a placeholder that gains content later (regen) is never notified — add a
    # notified_at column on the mirror row if that ever matters.
    allowed = await _podcast_service._allowed_podcast_names()
    cutoff = _podcast_service._recency_cutoff_ms()
    eligible = []
    for episode_id, _, doc in rows:
        d = dict(doc or {})
        d["id"] = episode_id
        if not PodcastService._dict_has_content(d):
            continue
        if allowed is not None and d.get("podcast_name") not in allowed:
            continue
        if cutoff is not None and _podcast_service._dict_release_ms(d) < cutoff:
            continue
        eligible.append(d)

    sent = 0
    if eligible:
        sent = await asyncio.to_thread(_notify_for_episodes, eligible)
    await cache_set(_MARKER_KEY, max_seen.isoformat(), _MARKER_TTL)
    logger.info(
        "notify: %d new mirror row(s), %d eligible, %d notification(s) sent.",
        len(rows), len(eligible), sent,
    )
    return sent


async def run_periodic_notifications(interval_seconds: float = 600.0) -> None:
    """Background loop: scan on startup, then every interval_seconds. Never raises."""
    while True:
        try:
            await scan_and_notify()
        except Exception as e:
            logger.warning(f"notify: cycle failed: {e}")
        await asyncio.sleep(interval_seconds)
