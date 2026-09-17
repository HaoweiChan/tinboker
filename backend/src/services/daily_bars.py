"""Daily chart bars from Postgres, with the upstream API only filling the recent tail.

Charts used to fetch every bar from Massive (US) or FinMind (TW) on each cache miss. A
Massive 429 storm after a deploy then left a chart empty and its share card 404ing, even
though ``stock_daily_ohlc`` held the same year of bars. Compared 2026-09-17 on 12 tickers
over ~245 shared days: TW matched FinMind exactly (both unadjusted — 6669's 2026-09-02
split shows in both), US matched Massive to the half-cent except one set of rows.

That set is why US re-fetches a fixed tail instead of only what is missing: 2026-09-01 was
stored mid-session for NVDA/AMD/GOOGL/MSFT (about half the day's volume, AMD's close 1.1%
off) and later days were written normally, so the bad row sat inside the history. Every US
chart load re-fetches the last ``US_TAIL_DAYS`` and writes the closed sessions back, which
heals such rows for any ticker someone looks at. TW rows come from the official TWSE/TPEx
feeds every 6h (``tw_daily_ohlc_refresh``), so TW only fetches what is newer than the last
stored day and never writes back.

Sync on purpose: callers already run inside ``run_in_executor``.
"""

import asyncio
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.dialects.postgresql import insert as pg_insert

from src.database.models import StockDailyOHLC
from src.database.postgres import get_session

logger = logging.getLogger(__name__)

US_TAIL_DAYS = 14
# The window's first day can fall on a weekend or a holiday run (Lunar New Year closes TW
# for about a week), so a store "covers" a window whose first bar is at most this late.
COVERAGE_SLACK_DAYS = 10


def _day(d: str) -> datetime:
    return datetime.strptime(d, "%Y-%m-%d")


def read_bars(ticker: str, from_date: str, to_date: str) -> List[Dict[str, Any]]:
    """Stored bars for ``ticker`` in [from_date, to_date], ascending. NaN closes (yfinance
    marks missing days that way) are dropped: a missing day is not a price."""
    for db in get_session():
        rows = (
            db.query(StockDailyOHLC.date, StockDailyOHLC.open, StockDailyOHLC.high,
                     StockDailyOHLC.low, StockDailyOHLC.close, StockDailyOHLC.volume)
            .filter(StockDailyOHLC.ticker == ticker,
                    StockDailyOHLC.date >= from_date, StockDailyOHLC.date <= to_date)
            .order_by(StockDailyOHLC.date)
            .all()
        )
        return [
            {"date": d, "open": o, "high": h, "low": lo, "close": c, "volume": v or 0}
            for d, o, h, lo, c, v in rows
            if c is not None and math.isfinite(c)
        ]
    return []


def covers(bars: List[Dict[str, Any]], from_date: str) -> bool:
    return bool(bars) and _day(bars[0]["date"]) <= _day(from_date) + timedelta(days=COVERAGE_SLACK_DAYS)


def fetch_from(bars: List[Dict[str, Any]], from_date: str, to_date: str, *, us: bool) -> str:
    """First date the upstream must be asked for. Without full stored coverage, the whole
    window. Otherwise US re-fetches a fixed tail (to heal intraday rows, see module doc) and
    TW only what is newer than the last stored day."""
    if not covers(bars, from_date):
        return from_date
    if us:
        tail = (_day(to_date) - timedelta(days=US_TAIL_DAYS)).strftime("%Y-%m-%d")
        return max(from_date, min(tail, bars[-1]["date"]))
    return max(from_date, bars[-1]["date"])


def merge(stored: List[Dict[str, Any]], fetched: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Stored bars overlaid by fetched ones on shared dates (the upstream is fresher)."""
    by_date = {b["date"]: b for b in stored}
    by_date.update({b["date"]: b for b in fetched})
    return [by_date[d] for d in sorted(by_date)]


def write_bars(ticker: str, bars: List[Dict[str, Any]], source: str) -> int:
    """Upsert closed sessions only. A bar for a session still trading is a partial quote —
    storing it is exactly how 2026-09-01 went wrong. ``trading_value`` is left alone: the
    TW feeds own it and the upstream bars don't carry it."""
    from src.services.stock_close_refresh import close_is_final

    rows = [
        {"ticker": ticker, "date": b["date"], "open": b["open"], "high": b["high"], "low": b["low"],
         "close": b["close"], "volume": b.get("volume") or 0, "source": source}
        for b in bars
        if b.get("close") and close_is_final(ticker, b["date"])
    ]
    if not rows:
        return 0
    stmt = pg_insert(StockDailyOHLC.__table__).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["ticker", "date"],
        set_={k: stmt.excluded[k] for k in ("open", "high", "low", "close", "volume", "source")},
    )
    for db in get_session():
        db.execute(stmt)
        db.commit()
    return len(rows)


