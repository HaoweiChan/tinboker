"""
Podcast mention + post-mention performance endpoints (TKB-001).

Serves content_mentions joined to the performance snapshot tables — all
Postgres, no Firestore on the request path. Every response carries a zh-TW
disclaimer: podcast mentions are NOT investment recommendations.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from src.cache.cdn_cache import CacheProfile, cdn_cache_trending, cdn_cached
from src.database.postgres import get_session
from src.database.models import (
    ContentMention,
    SectorPerformanceSnapshot,
    StockTranslation,
    TickerPerformanceSnapshot,
)
from src.services.attention import WINDOW_DAYS as _LEVEL_WINDOW_DAYS, attention_level, scope_mentions
from src.models.user import UserResponse
from src.services.podcast import PodcastService
from src.utils.dependencies import require_member

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["mentions"])
# ponytail: same module-level instance the other routers use; only its release scope is read here.
podcast_service = PodcastService()

DISCLAIMER = (
    "本頁面之播客提及與後續表現統計僅供資訊參考，並非投資建議。"
    "節目提及不代表推薦買賣；過去績效不代表未來表現，投資前請自行評估風險。"
)


def _performance_dict(snap) -> Optional[dict]:
    if snap is None:
        return None
    return {
        "baseline_close": snap.baseline_close,
        "r1d": snap.r1d,
        "r5d": snap.r5d,
        "r20d": snap.r20d,
        "r60d": snap.r60d,
    }


def _sector_performance_dict(snap) -> Optional[dict]:
    if snap is None:
        return None
    return {
        "member_count": snap.member_count,
        "r1d": snap.r1d,
        "r5d": snap.r5d,
        "r20d": snap.r20d,
        "r60d": snap.r60d,
    }


def _mention_dict(mention: ContentMention, performance: Optional[dict]) -> dict:
    return {
        "episode_id": mention.episode_id,
        "podcaster": mention.podcaster,
        "mention_type": mention.mention_type,
        "ticker": mention.ticker,
        "exposure_id": mention.exposure_id,
        "display_name": mention.display_name,
        "market": mention.market,
        "mentioned_at": mention.mentioned_at.isoformat() + "Z",
        "mention_start_s": mention.mention_start_s,
        "confidence": mention.confidence,
        "extraction_method": mention.extraction_method,
        "sentiment_label": mention.sentiment_label,
        "thesis": mention.thesis,
        "performance": performance,
    }


def _ticker_mentions(db: Session, tickers: List[str], limit: int, allowed: Optional[frozenset]) -> List[dict]:
    rows = (
        scope_mentions(db.query(ContentMention, TickerPerformanceSnapshot), allowed)
        .outerjoin(TickerPerformanceSnapshot, TickerPerformanceSnapshot.mention_id == ContentMention.id)
        .filter(ContentMention.mention_type == "ticker", ContentMention.ticker.in_(tickers))
        .order_by(ContentMention.mentioned_at.desc())
        .limit(limit)
        .all()
    )
    return [_mention_dict(m, _performance_dict(s)) for m, s in rows]


@router.get("/tickers/{ticker}/mentions")
@cdn_cache_trending
async def get_ticker_mentions(
    ticker: str,
    limit: int = Query(default=50, ge=1, le=200),
):
    """Podcast mentions of one ticker with post-mention 1/5/20/60 trading-day returns."""
    canonical = ticker.upper().replace(".TW", "").strip()
    allowed = await podcast_service._allowed_podcast_names()
    for db in get_session():
        mentions = _ticker_mentions(db, [canonical, ticker.upper()], limit, allowed)
        return {"ticker": canonical, "mentions": mentions, "disclaimer": DISCLAIMER}
    return {"ticker": canonical, "mentions": [], "disclaimer": DISCLAIMER}


@router.get("/sectors/{exposure_id}/mentions")
@cdn_cache_trending
async def get_sector_mentions(
    exposure_id: str,
    limit: int = Query(default=50, ge=1, le=200),
):
    """Podcast mentions of one sector/theme with post-mention member-average returns."""
    allowed = await podcast_service._allowed_podcast_names()
    for db in get_session():
        rows = (
            scope_mentions(db.query(ContentMention, SectorPerformanceSnapshot), allowed)
            .outerjoin(SectorPerformanceSnapshot, SectorPerformanceSnapshot.mention_id == ContentMention.id)
            .filter(ContentMention.mention_type == "sector", ContentMention.exposure_id == exposure_id)
            .order_by(ContentMention.mentioned_at.desc())
            .limit(limit)
            .all()
        )
        mentions = [_mention_dict(m, _sector_performance_dict(s)) for m, s in rows]
        return {"exposure_id": exposure_id, "mentions": mentions, "disclaimer": DISCLAIMER}
    return {"exposure_id": exposure_id, "mentions": [], "disclaimer": DISCLAIMER}


@router.get("/episodes/{episode_id}/mentions")
@cdn_cache_trending
async def get_episode_mentions(episode_id: str):
    """All ticker + sector mentions extracted from one episode, with performance."""
    allowed = await podcast_service._allowed_podcast_names()
    for db in get_session():
        rows = (
            scope_mentions(db.query(ContentMention), allowed)
            .filter(ContentMention.episode_id == episode_id)
            .order_by(ContentMention.mention_type, ContentMention.ticker)
            .all()
        )
        ticker_snaps = {
            s.mention_id: s
            for s in db.query(TickerPerformanceSnapshot)
            .filter(TickerPerformanceSnapshot.mention_id.in_([m.id for m in rows] or [0]))
            .all()
        }
        sector_snaps = {
            s.mention_id: s
            for s in db.query(SectorPerformanceSnapshot)
            .filter(SectorPerformanceSnapshot.mention_id.in_([m.id for m in rows] or [0]))
            .all()
        }
        ticker_mentions, sector_mentions, macro_mentions = [], [], []
        for m in rows:
            if m.mention_type == "ticker":
                ticker_mentions.append(_mention_dict(m, _performance_dict(ticker_snaps.get(m.id))))
            elif m.mention_type == "sector":
                sector_mentions.append(_mention_dict(m, _sector_performance_dict(sector_snaps.get(m.id))))
            elif m.mention_type == "macro":
                # exposure_id = indicator id (US10Y…), thesis = the claim, sentiment_label =
                # expected direction; the quoted level and reasons ride in payload.
                macro_mentions.append({**_mention_dict(m, None), **(m.payload or {})})
        return {
            "episode_id": episode_id,
            "ticker_mentions": ticker_mentions,
            "sector_mentions": sector_mentions,
            "macro_mentions": macro_mentions,
            "disclaimer": DISCLAIMER,
        }
    return {
        "episode_id": episode_id,
        "ticker_mentions": [],
        "sector_mentions": [],
        "macro_mentions": [],
        "disclaimer": DISCLAIMER,
    }


# ── Cross-show view of one episode ────────────────────────────────────────────
# An episode page used to be the episode alone: a summary of what one show said. The
# thing only this site can add is the other shows — who else was talking about the same
# names in the same weeks, and whether they leaned the same way.
CROSS_SHOW_WINDOW_DAYS = 30
# A lean needs this share of the other shows' mentions; below it they "disagree".
_LEAN_SHARE = 0.6


def _stance(label: Optional[str]) -> Optional[str]:
    s = (label or "").upper()
    if "BULL" in s or s == "POSITIVE":
        return "BULLISH"
    if "BEAR" in s or s == "NEGATIVE":
        return "BEARISH"
    if s in ("NEUTRAL", "NEUT", "MIXED"):
        return "NEUTRAL"
    return None


def _cross_show_lean(bull: int, neutral: int, bear: int) -> Optional[str]:
    total = bull + neutral + bear
    if total == 0:
        return None
    return next((k for k, n in (("BULLISH", bull), ("BEARISH", bear), ("NEUTRAL", neutral))
                 if n / total >= _LEAN_SHARE), None)


def cross_show_relation(mine: Optional[str], bull: int, neutral: int, bear: int) -> str:
    """How this episode's stance on a ticker sits against the other shows' mentions.

    Descriptive only — it compares public statements with each other, never with the
    price. ``alone``: nobody else mentioned it. ``split``: the others have no lean.
    ``aligned`` / ``opposite``: same or reverse of the others' lean. ``reserved``: the
    others lean one way and this episode is neutral. ``firmer``: the others are mostly
    neutral and this episode takes a side.
    """
    total = bull + neutral + bear
    if total == 0:
        return "alone"
    lean = _cross_show_lean(bull, neutral, bear)
    if lean is None:
        return "split"
    if mine == lean:
        return "aligned"
    if lean == "NEUTRAL":
        return "firmer" if mine in ("BULLISH", "BEARISH") else "split"
    return "opposite" if mine in ("BULLISH", "BEARISH") else "reserved"


@router.get("/episodes/{episode_id}/cross-show")
@cdn_cache_trending
async def get_episode_cross_show_teaser(episode_id: str):
    """Public episode subjects and aggregate cross-show comparison counts.

    Other shows' per-subject opinions belong only to the member route below. This is
    also what the crawler body prints, so it must never carry comparison rows.
    """
    full = await _cross_show(episode_id)
    compared = [r for r in full["rows"] if r["others"]["shows"] > 0]
    return {**full, "rows": [], "compared": len(compared),
            "opposite": sum(r["relation"] == "opposite" for r in compared)}


@router.get("/episodes/{episode_id}/cross-show/detail")
@cdn_cached(profile=CacheProfile.PRIVATE)
async def get_episode_cross_show(episode_id: str, _user: UserResponse = Depends(require_member)):
    """Members-only (401 anonymous, 402 non-member). PRIVATE: Cloudflare caches every
    `GET /api/*` by URL with no Vary on Authorization."""
    return await _cross_show(episode_id)


async def _cross_show(episode_id: str) -> dict:
    """For each ticker or theme this episode discussed: how many OTHER shows mentioned it in the
    30 days up to the episode's release day, how those mentions split, and how this
    episode's stance relates to them.

    The window ends on the release day, not today, so the answer describes the moment
    the episode aired and does not drift afterwards. Scoped to the release roster like
    every other mention read.
    """
    empty = {"episode_id": episode_id, "window_days": CROSS_SHOW_WINDOW_DAYS, "podcaster": None,
             "as_of": None, "shows_in_window": 0, "subjects": [], "rows": [], "disclaimer": DISCLAIMER}
    allowed = await podcast_service._allowed_podcast_names()
    for db in get_session():
        subject_filter = or_(
            and_(ContentMention.mention_type == "ticker", ContentMention.ticker.isnot(None)),
            and_(ContentMention.mention_type == "sector", ContentMention.exposure_id.isnot(None)),
        )
        mine = (
            scope_mentions(db.query(ContentMention), allowed)
            .filter(ContentMention.episode_id == episode_id, subject_filter)
            .all()
        )
        if not mine:
            return empty
        podcaster = mine[0].podcaster
        aired = max(m.mentioned_at for m in mine)
        end = datetime(aired.year, aired.month, aired.day) + timedelta(days=1)
        start = end - timedelta(days=CROSS_SHOW_WINDOW_DAYS + 1)
        window = (
            scope_mentions(db.query(ContentMention.mention_type, ContentMention.ticker,
                                    ContentMention.exposure_id, ContentMention.podcaster,
                                    ContentMention.sentiment_label), allowed)
            .filter(subject_filter,
                    ContentMention.mentioned_at >= start,
                    ContentMention.mentioned_at < end,
                    ContentMention.episode_id != episode_id)
            .all()
        )
        shows_in_window = {p for _, _, _, p, _ in window if p} | ({podcaster} if podcaster else set())
        mine_by_subject = {(m.mention_type, m.ticker if m.mention_type == "ticker" else m.exposure_id): m
                           for m in mine}
        others: dict = {key: {"shows": set(), "bull": 0, "neutral": 0, "bear": 0, "unknown": 0} for key in mine_by_subject}
        for mention_type, ticker, exposure_id, show, label in window:
            key = (mention_type, ticker if mention_type == "ticker" else exposure_id)
            # Another episode of the SAME show is not a second opinion.
            if key not in others or not show or show == podcaster:
                continue
            o = others[key]
            o["shows"].add(show)
            stance = _stance(label)
            o[{"BULLISH": "bull", "BEARISH": "bear", "NEUTRAL": "neutral"}.get(stance, "unknown")] += 1
        # content_mentions rarely carries a display name for tickers; the translation
        # table is where the site's zh-TW names live.
        names = {
            tk: zh or en
            for tk, zh, en in db.query(StockTranslation.ticker, StockTranslation.name_zh_tw,
                                       StockTranslation.name_en)
            .filter(StockTranslation.ticker.in_([m.ticker for m in mine if m.mention_type == "ticker"])).all()
        }
        subjects = []
        rows = []
        for key, m in mine_by_subject.items():
            o = others[key]
            stance = _stance(m.sentiment_label)
            subject = {
                "mention_type": m.mention_type,
                "ticker": m.ticker if m.mention_type == "ticker" else None,
                "exposure_id": m.exposure_id if m.mention_type == "sector" else None,
                "name": (names.get(m.ticker) if m.mention_type == "ticker" else None) or m.display_name,
                "stance": stance,
            }
            subjects.append(subject)
            rows.append({
                **subject,
                "others": {"shows": len(o["shows"]),
                           "mentions": o["bull"] + o["neutral"] + o["bear"] + o["unknown"],
                           "bull": o["bull"], "neutral": o["neutral"], "bear": o["bear"],
                           "unknown": o["unknown"],
                           "lean": _cross_show_lean(o["bull"], o["neutral"], o["bear"])},
                "relation": ("split" if o["unknown"] and not (o["bull"] + o["neutral"] + o["bear"])
                             else cross_show_relation(stance, o["bull"], o["neutral"], o["bear"])),
            })
        subjects.sort(key=lambda s: (s["mention_type"], s["ticker"] or s["exposure_id"]))
        rows.sort(key=lambda r: (-r["others"]["shows"], -r["others"]["mentions"],
                                 r["mention_type"], r["ticker"] or r["exposure_id"]))
        return {
            "episode_id": episode_id,
            "window_days": CROSS_SHOW_WINDOW_DAYS,
            "podcaster": podcaster,
            "as_of": aired.date().isoformat(),
            "shows_in_window": len(shows_in_window),
            "subjects": subjects,
            "rows": rows,
            "disclaimer": DISCLAIMER,
        }
    return empty


# The card's window. Matches the "近 30 天" label on the consensus tile it feeds.
_HEAT_INDEX_DAYS = 30
_HEAT_HALF_LIFE_DAYS = 7.0


def _heat_index(db, ticker_variants: List[str], allowed: Optional[frozenset]) -> Optional[int]:
    """This ticker's discussion heat as 0-100, where 100 is the busiest ticker on the site.

    A raw share is unreadable here: over 30 days the median mentioned ticker holds 0.059%
    of all discussion — half of them were named exactly once — and even TSMC, second on
    the whole site, is 3.94%. Printed as a percentage almost every stock shows "0.0%",
    which reads as nothing rather than as "rarely discussed". Anchoring to the busiest
    ticker spreads the same information across a range people can feel.

    Decayed the same way as everything else here (0.5^(age/7)), so a ticker named once
    yesterday outranks one named once three weeks ago.
    """
    age_days = func.extract("epoch", func.now() - ContentMention.mentioned_at) / 86400.0
    heat = func.sum(func.power(0.5, age_days / _HEAT_HALF_LIFE_DAYS)).label("heat")
    since = datetime.utcnow() - timedelta(days=_HEAT_INDEX_DAYS)
    per_ticker = (
        scope_mentions(db.query(ContentMention.ticker.label("ticker"), heat), allowed)
        .filter(ContentMention.mention_type == "ticker",
                ContentMention.ticker.isnot(None),
                ContentMention.mentioned_at >= since)
        .group_by(ContentMention.ticker)
        .subquery()
    )
    top = db.query(func.max(per_ticker.c.heat)).scalar()
    mine = (
        db.query(per_ticker.c.heat)
        .filter(per_ticker.c.ticker.in_(ticker_variants))
        .order_by(per_ticker.c.heat.desc())
        .first()
    )
    if not top or top <= 0 or not mine or not mine[0]:
        return None
    return max(0, min(100, round(float(mine[0]) / float(top) * 100)))


@router.get("/tickers/{ticker}/mention-heat")
@cdn_cache_trending
async def get_mention_heat(
    ticker: str,
    days: int = Query(default=730, ge=30, le=1825, description="Look-back window in days"),
):
    """Daily mention counts for one ticker AND for the whole market, over one window.

    Both series come back from ONE call and ONE table on purpose. The chart plots the
    ticker's share of all podcast attention, not its raw count, because the raw count
    mostly tracks how many shows we had ingested at the time: over the two years to
    2026-09, TSMC's decayed heat rose 10x while the market's rose 5.7x, and its actual
    share sat flat between 3.5% and 5.9% the whole time. A numerator and a denominator
    taken from different tables would silently mix two populations, so they are taken
    together here rather than assembled by the caller from two endpoints.

    Counts, not heat: the decay (0.5^(age/7), the platform's 討論熱度 definition) is
    applied client-side against the chart's own trading sessions, so it lines up with the
    bars actually drawn rather than with calendar days the market was shut.

    `level` is 聲量水位 — the share's percentile inside the ticker's own trailing year,
    0-100 per calendar day — computed here (services/attention.py) rather than by the
    chart so the stock page and the weekly can never hold two definitions of it.

    Every query is scoped to the release roster, like the episode surfaces: an English
    batch landing in the store must not move a TW ticker's share or its level.
    """
    canonical = ticker.upper().replace(".TW", "").strip()
    variants = [canonical, ticker.upper()]
    today = datetime.utcnow().date()
    since = today - timedelta(days=days)
    day = func.date(ContentMention.mentioned_at)
    allowed = await podcast_service._allowed_podcast_names()
    for db in get_session():
        base = scope_mentions(db.query(day, func.count(1)), allowed).filter(
            ContentMention.mention_type == "ticker",
            ContentMention.mentioned_at >= since,
        )
        market_rows = base.group_by(day).all()
        rows = (
            scope_mentions(db.query(day, func.count(1),
                             func.count(1).filter(ContentMention.sentiment_label.like("%BULLISH%")),
                             func.count(1).filter(ContentMention.sentiment_label.like("%BEARISH%"))),
                    allowed)
            .filter(ContentMention.mention_type == "ticker",
                    ContentMention.ticker.in_(variants),
                    ContentMention.mentioned_at >= since)
            .group_by(day)
            .all()
        )
        return {
            "ticker": canonical,
            "half_life_days": 7,
            "heat_index": _heat_index(db, variants, allowed),
            "heat_index_days": _HEAT_INDEX_DAYS,
            "series": [{"d": str(d), "n": n, "bull": b, "bear": r} for d, n, b, r in rows],
            "market": [{"d": str(d), "n": n} for d, n in market_rows],
            "level": attention_level({d: n for d, n, _, _ in rows}, dict(market_rows), today),
            "level_window_days": _LEVEL_WINDOW_DAYS,
            "disclaimer": DISCLAIMER,
        }
    return {"ticker": canonical, "half_life_days": 7, "heat_index": None,
            "heat_index_days": _HEAT_INDEX_DAYS, "series": [], "market": [],
            "level": [], "level_window_days": _LEVEL_WINDOW_DAYS, "disclaimer": DISCLAIMER}
