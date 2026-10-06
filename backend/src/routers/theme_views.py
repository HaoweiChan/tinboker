"""Theme views: the themes an episode discusses WITH a stance, and the members-only
"theme card" feed built from them.

`sector_exposures` on an episode are keyword matches (9-19 per episode, no stance), so
they cannot back a performance card. A theme view is extracted from the transcript:
one row per (episode, theme) with the host's stance, how firmly it was held, and the
companies named as beneficiaries. Cards group consecutive mentions of one theme by one
show into a "run" anchored on the FIRST mention — for a theme, when a show started
talking about it is the call; later mentions are the timeline.
"""
import asyncio
import re
import unicodedata
from datetime import datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from src.auth.admin_auth import AdminAccess, get_content_write_access
from src.cache.cdn_cache import CacheProfile, cdn_cached
from src.database.models import ThemeView
from src.database.postgres import session_scope
from src.models.user import UserResponse
from src.utils.dependencies import require_member

router = APIRouter(prefix="/api/theme-views", tags=["theme-views"])

# A gap longer than this between two mentions starts a new card: the show came back to
# the theme as a fresh call rather than continuing the same one.
RUN_GAP_DAYS = 45


class ThemeTicker(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ticker: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=80)
    role: Literal["beneficiary", "context"]


class ThemeViewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    theme_label: str = Field(min_length=1, max_length=80)
    exposure_id: Optional[str] = Field(None, max_length=100)
    stance: Literal["bullish", "bearish", "mixed"]
    conviction: Literal["firm", "tentative"]
    thesis: str = Field(min_length=1, max_length=400)
    start_ms: Optional[int] = Field(None, ge=0)
    tickers: List[ThemeTicker] = Field(default_factory=list, max_length=20)
    quote: Optional[str] = Field(None, max_length=200)


class EpisodeThemeViews(BaseModel):
    model_config = ConfigDict(extra="forbid")
    podcaster: str = Field(min_length=1, max_length=255)
    episode_number: Optional[str] = Field(None, max_length=20)
    released_at_ms: int = Field(gt=0)
    source: str = Field("backfill", max_length=40)
    theme_views: List[ThemeViewIn] = Field(max_length=3)


def theme_key(label: str, exposure_id: Optional[str]) -> str:
    """Stable grouping key: the taxonomy id when the label matched one, else the label
    itself normalised (width, case, spacing) so 矽光子 and ' 矽光子 ' are one theme."""
    if exposure_id:
        return exposure_id
    return "label:" + re.sub(r"\s+", "", unicodedata.normalize("NFKC", label)).casefold()


def _replace_episode(episode_id: str, body: EpisodeThemeViews) -> int:
    released = datetime.fromtimestamp(body.released_at_ms / 1000, tz=timezone.utc).replace(tzinfo=None)
    with session_scope() as db:
        db.query(ThemeView).filter_by(episode_id=episode_id).delete()
        seen = set()
        for view in body.theme_views:
            key = theme_key(view.theme_label, view.exposure_id)
            if key in seen:  # two labels for one theme in one episode: keep the first
                continue
            seen.add(key)
            db.add(ThemeView(
                episode_id=episode_id, podcaster=body.podcaster, episode_number=body.episode_number,
                released_at=released, theme_key=key, theme_label=view.theme_label,
                exposure_id=view.exposure_id, stance=view.stance, conviction=view.conviction,
                thesis=view.thesis, start_ms=view.start_ms, quote=view.quote, source=body.source,
                tickers=[t.model_dump() for t in view.tickers],
            ))
        return len(seen)


@router.put("/episode/{episode_id}")
async def put_episode_theme_views(episode_id: str, body: EpisodeThemeViews,
                                  _writer: AdminAccess = Depends(get_content_write_access)):
    """Replace one episode's theme views (idempotent; an empty list clears them)."""
    return {"episode_id": episode_id, "stored": await asyncio.to_thread(_replace_episode, episode_id, body)}


def _ms(value: datetime) -> int:
    return int(value.replace(tzinfo=timezone.utc).timestamp() * 1000)


def build_cards(rows: list, limit: int) -> List[dict]:
    """Group rows (any order) into run cards, newest run first.

    `rows` need: podcaster, theme_key, theme_label, exposure_id, episode_id,
    episode_number, released_at, stance, conviction, thesis, start_ms, quote, tickers.
    """
    groups: dict = {}
    for row in sorted(rows, key=lambda r: r.released_at):
        runs = groups.setdefault((row.podcaster, row.theme_key), [])
        if runs and (row.released_at - runs[-1][-1].released_at).days <= RUN_GAP_DAYS:
            runs[-1].append(row)
        else:
            runs.append([row])
    cards = []
    for (podcaster, key), runs in groups.items():
        for run in runs:
            first, last = run[0], run[-1]
            # Beneficiaries named anywhere in the run, most-mentioned first; the card's
            # performance is measured on these from the first mention.
            counts: dict = {}
            for row in run:
                for t in row.tickers or []:
                    if t.get("role") == "beneficiary":
                        entry = counts.setdefault(t["ticker"], {"ticker": t["ticker"], "name": t["name"], "mentions": 0})
                        entry["mentions"] += 1
            cards.append({
                "key": f"{podcaster}|{key}|{_ms(first.released_at)}",
                "podcaster": podcaster,
                "theme_key": key,
                "theme_label": last.theme_label,
                "exposure_id": first.exposure_id,
                "first_ms": _ms(first.released_at),
                "latest_ms": _ms(last.released_at),
                "tickers": sorted(counts.values(), key=lambda c: (-c["mentions"], c["ticker"])),
                "mentions": [{
                    "episode_id": r.episode_id, "episode_number": r.episode_number,
                    "released_at_ms": _ms(r.released_at), "stance": r.stance,
                    "conviction": r.conviction, "thesis": r.thesis, "start_ms": r.start_ms,
                    "quote": r.quote,
                } for r in run],
            })
    cards.sort(key=lambda c: c["latest_ms"], reverse=True)
    return cards[:limit]


def _cards(podcaster: Optional[str], limit: int) -> List[dict]:
    with session_scope() as db:
        query = db.query(ThemeView)
        if podcaster:
            query = query.filter_by(podcaster=podcaster)
        return build_cards(query.all(), limit)


@router.get("/cards")
@cdn_cached(profile=CacheProfile.PRIVATE)
async def get_theme_cards(
    podcaster: Optional[str] = Query(None, max_length=255),
    limit: int = Query(60, ge=1, le=200),
    _user: UserResponse = Depends(require_member),
):
    """Members-only theme cards, newest run first. PRIVATE: Cloudflare caches every
    `GET /api/*` by URL with no Vary on Authorization."""
    return await asyncio.to_thread(_cards, podcaster, limit)
