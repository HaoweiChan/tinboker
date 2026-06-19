"""
Daily-close refresher.

FinMind (TW, per-IP ~300/hr) and Massive/Polygon (US, ~5/min) free tiers are far too
small to fetch live prices per request for a homepage full of tickers. Instead a slow
background task keeps the permanent ``stock_daily_closes`` table warm for the tracked
(trending) tickers, fetching only what's missing and throttling well under the limits.
The serving paths then read end-of-day change% straight from Postgres (no per-request
API calls). EOD prices are fine for a podcast-insight site — not intraday trading.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from src.database.models import StockDailyClose
from src.database.postgres import get_session
from src.services import finmind_budget

logger = logging.getLogger(__name__)

# How many of the most-relevant tickers to keep warm. Covers the sector/theme basket
# members (so the /topics board's price diffs are populated) plus the trending set.
MAX_TRACKED = 400
# Throttle between external calls. Massive/Polygon free is ~5 req/min, so US tickers get
# a wide gap; FinMind is gated by its hourly budget but we still space calls out.
_US_GAP_SECONDS = 14.0
_TW_GAP_SECONDS = 2.0
# Lookback window to fetch per ticker (enough for the last 2 trading days incl. weekends).
_LOOKBACK_DAYS = 7


def _is_tw(ticker: str) -> bool:
    return ticker.split(".")[0].isdigit()


async def get_tracked_tickers(limit: int = MAX_TRACKED) -> List[str]:
    """Tickers worth keeping warm: the sector/theme basket members PLUS the trending
    set (episode mentions). Sector members come first so the /topics board's price
    diffs are always populated; trending fills any remaining headroom."""
    seen: set = set()
    out: List[str] = []

    def _add(raw) -> None:
        t = raw.strip().upper() if isinstance(raw, str) else ""
        if t and t not in seen:
            seen.add(t)
            out.append(t)

    # 1. Sector/theme basket members — the board's constituents (priority).
    try:
        from src.services.podcast import PodcastService
        for t in await PodcastService().sector_member_tickers():
            _add(t)
    except Exception as e:
        logger.warning(f"close-refresh: could not load sector tickers: {e}")

    # 2. Trending (episode-mention) set — fills the rest.
    try:
        from src.services.insight_service import InsightService
        for r in (await InsightService().get_trending(days=30, limit=limit)) or []:
            _add(r.get("ticker") if isinstance(r, dict) else None)
    except Exception as e:
        logger.warning(f"close-refresh: could not load trending tickers: {e}")

    return out[:limit]


def _has_recent_close(db, ticker: str, since_date: str) -> bool:
    """True if we already stored a close for this ticker on/after since_date."""
    return (
        db.query(StockDailyClose.id)
        .filter(StockDailyClose.ticker == ticker, StockDailyClose.date >= since_date)
        .first()
        is not None
    )


def _fetch_and_store_closes(ticker: str, fin_svc, mas_svc) -> int:
    """Fetch recent daily closes for one ticker and upsert into stock_daily_closes.

    Sync (runs in a thread). Returns the number of rows inserted. Respects the FinMind
    global budget for TW tickers; US tickers go through Massive (caller throttles). The
    service clients are passed in and reused across tickers (avoids re-login per call).
    """
    end = datetime.utcnow().strftime("%Y-%m-%d")
    start = (datetime.utcnow() - timedelta(days=_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    try:
        if _is_tw(ticker):
            if not finmind_budget.consume(finmind_budget_bucket()):
                return 0  # FinMind budget spent — skip; next cycle retries
            rows = fin_svc.list_daily_ticker_summary_range(ticker.split(".")[0], start, end)
        else:
            rows = mas_svc.list_daily_ticker_summary_range(ticker, start, end)
    except Exception as e:
        logger.debug(f"close-refresh: fetch failed for {ticker}: {e}")
        return 0

    if not rows:
        return 0

    inserted = 0
    for session in get_session():
        try:
            for row in rows:
                date = row.get("date")
                close = row.get("close")
                if not date or close is None:
                    continue
                exists = (
                    session.query(StockDailyClose.id)
                    .filter(StockDailyClose.ticker == ticker, StockDailyClose.date == date)
                    .first()
                )
                if not exists:
                    session.add(StockDailyClose(ticker=ticker, date=date, close=close))
                    inserted += 1
            if inserted:
                session.commit()
        except Exception as e:
            session.rollback()
            logger.debug(f"close-refresh: upsert failed for {ticker}: {e}")
        break
    return inserted


def finmind_budget_bucket() -> str:
    # Mirror the single global bucket used by the FinMind client.
    from src.services.finmind_service import _FINMIND_BUDGET
    return _FINMIND_BUDGET


async def refresh_daily_closes(max_tracked: int = MAX_TRACKED) -> int:
    """Refresh missing recent closes for the tracked tickers. Returns rows inserted."""
    tickers = await get_tracked_tickers(max_tracked)
    if not tickers:
        return 0
    # "Recent" = on/after the last expected trading day (yesterday, to allow for the
    # current day not having closed yet). Skip tickers already warm.
    since = (datetime.utcnow() - timedelta(days=4)).strftime("%Y-%m-%d")
    loop = asyncio.get_event_loop()

    # Build the API clients once and reuse them across all tickers.
    from src.services.finmind_service import FinMindAPIService
    from src.services.massive_service import MassiveAPIService
    fin_svc = FinMindAPIService()
    mas_svc = MassiveAPIService()

    total = 0
    fetched = 0
    for ticker in tickers:
        try:
            # Cheap DB check first — skip tickers we already have a recent close for.
            skip = False
            for session in get_session():
                skip = _has_recent_close(session, ticker, since)
                break
            if skip:
                continue

            inserted = await loop.run_in_executor(None, _fetch_and_store_closes, ticker, fin_svc, mas_svc)
            total += inserted
            fetched += 1
        except Exception as e:
            logger.debug(f"close-refresh: skipping {ticker}: {e}")
        # Throttle to stay under the free-tier rate limits (even on skip-check failure).
        await asyncio.sleep(_US_GAP_SECONDS if not _is_tw(ticker) else _TW_GAP_SECONDS)

    if fetched:
        logger.info(f"close-refresh: fetched {fetched} ticker(s), inserted {total} close row(s).")
    return total


async def run_periodic_refresh(interval_hours: float = 6.0) -> None:
    """Background loop: refresh on startup, then every interval_hours. Never raises."""
    while True:
        try:
            await refresh_daily_closes()
        except Exception as e:
            logger.warning(f"close-refresh cycle failed: {e}")
        await asyncio.sleep(interval_hours * 3600)


async def get_eod_change_pct(ticker: str) -> Optional[float]:
    """End-of-day change% from the two most recent stored closes, or None if <2 rows."""
    ticker = ticker.strip().upper()
    loop = asyncio.get_event_loop()

    def _read() -> Optional[float]:
        try:
            for session in get_session():
                rows = (
                    session.query(StockDailyClose.close)
                    .filter(StockDailyClose.ticker == ticker)
                    .order_by(StockDailyClose.date.desc())
                    .limit(2)
                    .all()
                )
                if len(rows) < 2:
                    return None
                latest, prev = rows[0][0], rows[1][0]
                if not prev:
                    return None
                return (latest - prev) / prev * 100.0
        except Exception as e:
            # Never let a DB hiccup 500 the request path — callers fall back to live data.
            logger.debug(f"close-refresh: eod read failed for {ticker}: {e}")
        return None

    return await loop.run_in_executor(None, _read)
