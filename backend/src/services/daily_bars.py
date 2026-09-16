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

import logging
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

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
