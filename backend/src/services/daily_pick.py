"""每日一集 — syndicate at most one episode summary a day to 方格子, the best one.

Four weeks of pushing every summary made 870 articles at a median of 7 pageviews; the
per-show medians all sit between 6 and 9, so the show barely moves the median, but the
outliers (108, 50, 27, 24 pageviews) came from 股癌, 財經一路發, 財女珍妮 and 皓角. A
summary still reads like an article, which a ticker digest does not (tried and
retired 2026-09-13), so the volume is cut instead of the format: one episode a day,
chosen by show priority (settings.daily_pick_shows, measured order) and, within a
show, by how many ticker observations the episode produced.

Reads only what the public weekly already reads (release-scoped episodes and the ticker
insights the pipeline writes); ``select_pick`` is pure. Publishing reuses the
per-episode vocus path (``routers.social.publish_episode_summary_to_vocus``) and the
shared claim-then-publish ledger, so the pick is idempotent across environments.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from src.config import settings
from src.routers.weekly import _insights_for, _released_ms, podcast_service

logger = logging.getLogger(__name__)

TAIPEI = ZoneInfo("Asia/Taipei")
# After the evening ingest (systemd timer 20:10 Asia/Taipei) has landed.
PUBLISH_AT = time(20, 40)


def day_bounds_ms(day: date) -> tuple[int, int]:
    """[start, end) of one Asia/Taipei calendar day in Unix milliseconds."""
    start = datetime.combine(day, time.min, tzinfo=TAIPEI)
    return int(start.timestamp() * 1000), int((start + timedelta(days=1)).timestamp() * 1000)


def show_priority() -> list[str]:
    return [s.strip() for s in settings.daily_pick_shows.split(",") if s.strip()]


def select_pick(episodes: list[dict], insight_counts: dict[str, int], priority: list[str], limit: int) -> list[dict]:
    """The day's episodes worth syndicating, best first. Pure.

    Only shows on the priority list qualify; earlier in the list wins, then more ticker
    observations, then the earlier release (a stable order for a stable ledger key).
    """
    rank = {name: i for i, name in enumerate(priority)}
    eligible = [e for e in episodes if e.get("podcast_name") in rank]
    eligible.sort(key=lambda e: (rank[e["podcast_name"]], -insight_counts.get(e["id"], 0), e.get("released_at_ms") or 0))
    return [{**e, "insights": insight_counts.get(e["id"], 0)} for e in eligible[:max(0, limit)]]


async def build_daily_pick(day: date) -> dict:
    """Which episode(s) tonight would send, with the ranking inputs, for review."""
    lo, hi = day_bounds_ms(day)
    episodes = [
        {"id": ep.id, "podcast_name": ep.podcast_name, "episode_title": ep.episode_title,
         "released_at_ms": _released_ms(ep)}
        for ep in await podcast_service.get_recent_episodes(limit=2000, enrich_content=False)
        if (ms := _released_ms(ep)) is not None and lo <= ms < hi
    ]
    counts: Counter = Counter()
    if episodes:
        podcasters = sorted({e["podcast_name"] for e in episodes if e.get("podcast_name")})
        # One day either side: podcast_launch_time is a UTC string, the day is Taipei.
        for i in await _insights_for(podcasters, day - timedelta(days=1), day + timedelta(days=1)):
            if i.get("ticker") and i.get("episode_id"):
                counts[i["episode_id"]] += 1
    picks = select_pick(episodes, counts, show_priority(), settings.daily_pick_limit)
    return {"day": day.isoformat(), "episode_count": len(episodes), "priority": show_priority(),
            "picks": picks, "skipped": [e["id"] for e in episodes if e["id"] not in {p["id"] for p in picks}]}


async def publish_daily_pick(day: date, *, dry_run: bool, publish: bool) -> dict:
    """Send the day's pick(s) through the per-episode vocus path and the shared ledger."""
    from src.routers.social import _syndicate_once, publish_episode_summary_to_vocus  # routers import services; keep lazy

    plan = await build_daily_pick(day)
    results = []
    for pick in plan["picks"]:
        episode = await podcast_service.get_episode_admin(pick["id"])
        if not episode:
            results.append({"episode_id": pick["id"], "posted": False, "reason": "episode_not_found"})
            continue
        result = await _syndicate_once("vocus", pick["id"], lambda ep=episode: publish_episode_summary_to_vocus(
            ep, base_url=settings.public_api_url.rstrip("/"), publish=publish, dry_run=dry_run,
        ), dry_run)
        results.append({**result, "podcast_name": pick["podcast_name"], "insights": pick["insights"]})
    return {**plan, "results": results}


async def run_periodic_daily_pick(interval_seconds: float = 600.0) -> None:
    """Background loop: once a day, after PUBLISH_AT Asia/Taipei, send today's pick.

    Gated by ``settings.daily_pick_autopublish`` so only the environment that owns
    syndication runs it; the ledger makes a second environment a no-op anyway. The
    per-episode ledger key means a re-tick after a publish is a no-op too.
    """
    if not settings.daily_pick_autopublish:
        return
    last_day: Optional[date] = None
    while True:
        try:
            now = datetime.now(TAIPEI)
            if now.time() >= PUBLISH_AT and last_day != now.date():
                result = await publish_daily_pick(now.date(), dry_run=False, publish=True)
                last_day = now.date()
                for r in result["results"]:
                    logger.info("daily pick %s: %s posted=%s reason=%s", now.date(), r.get("episode_id"), r.get("posted"), r.get("reason"))
                if not result["results"]:
                    logger.info("daily pick %s: nothing eligible (%d episodes)", now.date(), result["episode_count"])
        except Exception as e:  # noqa: BLE001 — a bad day must not kill the loop
            logger.exception("daily pick tick failed: %s", e)
        await asyncio.sleep(interval_seconds)
