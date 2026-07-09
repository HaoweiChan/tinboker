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
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import requests

from src.database.models import StockDailyOHLC, StockInstitutionalDaily
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
# Per-source thresholds for stock_daily_ohlc completeness (mirrors screener_refresh's
# MIN_TWSE_ROWS_COMPLETE/MIN_TPEX_ROWS_COMPLETE). TWSE's STOCK_DAY_ALL feed sometimes lags
# a day, landing a single-source (TPEx-only, ~880 rows) partial day that the old
# rows>=_MIN_ROWS_PER_DAY check wrongly treated as "filled" — its missing TWSE half was
# never backfilled. A date is "filled" only once BOTH sources clear their own bar.
_MIN_TWSE_ROWS = 500
_MIN_TPEX_ROWS = 100
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


def _rows_for_date(iso: str) -> Tuple[int, int]:
    """Per-source row counts already stored for a date: ``(twse_count, tpex_count)``.

    Lets backfill skip a date only when BOTH sources are filled, not just the total — a
    TPEx-only day (~880 rows) clears the old combined 500-row bar while its TWSE half is
    still 0 and unbackfilled. ``return`` inside the get_session() loop exits after the
    single yielded session (and closes it via the generator's finally) — no explicit
    break, which in a ``finally`` would swallow the return value and always yield 0.
    """
    for session in get_session():
        try:
            twse_n = (
                session.query(StockDailyOHLC)
                .filter(StockDailyOHLC.date == iso, StockDailyOHLC.source == "twse")
                .count()
            )
            tpex_n = (
                session.query(StockDailyOHLC)
                .filter(StockDailyOHLC.date == iso, StockDailyOHLC.source == "tpex")
                .count()
            )
            return twse_n, tpex_n
        except Exception:
            return 0, 0
    return 0, 0


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

    Idempotent + resumable: a date is skipped only when BOTH sources are already populated
    (twse >= _MIN_TWSE_ROWS AND tpex >= _MIN_TPEX_ROWS) — a single-source partial day (e.g.
    TPEx-only) is re-fetched so its missing half gets filled via upsert (idempotent for the
    source already present). Recent-first so an interrupted run still leaves the most useful
    days filled. Pre-TPEx-era dates genuinely have tpex=0 and will never satisfy the
    both-sources rule, so they're re-probed every run — one cheap historical fetch that
    returns empty, harmless and self-limiting to the `days` window. Never raises.
    """
    loop = asyncio.get_event_loop()
    dates = _weekday_dates(days)
    filled_days = total = 0
    for iso in dates:
        twse_n, tpex_n = await loop.run_in_executor(None, _rows_for_date, iso)
        if twse_n >= _MIN_TWSE_ROWS and tpex_n >= _MIN_TPEX_ROWS:
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


# ── 三大法人 institutional net-buy (keyless: TWSE T86 + TPEx OpenAPI) ───────────────

_TWSE_T86_URL = "https://www.twse.com.tw/fund/T86"                      # date=YYYYMMDD, selectType=ALL
_TPEX_INSTI_URL = "https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading"  # today-only
_INSTI_BACKFILL_DAYS = 30  # covers the 20-day money-flow window with margin


def _normalize_twse_t86(rec: Dict[str, Any], iso: str) -> Optional[Dict[str, Any]]:
    ticker = str(rec.get("證券代號", "")).strip()
    total = _num(rec.get("三大法人買賣超股數"))
    if not ticker or total is None or not is_tw_ticker(ticker):
        return None
    foreign = (_num(rec.get("外陸資買賣超股數(不含外資自營商)")) or 0.0) + (
        _num(rec.get("外資自營商買賣超股數")) or 0.0
    )
    return {
        "ticker": ticker, "date": iso,
        "foreign_net_shares": foreign,
        "trust_net_shares": _num(rec.get("投信買賣超股數")) or 0.0,
        "total_net_shares": total, "source": "twse",
    }


# TPEx OpenAPI 3insti keys (exact, verified 2026-07-09 — the feed's key spacing is
# inconsistent across columns, e.g. a leading space on the "-Total Sell" variant and
# a stray space before "-TotalSell" on the Dealers row; these three are clean/exact).
_TPEX_FX_EXCL = "Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Difference"
_TPEX_FX_DEALER = "ForeignDealers-Difference"
_TPEX_TRUST = "SecuritiesInvestmentTrustCompanies-Difference"


def _normalize_tpex_insti(rec: Dict[str, Any], iso: str) -> Optional[Dict[str, Any]]:
    ticker = str(rec.get("SecuritiesCompanyCode", "")).strip()
    total = _num(rec.get("TotalDifference"))
    if not ticker or total is None or not is_tw_ticker(ticker):
        return None
    foreign = (_num(rec.get(_TPEX_FX_EXCL)) or 0.0) + (_num(rec.get(_TPEX_FX_DEALER)) or 0.0)
    return {
        "ticker": ticker, "date": iso,
        "foreign_net_shares": foreign,
        "trust_net_shares": _num(rec.get(_TPEX_TRUST)) or 0.0,
        "total_net_shares": total, "source": "tpex",
    }


def _fetch_twse_t86(iso: str) -> List[Dict[str, Any]]:
    """TWSE T86 (all listed 三大法人) for one day — fields/data table, historical-capable."""
    try:
        payload = requests.get(
            _TWSE_T86_URL,
            params={"response": "json", "date": iso.replace("-", ""), "selectType": "ALL"},
            headers={"User-Agent": _BROWSER_UA}, timeout=60,
        ).json()
    except Exception as e:
        logger.warning("TWSE T86 fetch failed for %s: %s", iso, e)
        return []
    if str(payload.get("stat", "")).lower() not in ("ok",):
        return []  # holiday / no session
    fields = payload.get("fields") or []
    return [r for row in (payload.get("data") or []) if (r := _normalize_twse_t86(dict(zip(fields, row)), iso))]


def _fetch_tpex_insti(iso: str) -> List[Dict[str, Any]]:
    """TPEx OpenAPI 3insti (all OTC 三大法人) — today's session only; row Date confirms it."""
    try:
        payload = requests.get(_TPEX_INSTI_URL, headers={"User-Agent": _BROWSER_UA}, timeout=60).json()
    except Exception as e:
        logger.warning("TPEx 3insti fetch failed: %s", e)
        return []
    out: List[Dict[str, Any]] = []
    for rec in payload if isinstance(payload, list) else []:
        # The feed is today-only; only accept rows whose ROC date matches the target day.
        if _roc_to_iso(str(rec.get("Date", ""))) != iso:
            continue
        r = _normalize_tpex_insti(rec, iso)
        if r:
            out.append(r)
    return out


