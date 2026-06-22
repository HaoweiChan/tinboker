"""
FinMind free-tier request budget.

FinMind's registered free tier caps API usage at a fixed number of HTTP requests
per clock-hour (≈600/hr; configurable via FINMIND_HOURLY_CAP). We have no contractual
headroom, so every FinMind HTTP call must be counted and hard-capped — otherwise a
launch-day traffic spike silently exhausts the quota and every TW stock page degrades
to "no data" for the rest of the hour.

This module is a process-safe, Redis-backed fixed-window counter:
- The window key is the current UTC clock-hour, so it auto-resets without a cleanup job.
- It is intentionally *sync* (redis-py, not aioredis) because the FinMind client runs
  inside `run_in_executor` worker threads.
- If Redis is unavailable it falls back to a per-process in-memory counter (fail-soft):
  we still cap each worker process rather than removing the cap entirely.

Set the cap BELOW the real ceiling (default 500 against a 600 limit) to leave headroom
for clock skew and any un-instrumented call path.
"""

from __future__ import annotations

import os
import threading
import time
import logging
from datetime import datetime, timezone

from src.config import settings

logger = logging.getLogger(__name__)

# Single global hourly cap, set a little under the primary key's real limit so we stop
# calling (and serve stale) BEFORE FinMind returns 402s. A real 402/429 also retires it via
# exhaust(). Env wins (tests / local override); otherwise the GSM-backed settings value —
# secrets load into `settings`, not os.environ, so prod configures this via
# settings.finmind_hourly_cap. Default suits the free tier; raise it once the backer key
# (higher per-key limit) is the PRIMARY key in the pool.
HOURLY_CAP = int(os.getenv("FINMIND_HOURLY_CAP") or settings.finmind_hourly_cap)
_WINDOW_SECONDS = 3700  # one hour + slack, so the key outlives its clock-hour

_redis_client = None
_redis_unavailable = False

# In-process fallback (used only when Redis can't be reached). Counts are per-bucket so a
# pool of keys each get their own quota — {bucket: (window, count)}.
_local_lock = threading.Lock()
_local_counts: dict = {}

# Throttle the "budget exhausted" log so we don't spam once we hit the cap (per bucket).
_last_exhausted_log: dict = {}


def _window_key(bucket: str) -> str:
    return f"finmind:budget:{bucket}:{datetime.now(timezone.utc):%Y%m%d%H}"


def _get_sync_redis():
    """Lazily build a sync redis client; returns None if unavailable."""
    global _redis_client, _redis_unavailable
    if _redis_unavailable:
        return None
    if _redis_client is not None:
        return _redis_client
    url = settings.redis_connection_string
    if not url:
        _redis_unavailable = True
        return None
    try:
        import redis  # redis-py (sync) — already a dependency of the async client
        _redis_client = redis.Redis.from_url(
            url, socket_connect_timeout=1, socket_timeout=1, decode_responses=True
        )
        _redis_client.ping()
        return _redis_client
    except Exception as e:  # pragma: no cover - environment dependent
        logger.warning(f"FinMind budget: Redis unavailable, using per-process counter: {e}")
        _redis_unavailable = True
        _redis_client = None
        return None


def _consume_local(bucket: str, weight: int) -> bool:
    key = _window_key(bucket)
    with _local_lock:
        window, count = _local_counts.get(bucket, ("", 0))
        if key != window:
            window, count = key, 0
        count += weight
        _local_counts[bucket] = (window, count)
        return count <= HOURLY_CAP


def consume(bucket: str = "default", weight: int = 1) -> bool:
    """
    Account for `weight` FinMind HTTP requests against `bucket`'s current-hour budget.

    Each API key is its own bucket, so a pool of keys each get a full HOURLY_CAP. Returns
    True if within budget (proceed), False if this bucket's hourly cap is exhausted (the
    caller should try another key or serve stale cache / "unavailable").
    """
    client = _get_sync_redis()
    if client is None:
        return _consume_local(bucket, weight)
    try:
        key = _window_key(bucket)
        count = client.incrby(key, weight)
        if count == weight:  # first write in this window
            client.expire(key, _WINDOW_SECONDS)
        within = count <= HOURLY_CAP
        if not within:
            _maybe_log_exhausted(bucket, count)
        return within
    except Exception as e:  # Redis hiccup mid-flight — fall back, don't block forever
        logger.debug(f"FinMind budget: redis incr failed, falling back to local: {e}")
        return _consume_local(bucket, weight)


def exhaust(bucket: str = "default") -> None:
    """
    Retire `bucket` for the rest of the current clock-hour.

    Called when FinMind actually returns a quota error (402/429) for this key, which can
    happen before the configured HOURLY_CAP is reached (FinMind's real limit may be lower,
    or it counts differently). Sets the counter above the cap so subsequent consume()s
    return False and the client rotates to the next key.
    """
    key = _window_key(bucket)
    over = HOURLY_CAP + 1
    client = _get_sync_redis()
    if client is None:
        with _local_lock:
            _local_counts[bucket] = (key, over)
        return
    try:
        client.set(key, over, ex=_WINDOW_SECONDS)
    except Exception as e:
        logger.debug(f"FinMind budget: redis exhaust failed, falling back to local: {e}")
        with _local_lock:
            _local_counts[bucket] = (key, over)


def _maybe_log_exhausted(bucket: str, count: int) -> None:
    now = time.time()
    if now - _last_exhausted_log.get(bucket, 0.0) > 60:
        _last_exhausted_log[bucket] = now
        logger.warning(
            f"FinMind hourly budget exhausted for key bucket {bucket} ({count}/{HOURLY_CAP})."
        )


def remaining(bucket: str = "default") -> int:
    """Best-effort remaining budget for `bucket` this hour (for logging/alerts)."""
    client = _get_sync_redis()
    if client is None:
        with _local_lock:
            window, count = _local_counts.get(bucket, ("", 0))
            used = count if _window_key(bucket) == window else 0
        return max(0, HOURLY_CAP - used)
    try:
        used = int(client.get(_window_key(bucket)) or 0)
        return max(0, HOURLY_CAP - used)
    except Exception:
        return HOURLY_CAP
