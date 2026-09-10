"""
Podcast mention + post-mention performance endpoints (TKB-001).

Serves content_mentions joined to the performance snapshot tables — all
Postgres, no Firestore on the request path. Every response carries a zh-TW
disclaimer: podcast mentions are NOT investment recommendations.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.cache.cdn_cache import cdn_cache_trending
from src.database.postgres import get_session
from src.database.models import (
    ContentMention,
    SectorPerformanceSnapshot,
    TickerPerformanceSnapshot,
)
from src.services.attention import WINDOW_DAYS as _LEVEL_WINDOW_DAYS, attention_level
from src.services.podcast import PodcastService

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


def _ticker_mentions(db: Session, tickers: List[str], limit: int) -> List[dict]:
    rows = (
        db.query(ContentMention, TickerPerformanceSnapshot)
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
    for db in get_session():
        mentions = _ticker_mentions(db, [canonical, ticker.upper()], limit)
        return {"ticker": canonical, "mentions": mentions, "disclaimer": DISCLAIMER}
    return {"ticker": canonical, "mentions": [], "disclaimer": DISCLAIMER}


@router.get("/sectors/{exposure_id}/mentions")
@cdn_cache_trending
async def get_sector_mentions(
    exposure_id: str,
    limit: int = Query(default=50, ge=1, le=200),
):
    """Podcast mentions of one sector/theme with post-mention member-average returns."""
    for db in get_session():
        rows = (
            db.query(ContentMention, SectorPerformanceSnapshot)
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
    for db in get_session():
        rows = (
            db.query(ContentMention)
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
        ticker_mentions, sector_mentions = [], []
        for m in rows:
            if m.mention_type == "ticker":
                ticker_mentions.append(_mention_dict(m, _performance_dict(ticker_snaps.get(m.id))))
            else:
                sector_mentions.append(_mention_dict(m, _sector_performance_dict(sector_snaps.get(m.id))))
        return {
            "episode_id": episode_id,
            "ticker_mentions": ticker_mentions,
            "sector_mentions": sector_mentions,
            "disclaimer": DISCLAIMER,
        }
    return {
        "episode_id": episode_id,
        "ticker_mentions": [],
        "sector_mentions": [],
        "disclaimer": DISCLAIMER,
    }


# The card's window. Matches the "近 30 天" label on the consensus tile it feeds.
_HEAT_INDEX_DAYS = 30
_HEAT_HALF_LIFE_DAYS = 7.0


def _scoped(query, allowed: Optional[frozenset]):
    """Restrict mention reads to the release roster (settings.release_podcast_languages).

    ContentMention reads never pass through PodcastService's chokepoint, so without this
    an English batch landing in the store moves every TW ticker's share — and, because
    聲量水位 ranks each day against a trailing year, keeps moving it for a year after.
    None means no language scope is configured; an empty set fails closed.
    """
    return query if allowed is None else query.filter(ContentMention.podcaster.in_(allowed))


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
        _scoped(db.query(ContentMention.ticker.label("ticker"), heat), allowed)
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
        base = _scoped(db.query(day, func.count(1)), allowed).filter(
            ContentMention.mention_type == "ticker",
            ContentMention.mentioned_at >= since,
        )
        market_rows = base.group_by(day).all()
        rows = (
            _scoped(db.query(day, func.count(1),
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
