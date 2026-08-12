"""
Podcast mention + post-mention performance endpoints (TKB-001).

Serves content_mentions joined to the performance snapshot tables — all
Postgres, no Firestore on the request path. Every response carries a zh-TW
disclaimer: podcast mentions are NOT investment recommendations.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Query
from sqlalchemy.orm import Session

from src.cache.cdn_cache import cdn_cache_trending
from src.database.postgres import get_session
from src.database.models import (
    ContentMention,
    SectorPerformanceSnapshot,
    TickerPerformanceSnapshot,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["mentions"])

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
