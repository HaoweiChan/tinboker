"""
Notification producer — turns newly-ingested episodes into user notifications.

Everything else already existed: the notification model + Firestore storage, the
/api/notifications endpoints, and the bell dropdown UI. The only missing piece was a
producer. This background loop polls the recent-episodes feed on the same ~10-min
cadence as ingestion and, for each genuinely new episode, fans out notifications to:
  - users subscribed to that podcaster      -> NEW_EPISODE
  - users holding a mentioned ticker        -> STOCK_MENTION
  - users following a mentioned tag/topic   -> TOPIC_MENTION

Dedup is a Redis high-water mark on episode created_time (ingestion ms): each episode
is processed exactly once, so no per-notification dedup is needed.
"""

from __future__ import annotations

import asyncio
import logging

from src.cache import cache_get, cache_set
from src.services.notification_service import (
    notify_new_episode,
    notify_stock_mention,
    notify_topic_mention,
)
from src.services.podcast import PodcastService

logger = logging.getLogger(__name__)

_MARKER_KEY = "notif:last_seen_created_time"
# Marker only needs to outlive the cadence. If it expires/is lost, the cold-start guard
# below skips one batch and re-establishes it. ponytail: 30d TTL is plenty of headroom.
_MARKER_TTL = 30 * 24 * 3600
# Episodes to scan per cycle. The pipeline pulls every ~10 min, so a cycle almost never
# sees more than a handful of new episodes.
# ponytail: a burst of >50 new episodes between cycles would miss the oldest — raise if it matters.
_SCAN_LIMIT = 50

_podcast_service = PodcastService()


def _notify_for_episodes(episodes) -> int:
    """Sync fan-out for a batch of new episodes. Runs in a thread (Firestore is blocking)."""
    count = 0
    for ep in episodes:
        title = ep.episode_title or ep.id
        try:
            count += len(notify_new_episode(ep.podcast_name, ep.id, title))
            for ticker in ep.related_tickers:
                count += len(notify_stock_mention(ticker, ticker, ep.id, ep.podcast_name))
            for tag in ep.tags:
                count += len(notify_topic_mention(tag, ep.id, ep.podcast_name, title))
        except Exception as e:
            logger.warning(f"notify: fan-out failed for episode {ep.id}: {e}")
    return count


async def scan_and_notify() -> int:
    """One pass: find episodes newer than the high-water mark and fan out notifications."""
    episodes = await _podcast_service.get_recent_episodes(limit=_SCAN_LIMIT)
    if not episodes:
        return 0

    # max() over created_time (not list order) so the mark is robust to the feed's sort.
    max_ct = max(ep.created_time for ep in episodes)
    raw = await cache_get(_MARKER_KEY)

    # Cold start (first run, or marker lost): record the mark, don't blast the backlog.
    if raw is None:
        await cache_set(_MARKER_KEY, str(max_ct), _MARKER_TTL)
        logger.info("notify: cold start, marker set to %s (no notifications sent).", max_ct)
        return 0

    last_seen = int(raw)
    new_eps = [ep for ep in episodes if ep.created_time > last_seen]
    if not new_eps:
        return 0

    loop = asyncio.get_event_loop()
    sent = await loop.run_in_executor(None, _notify_for_episodes, new_eps)
    await cache_set(_MARKER_KEY, str(max_ct), _MARKER_TTL)
    logger.info("notify: %d new episode(s), %d notification(s) sent.", len(new_eps), sent)
    return sent


async def run_periodic_notifications(interval_seconds: float = 600.0) -> None:
    """Background loop: scan on startup, then every interval_seconds. Never raises."""
    while True:
        try:
            await scan_and_notify()
        except Exception as e:
            logger.warning(f"notify: cycle failed: {e}")
        await asyncio.sleep(interval_seconds)
