"""Whole-market TW daily OHLCV fetcher (M1 of the price-data architecture).

The old design fanned out hundreds of per-ticker FinMind calls per /topics recompute and
self-exhausted the hourly budget (see docs/fix-plans/2026-07-05-topics-bubbles-zero-
trading-value.md). Instead, a scheduled background task pulls the *entire* listed + OTC
market in **two free, key-less calls/day** from the official exchange OpenAPIs and lands
it in Postgres (``stock_daily_ohlc``). The request path then reads daily bars — trading
value, close — from the DB and never touches an external market API.

Sources (verified 2026-07-05):
- TWSE  https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL  (listed, ~1,100 stocks)
- TPEx  https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes  (OTC)
Both return a single trading day, ROC-format dates ("1150703" = 2026-07-03), string
numeric fields, and TPEx requires a browser User-Agent (plain curl 403s).

Rows are filtered through ``is_tw_ticker`` so we store the ~2k ordinary stocks/ETFs the
rest of the app looks up, not the ~9k OTC warrants/ETNs nobody queries.
ponytail: is_tw_ticker drops 6-digit codes, so 6-digit ETFs (e.g. 006208) aren't stored;
widen the filter here if per-chart 6-digit ETF history is ever needed.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import requests

from src.database.models import StockDailyOHLC
from src.database.postgres import get_session
from src.services.finmind_service import is_tw_ticker

logger = logging.getLogger(__name__)

_TWSE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
_TPEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
# TPEx OpenAPI 403s a plain requests UA; any browser-looking UA works.
_BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_ROC_YEAR_OFFSET = 1911  # ROC year 115 → 2026

# Historical whole-market feeds for backfill — the OpenAPI feeds above are today-only, but
# these legacy endpoints return the full market for ANY past trading day, so 90d of history
# is ~60 calls/exchange (one per trading day), not thousands of per-stock/month calls. Both
# return {tables:[{fields:[...], data:[[...]]}]}; find the per-stock table by its code field.
_TWSE_HIST_URL = "https://www.twse.com.tw/exchangeReport/MI_INDEX"       # date=YYYYMMDD, type=ALL
_TPEX_HIST_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes"  # date=YYYY/MM/DD
_BACKFILL_DAYS = 90
# A real TW trading day yields ~2,100 filtered rows; below this a date is "not yet backfilled"
# (0 for weekends/holidays — harmlessly re-probed). Makes backfill idempotent and resumable.
_MIN_ROWS_PER_DAY = 500
_BACKFILL_GAP_SECONDS = 1.0  # be polite to the gov endpoints (unpublished rate limits)


def _roc_to_iso(roc: str) -> Optional[str]:
    """'1150703' (ROC yyy-mm-dd) → '2026-07-03'. Returns None if unparseable."""
    roc = (roc or "").strip()
    if len(roc) < 7 or not roc.isdigit():
        return None
    year = int(roc[:-4]) + _ROC_YEAR_OFFSET
    month, day = roc[-4:-2], roc[-2:]
    return f"{year:04d}-{month}-{day}"


def _num(raw: Any) -> Optional[float]:
    """Parse an exchange numeric string ('1,234.5', '--', '') → float or None."""
    if raw is None:
        return None
    s = str(raw).replace(",", "").strip()
    if not s or s in ("--", "---", "N/A"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _normalize_twse(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ticker = str(rec.get("Code", "")).strip()
    date = _roc_to_iso(str(rec.get("Date", "")))
    close = _num(rec.get("ClosingPrice"))
    if not ticker or not date or close is None or not is_tw_ticker(ticker):
        return None
    return {
        "ticker": ticker, "date": date,
        "open": _num(rec.get("OpeningPrice")), "high": _num(rec.get("HighestPrice")),
        "low": _num(rec.get("LowestPrice")), "close": close,
        "volume": _num(rec.get("TradeVolume")), "trading_value": _num(rec.get("TradeValue")),
        "source": "twse",
    }


def _normalize_tpex(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ticker = str(rec.get("SecuritiesCompanyCode", "")).strip()
    date = _roc_to_iso(str(rec.get("Date", "")))
    close = _num(rec.get("Close"))
    if not ticker or not date or close is None or not is_tw_ticker(ticker):
        return None
    return {
        "ticker": ticker, "date": date,
        "open": _num(rec.get("Open")), "high": _num(rec.get("High")),
        "low": _num(rec.get("Low")), "close": close,
        "volume": _num(rec.get("TradingShares")), "trading_value": _num(rec.get("TransactionAmount")),
        "source": "tpex",
    }


def _fetch(url: str, normalize, headers: Optional[dict] = None) -> List[Dict[str, Any]]:
    """GET one whole-market feed and normalize; returns [] on any failure (logged)."""
    try:
        resp = requests.get(url, headers=headers, timeout=60)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        logger.warning("TW OHLC fetch failed for %s: %s", url, e)
        return []
    rows = [r for rec in payload if (r := normalize(rec))]
    logger.info("TW OHLC: %s → %d usable rows (of %d)", url.rsplit("/", 1)[-1], len(rows), len(payload))
    return rows


def _upsert_rows(rows: List[Dict[str, Any]]) -> int:
    """Upsert normalized rows into stock_daily_ohlc (update-or-insert on ticker+date).

    Sync (runs in a thread). Returns rows written (inserted + updated). Same-day re-runs
    overwrite so a post-close run finalizes an earlier intraday row.
    """
    written = 0
    for session in get_session():
        try:
            for row in rows:
                existing = (
                    session.query(StockDailyOHLC)
                    .filter(StockDailyOHLC.ticker == row["ticker"], StockDailyOHLC.date == row["date"])
                    .first()
                )
                if existing:
                    for k in ("open", "high", "low", "close", "volume", "trading_value", "source"):
                        setattr(existing, k, row[k])
                else:
                    session.add(StockDailyOHLC(**row))
                written += 1
            session.commit()
        except Exception as e:
            session.rollback()
            logger.warning("TW OHLC upsert failed: %s", e)
            written = 0
        break
    return written


async def refresh_tw_daily_ohlc() -> int:
    """Fetch TWSE + TPEx whole-market daily bars and upsert into Postgres. Never raises."""
    loop = asyncio.get_event_loop()
    twse = await loop.run_in_executor(None, _fetch, _TWSE_URL, _normalize_twse, None)
    tpex = await loop.run_in_executor(None, _fetch, _TPEX_URL, _normalize_tpex, {"User-Agent": _BROWSER_UA})
    rows = twse + tpex
    if not rows:
        logger.warning("TW OHLC refresh: both feeds empty — skipping upsert.")
        return 0
    written = await loop.run_in_executor(None, _upsert_rows, rows)
    logger.info("TW OHLC refresh: wrote %d rows (twse=%d, tpex=%d).", written, len(twse), len(tpex))
    return written


# ── Backfill (historical whole-market feeds) ──────────────────────────────────────

def _normalize_twse_hist(rec: Dict[str, Any], iso: str) -> Optional[Dict[str, Any]]:
    ticker = str(rec.get("證券代號", "")).strip()
    close = _num(rec.get("收盤價"))
    if not ticker or close is None or not is_tw_ticker(ticker):
        return None
    return {
        "ticker": ticker, "date": iso,
        "open": _num(rec.get("開盤價")), "high": _num(rec.get("最高價")),
        "low": _num(rec.get("最低價")), "close": close,
        "volume": _num(rec.get("成交股數")), "trading_value": _num(rec.get("成交金額")),
        "source": "twse",
    }


def _normalize_tpex_hist(rec: Dict[str, Any], iso: str) -> Optional[Dict[str, Any]]:
    ticker = str(rec.get("代號", "")).strip()
    close = _num(rec.get("收盤"))
    if not ticker or close is None or not is_tw_ticker(ticker):
        return None
    return {
        "ticker": ticker, "date": iso,
        "open": _num(rec.get("開盤")), "high": _num(rec.get("最高")),
        "low": _num(rec.get("最低")), "close": close,
        "volume": _num(rec.get("成交股數")), "trading_value": _num(rec.get("成交金額(元)")),
        "source": "tpex",
    }


def _rows_from_feed(payload: Dict[str, Any], key_field: str, normalize, iso: str) -> List[Dict[str, Any]]:
    """Pick the per-stock table (identified by its code column) and normalize its rows.

    Both feeds return tables of ``fields``/``data`` (data = list-of-lists); zip into dicts
    keyed by the exchange's own column names so a column reorder can't silently mismap.
    """
    if str(payload.get("stat", "")).lower() not in ("ok",):
        return []  # holiday / no session that day
    best: List[Dict[str, Any]] = []
    for table in payload.get("tables") or []:
        fields = table.get("fields") or []
        if key_field not in fields:
            continue
        rows = [r for row in (table.get("data") or []) if (r := normalize(dict(zip(fields, row)), iso))]
        if len(rows) > len(best):
            best = rows
    return best


def _fetch_twse_history(iso: str) -> List[Dict[str, Any]]:
    try:
        payload = requests.get(
            _TWSE_HIST_URL,
            params={"response": "json", "date": iso.replace("-", ""), "type": "ALL"},
            headers={"User-Agent": _BROWSER_UA}, timeout=60,
        ).json()
    except Exception as e:
        logger.warning("TWSE history fetch failed for %s: %s", iso, e)
        return []
    return _rows_from_feed(payload, "證券代號", _normalize_twse_hist, iso)


def _fetch_tpex_history(iso: str) -> List[Dict[str, Any]]:
    try:
        payload = requests.get(
            _TPEX_HIST_URL,
            params={"date": iso.replace("-", "/"), "type": "EW", "response": "json"},
            headers={"User-Agent": _BROWSER_UA}, timeout=60,
        ).json()
    except Exception as e:
        logger.warning("TPEx history fetch failed for %s: %s", iso, e)
        return []
    return _rows_from_feed(payload, "代號", _normalize_tpex_hist, iso)


def _rows_for_date(iso: str) -> int:
    """How many rows already stored for a date (sync) — lets backfill skip filled days.

    ``return`` inside the get_session() loop exits after the single yielded session (and
    closes it via the generator's finally) — no explicit break, which in a ``finally``
    would swallow the return value and always yield 0.
    """
    for session in get_session():
        try:
            return session.query(StockDailyOHLC).filter(StockDailyOHLC.date == iso).count()
        except Exception:
            return 0
    return 0


def _weekday_dates(days: int) -> List[str]:
    """The last `days` calendar days (excluding today — the daily fetcher owns it), most
    recent first, weekends dropped. Holidays are filtered later by the empty-response skip."""
    from datetime import date, timedelta

    today = date.today()
    out: List[str] = []
    for i in range(1, days + 1):
        d = today - timedelta(days=i)
        if d.weekday() < 5:  # Mon–Fri
            out.append(d.isoformat())
    return out


async def backfill_tw_daily_ohlc(days: int = _BACKFILL_DAYS, gap_seconds: float = _BACKFILL_GAP_SECONDS) -> int:
    """Seed `days` of history into stock_daily_ohlc from the historical whole-market feeds.

    Idempotent + resumable: dates already populated (≥ _MIN_ROWS_PER_DAY) are skipped, so a
    re-run (or restart mid-backfill) only fetches the gaps. Recent-first so an interrupted
    run still leaves the most useful days filled. Never raises.
    """
    loop = asyncio.get_event_loop()
    dates = _weekday_dates(days)
    filled_days = total = 0
    for iso in dates:
        if await loop.run_in_executor(None, _rows_for_date, iso) >= _MIN_ROWS_PER_DAY:
            continue
        twse = await loop.run_in_executor(None, _fetch_twse_history, iso)
        await asyncio.sleep(gap_seconds)
        tpex = await loop.run_in_executor(None, _fetch_tpex_history, iso)
        await asyncio.sleep(gap_seconds)
        rows = twse + tpex
        if rows:
            total += await loop.run_in_executor(None, _upsert_rows, rows)
            filled_days += 1
    logger.info(
        "TW OHLC backfill: filled %d day(s), wrote %d rows (scanned %d weekdays over %dd).",
        filled_days, total, len(dates), days,
    )
    return total


async def run_periodic_tw_ohlc_refresh(interval_hours: float = 6.0, backfill_days: int = _BACKFILL_DAYS) -> None:
    """Background loop: refresh on startup, then every interval_hours. Never raises.

    Both feeds publish the finalized day after ~15:00 Taipei; a 6h cadence lands the day
    within one cycle and cheaply re-confirms it (upsert overwrites), at 2 calls/run. On the
    first cycle it also seeds `backfill_days` of history (idempotent — a no-op once filled).
    """
    first = True
    while True:
        try:
            await refresh_tw_daily_ohlc()
        except Exception as e:
            logger.warning("TW OHLC refresh cycle failed: %s", e)
        if first:
            first = False
            try:
                await backfill_tw_daily_ohlc(days=backfill_days)
            except Exception as e:
                logger.warning("TW OHLC backfill failed: %s", e)
        await asyncio.sleep(interval_hours * 3600)


if __name__ == "__main__":
    # Manual run against the live exchanges (writes to the configured DB): `refresh` fetches
    # today, `backfill [days]` seeds history. Parsing is covered by the unit tests.
    import sys
    logging.basicConfig(level=logging.INFO)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "refresh"
    if cmd == "backfill":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else _BACKFILL_DAYS
        print("backfilled", asyncio.run(backfill_tw_daily_ohlc(days=days)), "rows")
    else:
        print("wrote", asyncio.run(refresh_tw_daily_ohlc()), "rows")
    sys.exit(0)
