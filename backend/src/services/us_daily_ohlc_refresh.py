"""Whole-market US daily OHLCV warmer (issue #449, US half).

Sibling of ``tw_daily_ohlc_refresh``. Instead of the TWSE/TPEx OpenAPI feeds it pulls the
entire US market for one trading day from Polygon's **grouped daily aggregates**
(``get_grouped_daily_aggs`` — ONE call returns every US stock's OHLCV for a date, vs the
per-ticker ``list_aggs`` fan-out the ~5-req/min Massive budget can't sustain across a
~1,500-name universe) and lands it in the same ``stock_daily_ohlc`` table with
``source='polygon'``. The US screener + request path then read US bars from Postgres.

Tier note: the grouped endpoint must be enabled on the Massive/Polygon plan. If it isn't,
the fetch returns [] and this warms nothing (logged loudly). US OHLC is a hard dependency
for the US screener, so we surface that rather than silently degrading to an infeasible
per-ticker loop.
ponytail: if the plan lacks grouped, add a bounded per-ticker warmer over an explicit index
universe here — only a few hundred names are feasible given the ~5/min/key rate cap.

Rows are filtered through ``_looks_us`` (shared with massive_service), which keeps ordinary
stocks AND ETFs (SPY/QQQ/SMH… — the US screener needs sector ETFs for regime/rotation) and
drops warrants/units/odd symbols the rest of the app never looks up.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date as _date, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional

from src.database.models import StockDailyOHLC
from src.database.postgres import get_session
from src.services.massive_service import MassiveAPIService, _looks_us
# Reuse the TW warmer's upsert — it writes StockDailyOHLC keyed on (ticker, date) and is
# source-agnostic (our rows carry source='polygon'), so there's one upsert path, not two.
from src.services.tw_daily_ohlc_refresh import _upsert_rows

logger = logging.getLogger(__name__)

_BACKFILL_DAYS = 90
_BACKFILL_GAP_SECONDS = 1.0
# A real US session yields thousands of grouped rows; below this a date is "not yet filled"
# (0 for weekends/holidays — harmlessly re-probed). Makes backfill idempotent + resumable.
_MIN_ROWS_PER_DAY = 100
# Walk back at most this many calendar days from today to find the latest completed session
# (grouped returns [] for weekends/holidays/before-close).
_LOOKBACK_PROBE = 5


def _f(raw: Any) -> Optional[float]:
    """Coerce a Polygon agg numeric field to float, or None."""
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _normalize_grouped(agg: Any, iso: str) -> Optional[Dict[str, Any]]:
    """Map one Polygon grouped-daily agg → a stock_daily_ohlc row dict, or None to drop.

    ``agg`` is a Polygon ``GroupedDailyAgg`` object (attrs: ticker/open/high/low/close/
    volume/vwap/…). ``trading_value`` (成交金額, $) is dollar volume — Polygon gives vwap +
    volume, so ``vwap × volume`` is the accurate figure; falls back to ``close × volume``
    when vwap is absent. Drops non-US symbols (warrants/units/odd tickers) via ``_looks_us``.
    """
    ticker = str(getattr(agg, "ticker", "") or "").strip().upper()
    close = _f(getattr(agg, "close", None))
    if not ticker or close is None or not _looks_us(ticker):
        return None
    volume = _f(getattr(agg, "volume", None))
    vwap = _f(getattr(agg, "vwap", None))
    if volume is None:
        trading_value = None
    elif vwap is not None:
        trading_value = vwap * volume
    else:
        trading_value = close * volume
    return {
        "ticker": ticker, "date": iso,
        "open": _f(getattr(agg, "open", None)), "high": _f(getattr(agg, "high", None)),
        "low": _f(getattr(agg, "low", None)), "close": close,
        "volume": volume, "trading_value": trading_value,
        "source": "polygon",
    }


def _fetch_grouped(iso: str) -> List[Dict[str, Any]]:
    """Fetch + normalize the whole US market for one date via Polygon grouped-daily.

    Sync (runs in a thread). Returns [] on any failure or an empty/non-trading day (logged).
    """
    try:
        svc = MassiveAPIService()
        client = svc.client
        if client is None:
            logger.warning("US OHLC: no Massive client configured — cannot warm US bars.")
            return []
        aggs = client.get_grouped_daily_aggs(iso, adjusted=True)
    except Exception as e:
        logger.warning("US grouped-daily fetch failed for %s: %s", iso, e)
        return []
    aggs = list(aggs or [])
    rows = [r for a in aggs if (r := _normalize_grouped(a, iso))]
    logger.info("US OHLC: grouped %s → %d usable rows (of %d).", iso, len(rows), len(aggs))
    return rows


def _us_rows_for_date(iso: str) -> int:
    """Count polygon-sourced rows already stored for a date (drives idempotent backfill)."""
    for session in get_session():
        try:
            return (
                session.query(StockDailyOHLC)
                .filter(StockDailyOHLC.date == iso, StockDailyOHLC.source == "polygon")
                .count()
            )
        except Exception:
            return 0
    return 0


async def refresh_us_daily_ohlc() -> int:
    """Fetch the latest completed US session's whole-market bars and upsert. Never raises.

    Grouped returns [] for weekends/holidays/before-close, so probe today then walk back up
    to ``_LOOKBACK_PROBE`` days and take the first date with rows.
    """
    loop = asyncio.get_event_loop()
    for i in range(_LOOKBACK_PROBE):
        iso = (_date.today() - timedelta(days=i)).isoformat()
        rows = await loop.run_in_executor(None, _fetch_grouped, iso)
        if rows:
            written = await loop.run_in_executor(None, _upsert_rows, rows)
            logger.info("US OHLC refresh: %s wrote %d rows.", iso, written)
            return written
    logger.warning(
        "US OHLC refresh: no session with data in the last %d days — grouped-daily empty. "
        "Check that the Massive/Polygon plan enables grouped aggregates.",
        _LOOKBACK_PROBE,
    )
    return 0


async def backfill_us_daily_ohlc(days: int = _BACKFILL_DAYS, gap_seconds: float = _BACKFILL_GAP_SECONDS) -> int:
    """Seed `days` of US history into stock_daily_ohlc from grouped-daily (one call/day).

    Idempotent + resumable: a weekday already holding >= _MIN_ROWS_PER_DAY polygon rows is
    skipped; recent-first so an interrupted run leaves the most useful days filled. Weekends
    are skipped; holidays return empty and are harmlessly re-probed next run. Never raises.
    """
    loop = asyncio.get_event_loop()
    filled = total = 0
    scanned = 0
    for i in range(1, days + 1):
        d = _date.today() - timedelta(days=i)
        if d.weekday() >= 5:  # Sat/Sun
            continue
        scanned += 1
        iso = d.isoformat()
        if await loop.run_in_executor(None, _us_rows_for_date, iso) >= _MIN_ROWS_PER_DAY:
            continue
        rows = await loop.run_in_executor(None, _fetch_grouped, iso)
        await asyncio.sleep(gap_seconds)
        if rows:
            total += await loop.run_in_executor(None, _upsert_rows, rows)
            filled += 1
    logger.info(
        "US OHLC backfill: filled %d day(s), wrote %d rows (scanned %d weekdays over %dd).",
        filled, total, scanned, days,
    )
    return total


async def run_periodic_us_ohlc_refresh(
    interval_hours: float = 6.0,
    backfill_days: int = _BACKFILL_DAYS,
    after_refresh: Optional[Callable[[], Awaitable[Any]]] = None,
) -> None:
    """Background loop: refresh on startup, then every interval_hours. Never raises.

    Mirrors ``run_periodic_tw_ohlc_refresh``. Polygon finalizes the grouped day after the US
    close; a 6h cadence lands it within one cycle and cheaply re-confirms it (upsert
    overwrites). The first cycle also seeds `backfill_days` of history (idempotent — a no-op
    once filled). ``after_refresh``, if given, is awaited once per cycle right after the
    refresh (+ first-run backfill) — e.g. to chain the US screener so it runs against data
    from *this* cycle. A hook failure is caught + logged, never breaking the loop.
    """
    first = True
    while True:
        try:
            await refresh_us_daily_ohlc()
        except Exception as e:
            logger.warning("US OHLC refresh cycle failed: %s", e)
        if first:
            first = False
            try:
                await backfill_us_daily_ohlc(days=backfill_days)
            except Exception as e:
                logger.warning("US OHLC backfill failed: %s", e)
        if after_refresh is not None:
            try:
                await after_refresh()
            except Exception as e:
                logger.warning("US post-refresh hook failed: %s", e)
        await asyncio.sleep(interval_hours * 3600)


if __name__ == "__main__":
    # Manual run against live Polygon (writes to the configured DB): `refresh` fetches the
    # latest session, `backfill [days]` seeds history. Normalization is covered by unit tests.
    import sys

    logging.basicConfig(level=logging.INFO)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "refresh"
    if cmd == "backfill":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else _BACKFILL_DAYS
        print("US OHLC backfilled", asyncio.run(backfill_us_daily_ohlc(days=n)), "rows")
    else:
        print("US OHLC wrote", asyncio.run(refresh_us_daily_ohlc()), "rows")
    sys.exit(0)