def display_name(ticker: str) -> Optional[str]:
    """A name for a chart built from stored bars alone (the details API is what failed)."""
    from src.database.models import StockTranslation

    for db in get_session():
        row = db.query(StockTranslation.name_zh_tw, StockTranslation.name_en).filter(
            StockTranslation.ticker == ticker).first()
        return (row[0] or row[1]) if row else None
    return None


_NEW_YORK = ZoneInfo("America/New_York")


def fetch_us_bars(client: Any, ticker: str, from_date: str, to_date: str, limit: int) -> List[Dict[str, Any]]:
    """Daily bars from Massive as plain dicts, dated in New York (Massive stamps a daily
    bar at the session's local midnight)."""
    return [
        {"date": datetime.fromtimestamp(a.timestamp / 1000, tz=_NEW_YORK).strftime("%Y-%m-%d"),
         "open": a.open, "high": a.high, "low": a.low, "close": a.close,
         "volume": int(getattr(a, "volume", 0) or 0)}
        for a in client.list_aggs(ticker=ticker, multiplier=1, timespan="day", from_=from_date, to=to_date, limit=limit)
    ]


# ── one-off repair ─────────────────────────────────────────────────────────────
#
# Chart loads only re-fetch the last US_TAIL_DAYS, so defects older than that stay:
# on 2026-09-17 NVDA/AMD/MSFT had no bar for 2026-07-24 and 2026-09-01 was stored
# mid-session. The repair re-fetches a year for every US ticker in the store, spaced like
# the other US warmers (Massive is ~5 req/min), and upserts the closed sessions. One run
# fixes every environment: dev, staging and prod share this table.

REPAIR_GAP_SECONDS = 14.0
REPAIR_BACKOFF_SECONDS = 60.0
REPAIR: Dict[str, Any] = {"running": False}


def us_tickers_in_store() -> List[str]:
    from sqlalchemy import distinct

    from src.services.finmind_service import is_tw_ticker

    for db in get_session():
        rows = db.query(distinct(StockDailyOHLC.ticker)).filter(StockDailyOHLC.ticker.op("~")("^[A-Z]")).all()
        return sorted(t for (t,) in rows if t and not is_tw_ticker(t))
    return []


async def repair_us_bars(days: int = 400, gap_seconds: float = REPAIR_GAP_SECONDS,
                         backoff_seconds: float = REPAIR_BACKOFF_SECONDS, massive: Any = None) -> Dict[str, Any]:
    """Re-fetch ``days`` of daily bars for every stored US ticker and upsert closed sessions.
    One attempt plus one retry after a back-off per ticker (a 429 run passes in a minute);
    a ticker that fails twice is recorded and skipped. Progress lives in ``REPAIR``."""
    if REPAIR.get("running"):
        return REPAIR
    if massive is None:
        from src.services.massive_service import MassiveAPIService
        massive = MassiveAPIService()
    tickers = await asyncio.to_thread(us_tickers_in_store)
    to_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    from_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    REPAIR.clear()
    REPAIR.update(running=True, total=len(tickers), done=0, written=0, failed=[], current=None,
                  window=[from_date, to_date], started_at=datetime.now(timezone.utc).isoformat(), finished_at=None)
    try:
        for ticker in tickers:
            REPAIR["current"] = ticker
            for attempt in (1, 2):
                try:
                    # `.client` per call: each access takes a unit of the shared Massive
                    # budget and raises when it is spent (a held client would bypass it).
                    bars = await asyncio.to_thread(
                        lambda: fetch_us_bars(massive.client, ticker, from_date, to_date, days + 50))
                    REPAIR["written"] += await asyncio.to_thread(write_bars, ticker, bars, "massive")
                    break
                except Exception as e:
                    if attempt == 2:
                        REPAIR["failed"].append({"ticker": ticker, "error": str(e)[:200]})
                        logger.warning("bar repair: %s failed twice: %s", ticker, e)
                    else:
                        await asyncio.sleep(backoff_seconds)
            REPAIR["done"] += 1
            await asyncio.sleep(gap_seconds)
    finally:
        REPAIR.update(running=False, current=None, finished_at=datetime.now(timezone.utc).isoformat())
        logger.info("bar repair finished: %s", {k: v for k, v in REPAIR.items() if k != "failed"})
    return REPAIR
