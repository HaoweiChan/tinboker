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
from src.services.finmind_service import is_tw_ticker as _is_tw

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


# Profile fields (name/market-cap/P-E) drift slowly; refresh weekly. Logos are static and
# fetched from Massive only when missing (the 429 saver). yfinance has no per-key cap but
# we still space calls out to be polite to Yahoo and avoid an IP throttle.
_PROFILE_TTL_DAYS = 7
_YF_GAP_SECONDS = 1.5


def _warm_us_slow_data(ticker: str, yf_provider, mas_provider) -> bool:
    """Warm stock_profiles (+ logo once) and stock_daily_ohlc for one US ticker.

    Sync (runs in a thread). Returns True if anything was written. Profile + P/E + OHLC
    come from yfinance (rate-cap-free, best-effort); the company logo is pulled from Massive
    only when we don't already have one stored — collapsing the per-request logo 429 storm
    to roughly one Massive call per ticker, ever.
    """
    from src.database.models import StockDailyOHLC, StockProfile

    wrote = False
    profile = yf_provider.get_profile(ticker)  # best-effort; may be None on scraper hiccup

    for session in get_session():
        try:
            existing = (
                session.query(StockProfile).filter(StockProfile.ticker == ticker).first()
            )
            # Logo: only hit Massive when we lack one — this is the rate-limit win.
            logo = None
            if existing is None or not existing.logo_image:
                mp = mas_provider.get_profile(ticker)
                if mp:
                    logo = mp

            if profile or logo:
                row = existing or StockProfile(ticker=ticker)
                if profile:
                    row.name = profile.name or row.name
                    row.market_cap = profile.market_cap if profile.market_cap is not None else row.market_cap
                    row.sector = profile.sector or row.sector
                    row.industry = profile.industry or row.industry
                    row.pe = profile.pe if profile.pe is not None else row.pe
                    row.dividend_yield = (
                        profile.dividend_yield if profile.dividend_yield is not None else row.dividend_yield
                    )
                    row.currency = profile.currency or row.currency
                    row.description = profile.description or row.description
                    row.source = profile.source or row.source
                if logo:
                    row.logo_url = logo.logo_url or row.logo_url
                    row.icon_url = logo.icon_url or row.icon_url
                    row.logo_image = logo.logo_image or row.logo_image
                    row.icon_image = logo.icon_image or row.icon_image
                    row.name = row.name or logo.name
                if existing is None:
                    session.add(row)
                session.commit()
                wrote = True
        except Exception as e:
            session.rollback()
            logger.debug(f"slow-data: profile upsert failed for {ticker}: {e}")
        break

    # OHLC bars (full chart data) — yfinance end is exclusive, so pad +1 day.
    end = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")
    start = (datetime.utcnow() - timedelta(days=_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    bars = yf_provider.get_daily_ohlc(ticker, start, end)
    if bars:
        for session in get_session():
            try:
                inserted = 0
                for b in bars:
                    exists = (
                        session.query(StockDailyOHLC.id)
                        .filter(StockDailyOHLC.ticker == ticker, StockDailyOHLC.date == b.date)
                        .first()
                    )
                    if not exists:
                        session.add(
                            StockDailyOHLC(
                                ticker=ticker, date=b.date, open=b.open, high=b.high,
                                low=b.low, close=b.close, volume=b.volume,
                            )
                        )
                        inserted += 1
                if inserted:
                    session.commit()
                    wrote = True
            except Exception as e:
                session.rollback()
                logger.debug(f"slow-data: ohlc upsert failed for {ticker}: {e}")
            break
    return wrote


def _profile_is_fresh(db, ticker: str, cutoff: datetime) -> bool:
    """True if we have a profile for ``ticker`` updated on/after ``cutoff``."""
    from src.database.models import StockProfile

    row = (
        db.query(StockProfile.updated_at, StockProfile.logo_image)
        .filter(StockProfile.ticker == ticker)
        .first()
    )
    if not row:
        return False
    updated_at, logo_image = row
    # Re-warm if the logo is still missing, even within the TTL, so it gets backfilled once.
    return bool(logo_image) and updated_at is not None and updated_at >= cutoff


async def refresh_us_slow_data(max_tracked: int = MAX_TRACKED) -> int:
    """Warm profiles + OHLC for the tracked US tickers. Returns tickers warmed."""
    tickers = [t for t in await get_tracked_tickers(max_tracked) if not _is_tw(t)]
    if not tickers:
        return 0

    from src.services.providers import MassiveProvider, YFinanceProvider
    yf_provider = YFinanceProvider()
    mas_provider = MassiveProvider()

    cutoff = datetime.utcnow() - timedelta(days=_PROFILE_TTL_DAYS)
    loop = asyncio.get_event_loop()
    warmed = 0
    for ticker in tickers:
        try:
            skip = False
            for session in get_session():
                skip = _profile_is_fresh(session, ticker, cutoff)
                break
            if skip:
                continue
            wrote = await loop.run_in_executor(
                None, _warm_us_slow_data, ticker, yf_provider, mas_provider
            )
            if wrote:
                warmed += 1
        except Exception as e:
            logger.debug(f"slow-data: skipping {ticker}: {e}")
        await asyncio.sleep(_YF_GAP_SECONDS)

    if warmed:
        logger.info(f"slow-data: warmed profile/OHLC for {warmed} US ticker(s).")
    return warmed


async def refresh_daily_closes(max_tracked: int = MAX_TRACKED) -> int:
    """Refresh missing recent closes for the tracked tickers. Returns rows inserted."""
    tickers = await get_tracked_tickers(max_tracked)
    if not tickers:
        return 0
    # Skip a ticker only once we already hold the most recent *trading day's* close, so the
    # latest close advances every market day. The old `today - 4 days` treated any close
    # within 4 days as "warm", which froze the table for days (06-19/06-22 never fetched).
    # Weekends roll back to Friday so we don't re-fetch the whole basket while markets shut.
    # ponytail: weekday-only; a real market holiday causes a harmless re-fetch until caught up.
    today = datetime.utcnow()
    since = (today - timedelta(days={5: 1, 6: 2}.get(today.weekday(), 0))).strftime("%Y-%m-%d")
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
        try:
            await refresh_us_slow_data()
        except Exception as e:
            logger.warning(f"slow-data refresh cycle failed: {e}")
        await asyncio.sleep(interval_hours * 3600)


def read_stored_profile_sync(ticker: str) -> Optional[dict]:
    """Sync read of a warmed US profile (incl. base64 logo/icon) from Postgres, or None.

    Lets request paths serve company logos/profile from the DB instead of re-fetching from
    Massive on a 1-hour TTL per ticker — the change that collapses the profile 429 storm.
    Safe to call from sync code (e.g. the CompanyDetail builder); never raises.
    """
    from src.database.models import StockProfile

    ticker = ticker.strip().upper()
    try:
        for session in get_session():
            row = (
                session.query(StockProfile)
                .filter(StockProfile.ticker == ticker)
                .first()
            )
            if row is None:
                return None
            return {
                "ticker": row.ticker,
                "name": row.name,
                "market_cap": row.market_cap,
                "sector": row.sector,
                "industry": row.industry,
                "pe": row.pe,
                "dividend_yield": row.dividend_yield,
                "currency": row.currency,
                "description": row.description,
                "logo_url": row.logo_url,
                "icon_url": row.icon_url,
                "logo_image": row.logo_image,
                "icon_image": row.icon_image,
            }
    except Exception as e:
        logger.debug(f"slow-data: profile read failed for {ticker}: {e}")
    return None


async def get_stored_profile(ticker: str) -> Optional[dict]:
    """Async wrapper around :func:`read_stored_profile_sync` (runs in a thread)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, read_stored_profile_sync, ticker)


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