def _upsert_insti_rows(rows: List[Dict[str, Any]]) -> int:
    """Upsert institutional net-share rows into stock_institutional_daily (update-or-insert)."""
    written = 0
    for session in get_session():
        try:
            for row in rows:
                existing = (
                    session.query(StockInstitutionalDaily)
                    .filter(
                        StockInstitutionalDaily.ticker == row["ticker"],
                        StockInstitutionalDaily.date == row["date"],
                    )
                    .first()
                )
                if existing:
                    existing.foreign_net_shares = row["foreign_net_shares"]
                    existing.trust_net_shares = row.get("trust_net_shares")
                    existing.total_net_shares = row["total_net_shares"]
                    existing.source = row["source"]
                else:
                    session.add(StockInstitutionalDaily(**row))
                written += 1
            session.commit()
        except Exception as e:
            session.rollback()
            logger.warning("TW institutional upsert failed: %s", e)
            written = 0
        break
    return written


def _insti_rows_for_date(iso: str) -> int:
    for session in get_session():
        try:
            return session.query(StockInstitutionalDaily).filter(StockInstitutionalDaily.date == iso).count()
        except Exception:
            return 0
    return 0


async def refresh_tw_institutional() -> int:
    """Fetch today's TWSE + TPEx 三大法人 net shares and upsert into Postgres. Never raises."""
    loop = asyncio.get_event_loop()
    iso_today = _fetch_latest_market_date()  # the newest date the feeds carry
    if not iso_today:
        return 0
    twse = await loop.run_in_executor(None, _fetch_twse_t86, iso_today)
    tpex = await loop.run_in_executor(None, _fetch_tpex_insti, iso_today)
    rows = twse + tpex
    if not rows:
        logger.warning("TW institutional refresh: both feeds empty for %s.", iso_today)
        return 0
    written = await loop.run_in_executor(None, _upsert_insti_rows, rows)
    logger.info("TW institutional refresh: %s wrote %d rows (twse=%d, tpex=%d).", iso_today, written, len(twse), len(tpex))
    return written


