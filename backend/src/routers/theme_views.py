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
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from src.auth.admin_auth import AdminAccess, get_content_write_access, get_social_access
from src.cache.cdn_cache import CacheProfile, cdn_cached
from src.config import settings
from src.database.models import TagRegistry, ThemeView
from src.database.postgres import session_scope
from src.models.user import UserResponse
from src.routers.stock import BatchPricesSinceRequest, TickerDatePair, get_batch_prices_windows
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


def build_cards(
    rows: list, limit: int, members_by_exposure: Optional[dict[str, list]] = None,
    public_since: Optional[datetime] = None,
) -> List[dict]:
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
            tickers = sorted(counts.values(), key=lambda c: (-c["mentions"], c["ticker"]))
            tickers_source = "named" if tickers else "none"
            if not tickers and first.exposure_id:
                members = (members_by_exposure or {}).get(first.exposure_id, [])
                # Stable sorting preserves stored order for ties and unranked members.
                members = sorted(
                    (m for m in members if m.get("ticker")),
                    key=lambda m: m.get("rank") if isinstance(m.get("rank"), (int, float)) else float("inf"),
                )
                tickers = [{"ticker": m["ticker"], "name": m.get("name") or m["ticker"], "mentions": 0}
                           for m in members[:5]]
                if tickers:
                    tickers_source = "members"
            cards.append({
                "key": f"{podcaster}|{key}|{_ms(first.released_at)}",
                "podcaster": podcaster,
                "theme_key": key,
                "theme_label": last.theme_label,
                "exposure_id": first.exposure_id,
                "first_ms": _ms(first.released_at),
                "latest_ms": _ms(last.released_at),
                "tickers": tickers,
                "tickers_source": tickers_source,
                "mentions": [{
                    "episode_id": r.episode_id, "episode_number": r.episode_number,
                    "released_at_ms": _ms(r.released_at), "stance": r.stance,
                    # Cards read further back than the public episode window; the UI
                    # must not link to (or play) an episode the window no longer serves.
                    "episode_public": public_since is None or r.released_at >= public_since,
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
        rows = query.all()
        exposure_ids = {row.exposure_id for row in rows if row.exposure_id}
        members = db.query(TagRegistry.exposure_id, TagRegistry.members).filter(
            TagRegistry.exposure_id.in_(exposure_ids),
        ).all()
        days = getattr(settings, "release_episode_max_age_days", 0) or 0
        public_since = datetime.utcnow() - timedelta(days=days) if days > 0 else None
        return build_cards(rows, limit, {row.exposure_id: row.members or [] for row in members}, public_since)


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


# ── Copywriting access ───────────────────────────────────────────────────────
# The same cards and forward returns members see, for the social copy pipeline and
# agent sessions: TINBOKER_SOCIAL_TOKEN or an admin JWT, never a member login.
WINDOW_KEYS = ("since", "d7", "d30", "d90")


def with_performance(cards: List[dict], windows: dict) -> List[dict]:
    """Attach each ticker's forward returns and the card's per-window mean — the numbers
    ThemeCard.tsx shows — so a copywriter never joins or averages by hand."""
    for card in cards:
        for t in card["tickers"]:
            t["windows"] = windows.get(f'{t["ticker"].upper()}:{card["first_ms"]}')
        card["averages"] = {}
        for key in WINDOW_KEYS:
            values = [t["windows"][key] for t in card["tickers"]
                      if t["windows"] and t["windows"].get(key) is not None]
            card["averages"][key] = round(sum(values) / len(values), 2) if values else None
    return cards


@router.post("/copy/windows")
async def post_copy_windows(body: BatchPricesSinceRequest, _svc: AdminAccess = Depends(get_social_access)):
    """Forward 7/30/90D (+ since) returns per stock pick, as `/api/stocks/batch-prices-windows`
    serves members. Pair with the public mention endpoints to rebuild a stock card."""
    # The member route's body never reads its user; the gate here is the service token.
    return await get_batch_prices_windows(body, _user=None)


@router.get("/copy/cards")
@cdn_cached(profile=CacheProfile.PRIVATE)
async def get_copy_cards(
    podcaster: Optional[str] = Query(None, max_length=255),
    theme: Optional[str] = Query(None, max_length=80, description="Substring of the theme label"),
    limit: int = Query(20, ge=1, le=60),
    _svc: AdminAccess = Depends(get_social_access),
):
    """Theme cards with their returns already attached, newest run first."""
    # Filters the newest 200 runs: pass `podcaster` to reach one show's older themes.
    cards = await asyncio.to_thread(_cards, podcaster, 200)
    cards = [c for c in cards if not theme or theme in c["theme_label"]][:limit]
    items = [TickerDatePair(ticker=t["ticker"], reference_ms=c["first_ms"]) for c in cards for t in c["tickers"]]
    windows: dict = {}
    for i in range(0, len(items), 300):  # BatchPricesSinceRequest caps at 300 items
        windows.update(await get_batch_prices_windows(BatchPricesSinceRequest(items=items[i:i + 300]), _user=None))
    return with_performance(cards, windows)
