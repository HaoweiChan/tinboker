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

# Cap well under the free-tier ceiling to leave headroom. Override via env.
HOURLY_CAP = int(os.getenv("FINMIND_HOURLY_CAP", "500"))
_WINDOW_SECONDS = 3700  # one hour + slack, so the key outlives its clock-hour

_redis_client = None
_redis_unavailable = False

# In-process fallback (used only when Redis can't be reached).
_local_lock = threading.Lock()
_local_window = ""
_local_count = 0

# Throttle the "budget exhausted" log so we don't spam once we hit the cap.
_last_exhausted_log = 0.0


def _window_key() -> str:
    return f"finmind:budget:{datetime.now(timezone.utc):%Y%m%d%H}"


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


def _consume_local(weight: int) -> bool:
    global _local_window, _local_count
    key = _window_key()
    with _local_lock:
        if key != _local_window:
            _local_window = key
            _local_count = 0
        _local_count += weight
        return _local_count <= HOURLY_CAP


def consume(weight: int = 1) -> bool:
    """
    Account for `weight` FinMind HTTP requests against the current hour's budget.

    Returns True if the call is within budget (and should proceed), False if the
    hourly cap is already exhausted (the caller should serve stale cache / "unavailable"
    rather than hit FinMind).
    """
    client = _get_sync_redis()
    if client is None:
        return _consume_local(weight)
    try:
        key = _window_key()
        count = client.incrby(key, weight)
        if count == weight:  # first write in this window
            client.expire(key, _WINDOW_SECONDS)
        within = count <= HOURLY_CAP
        if not within:
            _maybe_log_exhausted(count)
        return within
    except Exception as e:  # Redis hiccup mid-flight — fall back, don't block forever
        logger.debug(f"FinMind budget: redis incr failed, falling back to local: {e}")
        return _consume_local(weight)


def _maybe_log_exhausted(count: int) -> None:
    global _last_exhausted_log
    now = time.time()
    if now - _last_exhausted_log > 60:
        _last_exhausted_log = now
        logger.warning(
            f"FinMind hourly budget exhausted ({count}/{HOURLY_CAP}); serving stale/"
            f"unavailable for TW stock data until the next clock-hour."
        )


def remaining() -> int:
    """Best-effort remaining budget for the current hour (for logging/alerts)."""
    client = _get_sync_redis()
    if client is None:
        with _local_lock:
            used = _local_count if _window_key() == _local_window else 0
        return max(0, HOURLY_CAP - used)
    try:
        used = int(client.get(_window_key()) or 0)
        return max(0, HOURLY_CAP - used)
    except Exception:
        return HOURLY_CAP
