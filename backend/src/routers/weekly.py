"""Weekly rollup pages (TKB-013): what the tracked podcasts covered in one ISO week.

One dated URL per week (``/weekly/2026-W36``) gives search engines a fresh, unique page
every week without any new content pipeline: everything here is aggregated from the
release-scoped episode list and the ticker insights the pipeline already writes.

Weeks are Monday–Sunday in Asia/Taipei, the audience's calendar. Past weeks are stable
and cached for a day; the current week keeps growing and is cached for an hour.
"""

import asyncio
import json
import logging
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException

from src.cache.redis_client import cache_get, cache_set
from src.services.insight_service import InsightService
from src.services.podcast import PodcastService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/weekly", tags=["weekly"])

podcast_service = PodcastService()
insight_service = InsightService()

TAIPEI = ZoneInfo("Asia/Taipei")
TOP_TICKERS = 15
TOP_SECTORS = 10


def week_bounds(week: str) -> tuple[date, date]:
    """``2026-W36`` → (Monday, Sunday) dates. Raises ValueError on bad input."""
    year_s, _, num_s = week.partition("-W")
    if not year_s.isdigit() or not num_s.isdigit():
        raise ValueError(week)
    monday = date.fromisocalendar(int(year_s), int(num_s), 1)
    return monday, monday + timedelta(days=6)


def week_of_ms(ms: int) -> str:
    d = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone(TAIPEI).date()
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def _released_ms(ep) -> Optional[int]:
    return getattr(ep, "released_at_ms", None) or getattr(ep, "created_time", None)


def _in_week(ep, week: str) -> bool:
    ms = _released_ms(ep)
    return ms is not None and week_of_ms(ms) == week


def _sentiment(label) -> str:
    s = str(label or "").upper()
    if s in ("BULLISH", "BULL", "POSITIVE", "STRONG_BULLISH"):
        return "bull"
    if s in ("BEARISH", "BEAR", "NEGATIVE", "STRONG_BEARISH"):
        return "bear"
    return "neu"


async def _insights_for(podcasters: list[str], start: date, end: date) -> list[dict]:
    """Every ticker insight the given podcasters published inside [start, end]."""
    results = await asyncio.gather(
        *[insight_service.get_by_podcaster(p, start_date=start.isoformat(), end_date=end.isoformat()) for p in podcasters],
        return_exceptions=True,
    )
    out: list[dict] = []
    for r in results:
        if isinstance(r, list):
            out.extend(r)
    return out


def _tally(insights: list[dict]) -> dict[str, Counter]:
    by: dict[str, Counter] = defaultdict(Counter)
    for i in insights:
        tk = i.get("ticker")
        if tk:
            by[tk][_sentiment(i.get("sentiment_label"))] += 1
    return by


async def build_week(week: str) -> Optional[dict]:
    """The rollup for one week, or None when no scoped episode falls in it."""
    start, end = week_bounds(week)
    episodes = [ep for ep in await podcast_service.get_recent_episodes(limit=5000, enrich_content=False) if _in_week(ep, week)]
    if not episodes:
        return None

    prev_start, prev_end = start - timedelta(days=7), start - timedelta(days=1)
    podcasters = sorted({ep.podcast_name for ep in episodes if getattr(ep, "podcast_name", None)})
    this_ins, prev_ins = await asyncio.gather(
        _insights_for(podcasters, start, end),
        _insights_for(podcasters, prev_start, prev_end),
    )
    this_t, prev_t = _tally(this_ins), _tally(prev_ins)

    ticker_eps: Counter = Counter()
    names: dict[str, str] = {}
    sector_eps: Counter = Counter()
    sector_meta: dict[str, dict] = {}
    for ep in episodes:
        for tk in getattr(ep, "related_tickers", None) or []:
            ticker_eps[str(tk)] += 1
        seen: set[str] = set()
        for s in getattr(ep, "sector_exposures", None) or []:
            sid = s.get("exposure_id") if isinstance(s, dict) else getattr(s, "exposure_id", None)
            if not sid or sid in seen:
                continue
            seen.add(sid)
            sector_eps[sid] += 1
            if sid not in sector_meta:
                get = (lambda k: s.get(k)) if isinstance(s, dict) else (lambda k: getattr(s, k, None))
                sector_meta[sid] = {"display_name": get("display_name") or sid, "icon_id": get("icon_id"), "color_hex": get("color_hex")}
            for t in (s.get("resolved_tickers") if isinstance(s, dict) else getattr(s, "resolved_tickers", None)) or []:
                tk = t.get("ticker") if isinstance(t, dict) else getattr(t, "ticker", None)
                nm = t.get("name") if isinstance(t, dict) else getattr(t, "name", None)
                if tk and nm:
                    names.setdefault(str(tk), nm)

    def ticker_row(tk: str, n: int) -> dict:
        cur, prev = this_t.get(tk, Counter()), prev_t.get(tk, Counter())
        return {
            "ticker": tk, "name": names.get(tk), "episodes": n,
            "bull": cur["bull"], "neu": cur["neu"], "bear": cur["bear"],
            "prev_bull": prev["bull"], "prev_neu": prev["neu"], "prev_bear": prev["bear"],
        }

    return {
        "week": week,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "episode_count": len(episodes),
        "podcasts": [{"name": n, "episodes": c} for n, c in Counter(ep.podcast_name for ep in episodes).most_common()],
        "tickers": [ticker_row(tk, n) for tk, n in ticker_eps.most_common(TOP_TICKERS)],
        "sectors": [{"exposure_id": sid, "episodes": n, **sector_meta[sid]} for sid, n in sector_eps.most_common(TOP_SECTORS)],
        "episodes": [
            {
                "id": ep.id, "podcast_name": ep.podcast_name, "episode_title": ep.episode_title,
                "episode_number": getattr(ep, "episode_number", None), "released_at_ms": _released_ms(ep),
                "key_insights": (getattr(ep, "key_insights", None) or [])[:3],
                "related_tickers": (getattr(ep, "related_tickers", None) or [])[:8],
            }
            for ep in sorted(episodes, key=lambda e: _released_ms(e) or 0, reverse=True)
        ],
    }


async def list_weeks() -> list[dict]:
    """Weeks that have at least one scoped episode, newest first."""
    counts: Counter = Counter()
    for ep in await podcast_service.get_recent_episodes(limit=5000, enrich_content=False):
        ms = _released_ms(ep)
        if ms:
            counts[week_of_ms(ms)] += 1
    out = []
    for wk, n in sorted(counts.items(), reverse=True):
        s, e = week_bounds(wk)
        out.append({"week": wk, "start": s.isoformat(), "end": e.isoformat(), "episode_count": n})
    return out


@router.get("")
async def get_weeks():
    cache_key = f"weekly:list:v1:{PodcastService._scope_tag()}"
    cached = await cache_get(cache_key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass
    payload = {"weeks": await list_weeks()}
    try:
        await cache_set(cache_key, json.dumps(payload), 3600)
    except Exception:
        pass
    return payload


@router.get("/{week}")
async def get_week(week: str):
    try:
        week_bounds(week)
    except ValueError:
        raise HTTPException(status_code=400, detail="week must look like 2026-W36")
    cache_key = f"weekly:v1:{PodcastService._scope_tag()}:{week}"
    cached = await cache_get(cache_key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass
    payload = await build_week(week)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"no episodes in {week}")
    current = week_of_ms(int(datetime.now(tz=timezone.utc).timestamp() * 1000)) == week
    try:
        await cache_set(cache_key, json.dumps(payload), 3600 if current else 86400)
    except Exception:
        pass
    return payload
