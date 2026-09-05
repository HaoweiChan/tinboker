"""
Mention sync + post-mention performance snapshots (TKB-001).

Derives content_mentions rows from the two mention sources the pipelines
already produce — the mirrored ticker_insights docs (per-episode LLM ticker
extraction) and episode sector_exposures (deterministic alias matching) — then
computes 1D/5D/20D/60D trading-day returns from the warm stock_daily_closes
table. Daily-batch only by design (TKB-001: no real-time tracking).
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from src.database.postgres import get_session
from src.database.models import (
    ContentMention,
    SectorPerformanceSnapshot,
    StockDailyClose,
    TickerPerformanceSnapshot,
)
from src.utils.market import infer_market

logger = logging.getLogger(__name__)

# Trading-day windows required by TKB-001 (rN = Nth trading day after baseline).
TRADING_WINDOWS = (1, 5, 20, 60)

# 60 trading days ≈ 85–90 calendar days; past this a mention's missing windows
# are treated as permanently unavailable (no more recomputes).
RECOMPUTE_HORIZON_DAYS = 130

# How far back each sync cycle looks for new mentions.
SYNC_LOOKBACK_DAYS = 400

# The pipeline's LLM ticker extractor doesn't emit a per-row confidence yet, so
# stamp a constant; sector exposures carry their own (alias match = 1.0).
LLM_TICKER_CONFIDENCE = 0.9

# Equal-weight sector returns are averaged over at most this many members.
MAX_SECTOR_MEMBERS = 10


def _canonical_ticker(raw: str) -> str:
    return (raw or "").upper().replace(".TW", "").strip()


def _parse_iso(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _parse_start_s(reasons: Any) -> Optional[float]:
    """First reason's start_time as seconds. The pipeline writes numbers in
    milliseconds (regen/schemas.py: "int — ms"); older docs carry H:MM:SS."""
    if isinstance(reasons, str):
        try:
            reasons = json.loads(reasons)
        except ValueError:
            return None
    if not isinstance(reasons, list) or not reasons:
        return None
    raw = reasons[0].get("start_time") if isinstance(reasons[0], dict) else None
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw) / 1000.0
    text = str(raw).strip()
    try:
        if ":" not in text:  # a few docs stringify the ms integer ("3695725")
            return float(text) / 1000.0
        secs = 0.0
        for part in text.split(":"):
            secs = secs * 60 + float(part)
        return secs
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Source 1: ticker mentions from the pipeline-written ticker_insights table
# ---------------------------------------------------------------------------

def _fetch_recent_insight_rows(days: int) -> List[dict]:
    """Recent ticker_insights docs via the same read path /api/ticker-insights
    uses (Postgres mirror, or Firestore when the mirror flag is off). The flat
    public.ticker_insights table this used to query never existed on the VPS."""
    from src.services.postgres_mirror_service import content_read_service

    cutoff = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00")
    return content_read_service().query_collection_group(
        "tickers", filters=[("podcast_launch_time", ">=", cutoff)],
    )


def _existing_keys(db: Session) -> set:
    return {k for (k,) in db.query(ContentMention.mention_key).all()}


def sync_ticker_mentions(db: Session, days: int = SYNC_LOOKBACK_DAYS) -> int:
    """Upsert ticker mentions into content_mentions. Returns rows inserted.

    Existing rows whose mention_start_s no longer matches the source get it
    re-set (heals the rows written while ms were stored as seconds); after
    the first pass that is a no-op."""
    rows = _fetch_recent_insight_rows(days)
    stored = dict(db.query(ContentMention.mention_key, ContentMention.mention_start_s).all())
    seen = set(stored)
    inserted = healed = 0
    for row in rows:
        ticker = _canonical_ticker(row.get("ticker") or "")
        episode_id = (row.get("episode_id") or "").strip()
        mentioned_at = _parse_iso(row.get("podcast_launch_time"))
        if not ticker or not episode_id or mentioned_at is None:
            continue
        key = f"{episode_id}:ticker:{ticker}"
        start_s = _parse_start_s(row.get("reasons"))
        if key in seen:
            if start_s is not None and stored[key] != start_s:
                db.query(ContentMention).filter(ContentMention.mention_key == key).update(
                    {"mention_start_s": start_s}
                )
                healed += 1
            continue
        seen.add(key)
        db.add(ContentMention(
            mention_key=key,
            episode_id=episode_id,
            source_type="podcast",
            podcaster=row.get("podcaster"),
            mention_type="ticker",
            ticker=ticker,
            market=infer_market(ticker),
            mentioned_at=mentioned_at,
            mention_start_s=start_s,
            confidence=LLM_TICKER_CONFIDENCE,
            extraction_method="pipeline_llm",
            sentiment_label=row.get("sentiment_label"),
            thesis=row.get("bluf_thesis"),
        ))
        inserted += 1
    if inserted or healed:
        db.commit()
    return inserted


# ---------------------------------------------------------------------------
# Source 2: sector mentions from episode sector_exposures
# ---------------------------------------------------------------------------

def _scan_sector_exposures() -> List[dict]:
    """One flat record per (episode, exposure) via the projected episode scan
    the sector board already uses — reuses that read path, adds no new one."""
    from src.services.podcast import PodcastService

    service = PodcastService()
    docs = service.firestore_service.stream_documents_projected(
        "episodes", service._SECTOR_SCAN_FIELDS,
    )
    records: List[dict] = []
    for doc in docs:
        if doc.get("retracted_at"):
            continue
        episode_id = doc.get("id") or ""
        if not episode_id:
            continue
        release_ms = service._dict_release_ms(doc)
        for entry in doc.get("sector_exposures") or []:
            exposure_id = (entry.get("exposure_id") or "").strip()
            if not exposure_id:
                continue
            members = [
                _canonical_ticker(t.get("ticker") or "")
                for t in (entry.get("resolved_tickers") or [])
                if isinstance(t, dict) and t.get("ticker")
            ]
            records.append({
                "episode_id": episode_id,
                "podcaster": doc.get("podcast_name"),
                "exposure_id": exposure_id,
                "display_name": entry.get("display_name") or exposure_id,
                "confidence": entry.get("confidence"),
                "mentioned_at": datetime.utcfromtimestamp(release_ms / 1000),
                "members": [m for m in members if m][:MAX_SECTOR_MEMBERS],
                "mention_text": entry.get("mention_text"),
            })
    return records


def sync_sector_mentions(db: Session, days: int = SYNC_LOOKBACK_DAYS) -> int:
    """Upsert sector mentions into content_mentions. Returns rows inserted."""
    try:
        records = _scan_sector_exposures()
    except Exception as e:
        logger.warning("mention sync: sector exposure scan failed: %s", e)
        return 0
    cutoff = datetime.utcnow() - timedelta(days=days)
    seen = _existing_keys(db)
    inserted = 0
    for rec in records:
        if rec["mentioned_at"] < cutoff:
            continue
        # Episodes list the same exposure_id more than once (2,179 pairs on
        # 2026-09-05); with autoflush off a per-row lookup missed those and the
        # whole pass died on the unique key at commit.
        key = f"{rec['episode_id']}:sector:{rec['exposure_id']}"
        if key in seen:
            continue
        seen.add(key)
        confidence = rec.get("confidence")
        db.add(ContentMention(
            mention_key=key,
            episode_id=rec["episode_id"],
            source_type="podcast",
            podcaster=rec.get("podcaster"),
            mention_type="sector",
            exposure_id=rec["exposure_id"],
            display_name=rec.get("display_name"),
            mentioned_at=rec["mentioned_at"],
            confidence=float(confidence) if confidence is not None else 1.0,
            extraction_method="alias_match",
            payload={"members": rec.get("members") or [], "mention_text": rec.get("mention_text")},
        ))
        inserted += 1
    if inserted:
        db.commit()
    return inserted


# ---------------------------------------------------------------------------
# Post-mention returns (1D / 5D / 20D / 60D trading days)
# ---------------------------------------------------------------------------

def compute_trading_day_returns(db: Session, ticker: str, mention_date: str) -> dict:
    """Baseline close + rN percent returns for the given (ticker, mention date).

    Baseline = last close on/before mention_date (7-day lookback covers holiday
    stretches). rN = Nth stored trading date strictly after the baseline date.
    Windows without data yet stay None.
    """
    out: dict[str, Optional[float]] = {"baseline_close": None}
    for n in TRADING_WINDOWS:
        out[f"r{n}d"] = None
    window_start = (
        datetime.strptime(mention_date, "%Y-%m-%d") - timedelta(days=7)
    ).strftime("%Y-%m-%d")
    rows = (
        db.query(StockDailyClose)
        .filter(StockDailyClose.ticker == ticker, StockDailyClose.date >= window_start)
        .order_by(StockDailyClose.date.asc())
        .all()
    )
    baseline = None
    following: List[StockDailyClose] = []
    for row in rows:
        if row.date <= mention_date:
            baseline = row
        else:
            following.append(row)
    if baseline is None or not baseline.close or baseline.close <= 0:
        return out
    out["baseline_close"] = baseline.close
    for n in TRADING_WINDOWS:
        if len(following) >= n and following[n - 1].close:
            out[f"r{n}d"] = round((following[n - 1].close - baseline.close) / baseline.close * 100, 2)
    return out


def _snapshot_incomplete(snap) -> bool:
    return any(getattr(snap, f"r{n}d") is None for n in TRADING_WINDOWS) or snap.baseline_close is None


def compute_ticker_snapshots(db: Session, limit: int = 2000) -> int:
    """(Re)compute ticker performance snapshots for mentions that still need one."""
    horizon = datetime.utcnow() - timedelta(days=RECOMPUTE_HORIZON_DAYS)
    mentions = (
        db.query(ContentMention)
        .filter(ContentMention.mention_type == "ticker")
        .order_by(ContentMention.mentioned_at.desc())
        .limit(limit)
        .all()
    )
    updated = 0
    for mention in mentions:
        snap = (
            db.query(TickerPerformanceSnapshot)
            .filter(TickerPerformanceSnapshot.mention_id == mention.id)
            .first()
        )
        if snap is not None and (not _snapshot_incomplete(snap) or mention.mentioned_at < horizon):
            continue
        mention_date = mention.mentioned_at.strftime("%Y-%m-%d")
        returns = compute_trading_day_returns(db, mention.ticker, mention_date)
        if snap is None:
            snap = TickerPerformanceSnapshot(
                mention_id=mention.id, ticker=mention.ticker, mention_date=mention_date,
            )
            db.add(snap)
        snap.baseline_close = returns["baseline_close"]
        for n in TRADING_WINDOWS:
            setattr(snap, f"r{n}d", returns[f"r{n}d"])
        snap.computed_at = datetime.utcnow()
        updated += 1
    if updated:
        db.commit()
    return updated


def compute_sector_snapshots(db: Session, limit: int = 2000) -> int:
    """(Re)compute sector snapshots: equal-weight average over resolved members."""
    horizon = datetime.utcnow() - timedelta(days=RECOMPUTE_HORIZON_DAYS)
    mentions = (
        db.query(ContentMention)
        .filter(ContentMention.mention_type == "sector")
        .order_by(ContentMention.mentioned_at.desc())
        .limit(limit)
        .all()
    )
    updated = 0
    for mention in mentions:
        snap = (
            db.query(SectorPerformanceSnapshot)
            .filter(SectorPerformanceSnapshot.mention_id == mention.id)
            .first()
        )
        if snap is not None and (not _snapshot_incomplete_sector(snap) or mention.mentioned_at < horizon):
            continue
        members = ((mention.payload or {}).get("members") or [])[:MAX_SECTOR_MEMBERS]
        mention_date = mention.mentioned_at.strftime("%Y-%m-%d")
        member_returns = [
            compute_trading_day_returns(db, m, mention_date) for m in members
        ]
        member_returns = [r for r in member_returns if r["baseline_close"] is not None]
        if snap is None:
            snap = SectorPerformanceSnapshot(
                mention_id=mention.id, exposure_id=mention.exposure_id, mention_date=mention_date,
            )
            db.add(snap)
        snap.member_count = len(member_returns)
        for n in TRADING_WINDOWS:
            vals = [r[f"r{n}d"] for r in member_returns if r[f"r{n}d"] is not None]
            setattr(snap, f"r{n}d", round(sum(vals) / len(vals), 2) if vals else None)
        snap.computed_at = datetime.utcnow()
        updated += 1
    if updated:
        db.commit()
    return updated


def _snapshot_incomplete_sector(snap) -> bool:
    return snap.member_count == 0 or any(getattr(snap, f"r{n}d") is None for n in TRADING_WINDOWS)


# ---------------------------------------------------------------------------
# Periodic runner
# ---------------------------------------------------------------------------

def run_sync_cycle() -> dict:
    """One full sync + snapshot pass. Sync (blocking DB/IO) — call off-loop.

    ponytail: dev/staging/prod all run this against the one shared table; the
    loser of a same-key race rolls back and simply catches up next cycle."""
    stats = {"ticker_mentions": 0, "sector_mentions": 0, "ticker_snapshots": 0, "sector_snapshots": 0}
    for session in get_session():
        try:
            stats["ticker_mentions"] = sync_ticker_mentions(session)
        except Exception as e:
            logger.warning("mention sync: ticker mention pass failed: %s", e)
            session.rollback()
        try:
            stats["sector_mentions"] = sync_sector_mentions(session)
        except Exception as e:
            logger.warning("mention sync: sector mention pass failed: %s", e)
            session.rollback()
        try:
            stats["ticker_snapshots"] = compute_ticker_snapshots(session)
        except Exception as e:
            logger.warning("mention sync: ticker snapshot pass failed: %s", e)
            session.rollback()
        try:
            stats["sector_snapshots"] = compute_sector_snapshots(session)
        except Exception as e:
            logger.warning("mention sync: sector snapshot pass failed: %s", e)
            session.rollback()
        break
    return stats


async def run_periodic_mention_sync(interval_hours: float = 6.0) -> None:
    """Daily-batch loop (default every 6h, matching the close refresher so new
    closes get folded into snapshots the same day). Never raises."""
    await asyncio.sleep(180)  # let startup + close refresher settle first
    while True:
        try:
            stats = await asyncio.to_thread(run_sync_cycle)
            logger.info("mention sync cycle: %s", stats)
        except Exception as e:
            logger.warning("mention sync cycle failed: %s", e)
        await asyncio.sleep(interval_hours * 3600)