def _fetch_latest_market_date() -> Optional[str]:
    """The newest trading date the TPEx 3insti feed reports (drives 'today' for institutional
    — TWSE T86 for the same date is then historical-capable). Falls back to None if unreachable."""
    try:
        payload = requests.get(_TPEX_INSTI_URL, headers={"User-Agent": _BROWSER_UA}, timeout=60).json()
    except Exception as e:
        logger.warning("TPEx 3insti latest-date probe failed: %s", e)
        return None
    dates = {_roc_to_iso(str(rec.get("Date", ""))) for rec in (payload if isinstance(payload, list) else [])}
    dates.discard(None)
    return max(dates) if dates else None


async def backfill_tw_institutional(days: int = _INSTI_BACKFILL_DAYS, gap_seconds: float = _BACKFILL_GAP_SECONDS) -> int:
    """Seed `days` of 三大法人 history. TWSE T86 is historical; TPEx OpenAPI is today-only, so
    OTC (上櫃) institutional accretes forward instead. Idempotent + resumable. Never raises."""
    loop = asyncio.get_event_loop()
    dates = _weekday_dates(days)
    filled = total = 0
    for iso in dates:
        if await loop.run_in_executor(None, _insti_rows_for_date, iso) >= _MIN_ROWS_PER_DAY:
            continue
        twse = await loop.run_in_executor(None, _fetch_twse_t86, iso)
        await asyncio.sleep(gap_seconds)
        if twse:
            total += await loop.run_in_executor(None, _upsert_insti_rows, twse)
            filled += 1
    logger.info(
        "TW institutional backfill: filled %d day(s), wrote %d rows (TWSE T86 only; OTC accretes forward).",
        filled, total,
    )
    return total


async def run_periodic_tw_ohlc_refresh(
    interval_hours: float = 6.0,
    backfill_days: int = _BACKFILL_DAYS,
    after_refresh: Optional[Callable[[], Awaitable[Any]]] = None,
) -> None:
    """Background loop: refresh on startup, then every interval_hours. Never raises.

    Both feeds publish the finalized day after ~15:00 Taipei; a 6h cadence lands the day
    within one cycle and cheaply re-confirms it (upsert overwrites), at 2 calls/run. On the
    first cycle it also seeds `backfill_days` of history (idempotent — a no-op once filled).

    ``after_refresh``, if given, is awaited once per cycle right after the OHLC +
    institutional refresh (and first-run backfill) complete — e.g. to chain the screener
    so it always runs against data from *this* cycle rather than as an independent loop
    that could race ahead of the day's warm-table write. A failure in the hook is caught
    and logged like every other step here; it never breaks the refresh loop.
    """
    first = True
    while True:
        try:
            await refresh_tw_daily_ohlc()
        except Exception as e:
            logger.warning("TW OHLC refresh cycle failed: %s", e)
        try:
            await refresh_tw_institutional()
        except Exception as e:
            logger.warning("TW institutional refresh cycle failed: %s", e)
        if first:
            first = False
            try:
                await backfill_tw_daily_ohlc(days=backfill_days)
            except Exception as e:
                logger.warning("TW OHLC backfill failed: %s", e)
            try:
                await backfill_tw_institutional()
            except Exception as e:
                logger.warning("TW institutional backfill failed: %s", e)
        if after_refresh is not None:
            try:
                await after_refresh()
            except Exception as e:
                logger.warning("post-refresh hook failed: %s", e)
        await asyncio.sleep(interval_hours * 3600)


if __name__ == "__main__":
    # Manual run against the live exchanges (writes to the configured DB): `refresh` fetches
    # today, `backfill [days]` seeds history. Parsing is covered by the unit tests.
    import sys
    logging.basicConfig(level=logging.INFO)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "refresh"
    if cmd == "backfill":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else _BACKFILL_DAYS
        print("OHLC backfilled", asyncio.run(backfill_tw_daily_ohlc(days=days)), "rows")
        print("institutional backfilled", asyncio.run(backfill_tw_institutional()), "rows")
    else:
        print("OHLC wrote", asyncio.run(refresh_tw_daily_ohlc()), "rows")
        print("institutional wrote", asyncio.run(refresh_tw_institutional()), "rows")
    sys.exit(0)
