"""
Stock API router
"""
import json
import asyncio
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from src.models.stock import CompanyDetail
from src.services.stock import StockService
from src.services.websocket_subscriber import WebSocketSubscriber
from src.database.postgres import get_session
from src.database.models import StockTranslation, StockDailyClose, StockDailyOHLC, StockInstitutionalDaily
from src.utils.market import infer_market
from src.services.stock_close_refresh import batch_read_latest_closes, change_pct_from_pairs
from src.services.mention_sync import _closes_from, _is_price_break
from src.cache.redis_client import cache_get, cache_set
from src.cache.cache_config import CACHE_TTL
from src.routers.screener import require_internal_key
from src.utils.dependencies import require_member
from src.models.user import UserResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stocks", tags=["stocks"])

# Initialize service
stock_service = StockService()


def _has_cjk(text: Optional[str]) -> bool:
    if not text:
        return False
    return any(
        "㐀" <= ch <= "鿿" or "豈" <= ch <= "﫿"
        for ch in text
    )


def _translation_display_name(row: StockTranslation) -> str:
    pref = getattr(row, "name_preference", None) or "auto"
    if _has_cjk(row.name_zh_tw) and pref != "en":
        return row.name_zh_tw or row.ticker
    return row.name_en or row.ticker


# --------------------------------------------------------------------------- #
# Whole-universe daily market-data read endpoints (issue #449)
#
# Machine-only, internal-key gated (same mechanism as /api/screener). They serve the warm
# ``stock_daily_ohlc`` / ``stock_institutional_daily`` tables in bulk for backtesting /
# Hermes analysis — the screener services read Postgres directly and don't need these.
# --------------------------------------------------------------------------- #
_MARKET_SOURCES = {"tw": ("twse", "tpex"), "us": ("polygon",)}
_MAX_RANGE_DAYS = 90


def _resolve_range(date: Optional[str], start: Optional[str], end: Optional[str]) -> tuple[str, str]:
    """Validate the (date | start+end) query into an inclusive [start, end] pair of
    YYYY-MM-DD strings, or raise HTTPException(400). Caps the span at _MAX_RANGE_DAYS."""
    if date:
        start = end = date
    if not start or not end:
        raise HTTPException(status_code=400, detail="provide start & end (or date)")
    try:
        s = datetime.strptime(start, "%Y-%m-%d").date()
        e = datetime.strptime(end, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="dates must be YYYY-MM-DD")
    if e < s:
        raise HTTPException(status_code=400, detail="end is before start")
    if (e - s).days > _MAX_RANGE_DAYS:
        raise HTTPException(status_code=400, detail=f"range exceeds {_MAX_RANGE_DAYS} days")
    return start, end


@router.get("/daily-ohlc", dependencies=[Depends(require_internal_key)])
def get_daily_ohlc(
    market: str = Query("tw", description="tw | us"),
    start: Optional[str] = Query(None, description="Inclusive start YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="Inclusive end YYYY-MM-DD"),
    date: Optional[str] = Query(None, description="Shorthand for start=end=date"),
    db: Session = Depends(get_session),
):
    """Whole-universe daily OHLCV bars for a market over [start, end] (<= 90 days).

    ``market=tw`` → TWSE+TPEx rows; ``market=us`` → Polygon rows. Returns a JSON array of
    row objects ordered by (date, ticker); an empty range yields ``[]``.
    """
    sources = _MARKET_SOURCES.get(market.lower())
    if not sources:
        raise HTTPException(status_code=400, detail="market must be 'tw' or 'us'")
    s, e = _resolve_range(date, start, end)
    rows = (
        db.query(StockDailyOHLC)
        .filter(StockDailyOHLC.source.in_(sources), StockDailyOHLC.date >= s, StockDailyOHLC.date <= e)
        .order_by(StockDailyOHLC.date, StockDailyOHLC.ticker)
        .all()
    )
    return [
        {
            "ticker": r.ticker, "date": r.date, "open": r.open, "high": r.high,
            "low": r.low, "close": r.close, "volume": r.volume,
            "trading_value": r.trading_value, "source": r.source,
        }
        for r in rows
    ]


@router.get("/daily-institutional", dependencies=[Depends(require_internal_key)])
def get_daily_institutional(
    market: str = Query("tw", description="tw only for now"),
    start: Optional[str] = Query(None, description="Inclusive start YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="Inclusive end YYYY-MM-DD"),
    date: Optional[str] = Query(None, description="Shorthand for start=end=date"),
    db: Session = Depends(get_session),
):
    """Whole-universe daily 三大法人 net shares over [start, end] (<= 90 days). TW-only —
    the US institutional feed isn't warmed. Returns a JSON array ordered by (date, ticker)."""
    if market.lower() != "tw":
        raise HTTPException(status_code=400, detail="institutional data is TW-only")
    s, e = _resolve_range(date, start, end)
    rows = (
        db.query(StockInstitutionalDaily)
        .filter(StockInstitutionalDaily.date >= s, StockInstitutionalDaily.date <= e)
        .order_by(StockInstitutionalDaily.date, StockInstitutionalDaily.ticker)
        .all()
    )
    return [
        {
            "ticker": r.ticker, "date": r.date,
            "foreign_net_shares": r.foreign_net_shares,
            "trust_net_shares": r.trust_net_shares,
            "total_net_shares": r.total_net_shares,
            "source": r.source,
        }
        for r in rows
    ]


@router.get("", response_model=List[dict])
async def get_sorted_stocks(
    sort_by: str = Query(default="ticker", description="Sort field"),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum number of stocks to return (1-200)"),
    q: Optional[str] = Query(default=None, description="Search query (filters by ticker or name)")
):
    """
    Get sorted stocks list with optional search
    
    Query params:
    - sort_by: Sort field (ticker, name, price, change_percent, market_cap)
    - limit: Maximum number of stocks to return (default: 50, max: 200)
    - q: Optional search query to filter by ticker or name (case-insensitive)
    """
    stocks = await stock_service.get_sorted_stocks_async(sort_by=sort_by, limit=limit)
    
    # Apply search filter if provided
    if q:
        q_lower = q.lower()
        stocks = [
            stock for stock in stocks
            if q_lower in stock.get("ticker", "").lower() or q_lower in stock.get("name", "").lower()
        ]
    
    return stocks


@router.get("/batch-prices")
async def get_batch_prices(
    tickers: str = Query(description="Comma-separated ticker symbols (max 100)"),
):
    """
    Get changePercent for multiple tickers in one request.

    End-of-day change% from the warm Postgres tables (``stock_daily_closes`` +
    ``stock_daily_ohlc``), then the last-known-good Redis copy. Never calls FinMind/Massive:
    one page view carries ~200 tickers and the old per-ticker live fallback cost ~5 Massive
    calls each, which 429-stormed the whole process. A miss is a cheap miss (null).
    Returns {TICKER: changePercent} — null if unavailable.
    """
    ticker_list = [t.strip().upper() for t in tickers.split(',') if t.strip()][:100]
    if not ticker_list:
        return {}

    latest = await asyncio.to_thread(batch_read_latest_closes, ticker_list)

    async def _change(t: str) -> Optional[float]:
        pct = change_pct_from_pairs(latest.get(t))
        if pct is not None:
            return pct
        # Not warmed yet: serve the last-known-good copy the /basic route left in Redis.
        # A fresh entry that itself has no changePercent is not an answer — keep looking.
        for key in (f"stock:{t}:basic", f"stock:{t}:basic:stale"):
            cached = await cache_get(key)
            if not cached:
                continue
            try:
                pct = json.loads(cached).get("changePercent")
            except Exception:
                continue
            if pct is not None:
                return pct
        return None

    results = await asyncio.gather(*[_change(t) for t in ticker_list])
    return {ticker: pct for ticker, pct in zip(ticker_list, results)}


class TickerDatePair(BaseModel):
    ticker: str
    reference_ms: int = Field(..., description="Episode release timestamp (Unix ms)")


class BatchPricesSinceRequest(BaseModel):
    items: list[TickerDatePair] = Field(..., max_length=300)


# Concurrency limiter: at most 5 simultaneous external API calls to avoid
# thundering-herd on FinMind / Massive (which are aggressively rate-limited).
_ext_api_sem = asyncio.Semaphore(5)

# Short negative-cache TTL so we don't re-hammer failing APIs on every request.
_NULL_CACHE_TTL = 300  # 5 min


def _read_dated_close_before(ticker: str, ref_date_str: str) -> Optional[tuple]:
    """``(date, close)`` of the newest stored close in the 7-day window ending at
    *ref_date_str*, from either warm table, or None.

    A one-ticker call into :func:`batch_read_latest_closes` so the single-ticker and batch
    paths can't drift apart on which tables they read or how they break a date tie.
    """
    pairs = batch_read_latest_closes([ticker], days=7, ref_date_str=ref_date_str).get(ticker)
    return pairs[-1] if pairs else None


def _read_close_before(ticker: str, ref_date_str: str) -> Optional[float]:
    """Newest stored close in the 7-day window ending at *ref_date_str* (see
    :func:`_read_dated_close_before`); None when neither table has a row."""
    found = _read_dated_close_before(ticker, ref_date_str)
    return found[1] if found else None


def _read_close_date_before(ticker: str, ref_date_str: str) -> Optional[str]:
    """Date of the close :func:`_read_close_before` would return, or None when the DB has
    no row in the window (API-fetched closes are not dated here — see ``_window_returns``)."""
    try:
        found = _read_dated_close_before(ticker, ref_date_str)
        return found[0] if found else None
    except Exception:
        logger.debug("close date lookup failed for %s@%s", ticker, ref_date_str, exc_info=True)
    return None


def _persist_close(ticker: str, date: str, close: float) -> None:
    """Store a fetched close so this (ticker, date) never needs an API call again.

    Own session, same reason as :func:`_read_close_before`.
    """
    from src.services.stock_close_refresh import close_is_final

    if not close_is_final(ticker, date):
        return  # intraday quote, not a close — the warmer stores it after the session
    for session in get_session():
        try:
            existing = (
                session.query(StockDailyClose)
                .filter(StockDailyClose.ticker == ticker, StockDailyClose.date == date)
                .first()
            )
            if not existing:
                session.add(StockDailyClose(ticker=ticker, date=date, close=close))
                session.commit()
        except Exception:
            session.rollback()
        return


async def _get_reference_close(
    ticker: str,
    ref_date_str: str,
) -> Optional[float]:
    """Return the closing price on or just before *ref_date_str*.

    Lookup order:
      1. PostgreSQL warm tables (``stock_daily_closes`` + ``stock_daily_ohlc``)
      2. Redis cache (catches recent API results; 24 h TTL)
      3. FinMind, TW tickers only — result persisted to both DB + Redis. US tickers stop
         here: the ~5/min Massive budget can't serve a per-ticker fan-out on the request
         path (one page view = ~200 tickers), so a US miss is a cheap, negatively-cached
         miss and the yfinance mention backfill / close warmer fill the table offline.

    Every DB touch is offloaded with its own session, so this is safe to fan out
    concurrently — which is exactly what all three batch-price routes do.
    """
    # --- 1. DB lookup (permanent store, 7-day window) ---
    stored = await asyncio.to_thread(_read_close_before, ticker, ref_date_str)
    if stored is not None:
        return stored

    # --- 2. Redis cache ---
    cache_key = f"stock:{ticker}:close:{ref_date_str}"
    cached = await cache_get(cache_key)
    if cached is not None:
        if cached == "__null__":
            return None
        try:
            return float(cached)
        except (ValueError, TypeError):
            pass

    # --- 3. External API (rate-limited) — TW/FinMind only; US never fans out from here ---
    # infer_market, not `.isdigit()`: that read TW class-letter ETFs (00878B, 00632R) as US
    # and permanently null-cached them, and sent 6-digit KR codes (005930) into FinMind.
    if infer_market(ticker) != "TW":
        await cache_set(cache_key, "__null__", _NULL_CACHE_TTL)
        return None
    async with _ext_api_sem:
        loop = asyncio.get_event_loop()
        start = (datetime.strptime(ref_date_str, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
        try:
            from src.services.finmind_service import FinMindAPIService
            svc = FinMindAPIService()
            rows = await loop.run_in_executor(
                None, lambda: svc.list_daily_ticker_summary_range(ticker.split(".")[0], start, ref_date_str),
            )
        except Exception:
            rows = []

    if not rows:
        await cache_set(cache_key, "__null__", _NULL_CACHE_TTL)
        return None

    close = rows[-1].get("close")
    if close is None:
        await cache_set(cache_key, "__null__", _NULL_CACHE_TTL)
        return None

    # Persist to DB so this (ticker, date) never needs an API call again.
    actual_date = rows[-1].get("date", ref_date_str)
    await asyncio.to_thread(_persist_close, ticker, actual_date, close)

    await cache_set(cache_key, str(close), CACHE_TTL["stock_history"])
    return close


@router.post("/batch-prices-since")
async def get_batch_prices_since(
    body: BatchPricesSinceRequest,
):
    """Return % change from each ticker's reference date to its latest stored close.

    Both legs go through ``_get_reference_close`` (Postgres → Redis → FinMind for TW; never
    Massive), so a page's ~200 US tickers cost zero upstream calls. "Current" is the latest
    warmed close, like ``/batch-prices-windows`` — EOD is fine for a podcast-insight site.
    The full response is cached in Redis for 30 min.
    """
    # Deduplicate: same ticker may appear in multiple episodes; pick earliest date.
    earliest: dict[str, str] = {}
    for item in body.items:
        t = item.ticker.upper()
        d = datetime.utcfromtimestamp(item.reference_ms / 1000).strftime("%Y-%m-%d")
        if t not in earliest or d < earliest[t]:
            earliest[t] = d
    tickers = list(earliest.keys())
    if not tickers:
        return {}

    # --- Response-level Redis cache (30 min) ---
    pairs_key = ",".join(f"{t}:{earliest[t]}" for t in sorted(tickers))
    # v2: a pre-split-guard body (e.g. 6669's -60.3%) must not outlive the deploy.
    resp_cache_key = f"batch_since_v2:{hashlib.md5(pairs_key.encode()).hexdigest()}"
    cached_resp = await cache_get(resp_cache_key)
    if cached_resp:
        try:
            return json.loads(cached_resp)
        except Exception:
            pass

    # Reference closes fan out per ticker (DB-first, FinMind only for a TW miss; 10s cap so
    # a throttled FinMind can't hang the response); the "current" leg is one batched read.
    async def _ref_close_safe(t, d):
        try:
            return await asyncio.wait_for(_get_reference_close(t, d), timeout=10)
        except (asyncio.TimeoutError, Exception):
            logger.warning("reference close failed for %s@%s", t, d, exc_info=True)
            return None

    # Split guard: one DB-only series read per ticker, from the reference close's 7-day
    # lookback on. Closes are unadjusted, so a span that crosses a price break is null.
    ref_closes, latest, series_list = await asyncio.gather(
        asyncio.gather(*[_ref_close_safe(t, earliest[t]) for t in tickers]),
        asyncio.to_thread(batch_read_latest_closes, tickers),
        asyncio.gather(*[_read_series_safe(t, _days_before(earliest[t], 7)) for t in tickers]),
    )
    out: dict[str, Optional[float]] = {}
    for ticker, ref_close, series in zip(tickers, ref_closes, series_list):
        current_price = latest[ticker][-1][1] if latest.get(ticker) else None
        if ref_close and ref_close > 0 and _crosses_price_break(series, earliest[ticker], ref_close):
            out[ticker] = None
        elif ref_close and current_price and ref_close > 0:
            out[ticker] = round((current_price - ref_close) / ref_close * 100, 2)
        else:
            out[ticker] = None

    # Cache the response. Use shorter TTL if most values are null (likely API issues).
    non_null = sum(1 for v in out.values() if v is not None)
    ttl = 1800 if non_null > len(out) * 0.3 else _NULL_CACHE_TTL
    try:
        await cache_set(resp_cache_key, json.dumps(out), ttl)
    except Exception:
        pass
    return out


# Forward windows (calendar days) for the podcast-pick performance scoreboard.
WINDOW_DAYS = (7, 30, 90)


# Sentinel: this ticker's split-guard series could not be read (as opposed to a
# genuine empty list — no rows, which is not a failure). Passed into
# `_window_returns` so it fails closed (raises → `_win_safe` returns the all-None
# dict) instead of silently serving an un-guarded, possibly-wrong return.
_SERIES_READ_FAILED = object()


def _read_series_since(ticker: str, since: str) -> list:
    """Daily close series for *ticker* from *since* on (ascending), DB-only.

    Thin wrapper around ``mention_sync._closes_from`` (same warm tables, same merge
    rule). Fails CLOSED: a DB error propagates rather than being swallowed into an
    empty list — an empty list must mean "no rows", never "couldn't check", because
    the caller treats an empty series as "no break found" and serves the raw return.
    """
    for db in get_session():
        return _closes_from(db, ticker, since)
    return []


def _days_before(date_str: str, days: int) -> str:
    return (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=days)).strftime("%Y-%m-%d")


async def _read_series_safe(ticker: str, since: str):
    """``_read_series_since`` off the event loop; ``_SERIES_READ_FAILED`` instead of
    raising, so each caller fails closed for that ticker only."""
    # ponytail: one range scan per ticker (~200 on a home feed, cached 30 min) — fold
    # into a single `ticker IN (...)` read if this shows up in cold-page latency.
    try:
        return await asyncio.to_thread(_read_series_since, ticker, since)
    except Exception:
        logger.warning("split-guard series read failed for %s@%s", ticker, since, exc_info=True)
        return _SERIES_READ_FAILED


def _break_dates(series: list, prev: Optional[float] = None) -> list:
    """Dates in *series* whose close jumps outside ``PRICE_BREAK_BAND`` vs. the close
    before it (*prev* seeds the first comparison; None skips it)."""
    out = []
    for date, close in series:
        if prev is not None and _is_price_break(prev, close):
            out.append(date)
        prev = close
    return out


def _crosses_price_break(series, ref_date_str: str, ref_close: float) -> bool:
    """True when the span (reference close → newest close) reaches a price break, or
    when *series* could not be read (fail closed). The reference close is the newest
    row on/before *ref_date_str*, so only rows after that date can break the span."""
    if series is _SERIES_READ_FAILED:
        return True
    guard_start = max((d for d, _c in series if d <= ref_date_str), default=ref_date_str)
    return bool(_break_dates([p for p in series if p[0] > guard_start], ref_close))


async def _resolve_price_break_date(
    ticker: str,
    guard_start: str,
    baseline_close: float,
    series: Optional[list],
) -> Optional[str]:
    """First date after *guard_start* where a close in *series* jumps outside
    ``mention_sync.PRICE_BREAK_BAND`` vs. the previous close (``prev`` seeded with
    *baseline_close*) — a stock split or similar (6669's 2026-09-02 3-for-1 is the
    motivating case). Same rule and warm tables as
    ``mention_sync.compute_trading_day_returns``, so a pick can't show a return that
    path would have nulled.

    *series* is normally pre-fetched once per ticker by the batch route and shared
    across that ticker's picks (see ``get_batch_prices_windows``); pass ``None`` to
    have this read its own, so the function stays independently testable. Pass
    ``_SERIES_READ_FAILED`` when the caller already tried and the read failed, so
    this pick fails closed too instead of silently skipping the guard — this raises,
    same as a raw DB error from the ``None`` branch, so `_win_safe` catches either.
    """
    if series is _SERIES_READ_FAILED:
        raise RuntimeError(f"split-guard series unavailable for {ticker}")
    if series is None:
        series = await asyncio.to_thread(_read_series_since, ticker, guard_start)
    breaks = _break_dates([p for p in series if p[0] > guard_start], baseline_close)
    return breaks[0] if breaks else None


async def _window_returns(
    ticker: str,
    reference_ms: int,
    current_price: Optional[float],
    series: Optional[list] = None,
) -> dict:
    """Forward 7/30/90D returns measured *from* the mention date, plus mention→now.

    ``dN`` = ``close@(mention + N calendar days) / baseline − 1``. A window is left
    ``None`` until it has fully elapsed (so the UI can render "—" like the competitor),
    or when a close is missing. Reuses ``_get_reference_close`` (DB → Redis → API), so
    after warm-up this costs no external calls.

    Split guard: every window whose resolved close lands on/after the first
    ``_resolve_price_break_date`` past the baseline is left ``None`` too — closes in
    ``stock_daily_ohlc`` are unadjusted, so a return spanning a split (or similar
    capital change) would otherwise compare pre- and post-split prices. *series* lets
    the caller share one pre-fetched close series across every pick for this ticker
    (see ``get_batch_prices_windows``); omit it to have this read its own.
    """
    result: dict[str, Optional[float]] = {
        "baseline": None, "d7": None, "d30": None, "d90": None, "since": None,
    }
    mention_dt = datetime.utcfromtimestamp(reference_ms / 1000)
    mention_date_str = mention_dt.strftime("%Y-%m-%d")
    baseline = await _get_reference_close(ticker, mention_date_str)
    if not baseline or baseline <= 0:
        return result
    result["baseline"] = baseline

    now = datetime.utcnow()
    base_date = await asyncio.to_thread(_read_close_date_before, ticker, mention_date_str)
    # Unresolved base_date (baseline came from an API fetch not found via the 7-day
    # DB lookback) must not disable the guard — approximate with the mention date.
    guard_start = base_date or mention_date_str
    break_date = await _resolve_price_break_date(ticker, guard_start, baseline, series)

    for n in WINDOW_DAYS:
        end_dt = mention_dt + timedelta(days=n)
        if end_dt > now:
            continue  # window not complete yet → leave None ("—")
        end_date_str = end_dt.strftime("%Y-%m-%d")
        end_close = await _get_reference_close(ticker, end_date_str)
        if end_close and end_close > 0 and not (break_date and end_date_str >= break_date):
            result[f"d{n}"] = round((end_close - baseline) / baseline * 100, 2)

    if current_price and current_price > 0:
        # A mention on Friday night or a weekend has no close after its baseline yet:
        # "since" would be the baseline against itself (+0.00%). Leave it None so the
        # card says the market hasn't closed since, instead of showing a fake flat.
        latest_date = await asyncio.to_thread(_read_close_date_before, ticker, now.strftime("%Y-%m-%d"))
        if base_date and latest_date and latest_date <= base_date:
            return result
        # A break with no resolvable latest_date can't be proven clear of it either —
        # don't emit a "since" we can't back up.
        if break_date and (latest_date is None or latest_date >= break_date):
            return result
        result["since"] = round((current_price - baseline) / baseline * 100, 2)
    return result


@router.post("/batch-prices-windows")
async def get_batch_prices_windows(
    body: BatchPricesSinceRequest,
    _user: UserResponse = Depends(require_member),
):
    """Forward 7/30/90D (+ since) returns per *pick*, keyed by ``"{TICKER}:{reference_ms}"``.

    Member-only (401 anonymous, 402 non-member) — this powers the paid /picks page and
    the same block on PodcasterPage; `require_member` is a FastAPI dependency, resolved
    before the function body runs, so a non-member never reaches the Redis-cached body
    below (and can't be served a member's cached response either).

    Unlike ``/batch-prices-since`` (one row per ticker), each (ticker, mention-date) pair
    is computed independently so the same ticker mentioned by different episodes keeps its
    own scorecard. Current price is fetched once per distinct ticker. Cached in Redis.
    """
    # Dedupe by (ticker, reference_ms) — each pick keeps its own mention date.
    pairs: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for item in body.items:
        key = (item.ticker.upper(), item.reference_ms)
        if key not in seen:
            seen.add(key)
            pairs.append(key)
    if not pairs:
        return {}

    # --- Response-level Redis cache ---
    # v2: bumped so a pre-split-guard cached body (up to 30 min old, e.g. 6669's bad
    # d30/since) is never served after this fix deploys.
    pairs_key = ",".join(f"{t}:{ms}" for t, ms in sorted(pairs))
    resp_cache_key = f"batch_windows_v2:{hashlib.md5(pairs_key.encode()).hexdigest()}"
    cached_resp = await cache_get(resp_cache_key)
    if cached_resp:
        try:
            return json.loads(cached_resp)
        except Exception:
            pass

    distinct_tickers = list({t for t, _ in pairs})
    today_str = datetime.utcnow().strftime("%Y-%m-%d")

    # "Current" = latest stored close (DB-first via _get_reference_close), NOT the
    # live intraday price. The live `get_stock_basic_info_async` path is rate-limited
    # and returned null for many real tickers under batch load, leaving `since` empty.
    # Close-to-close is also consistent with the 7/30/90D windows.
    async def _latest_close_safe(t):
        try:
            return await asyncio.wait_for(_get_reference_close(t, today_str), timeout=12)
        except (asyncio.TimeoutError, Exception):
            logger.warning("latest close failed for %s@%s", t, today_str, exc_info=True)
            return None

    # Split-guard series: ONE read per distinct ticker, not per pick — a ticker
    # mentioned by N episodes shares one series instead of N identical range scans.
    # Starts 7 days before the ticker's earliest mention in this request (covers the
    # baseline lookback); a read failure marks the ticker so every one of its picks
    # fails closed (see `_resolve_price_break_date`'s `_SERIES_READ_FAILED` handling)
    # instead of silently serving an un-guarded return.
    earliest_ms: dict[str, int] = {}
    for t, ms in pairs:
        if t not in earliest_ms or ms < earliest_ms[t]:
            earliest_ms[t] = ms

    async def _series_safe(t: str):
        mention = datetime.utcfromtimestamp(earliest_ms[t] / 1000).strftime("%Y-%m-%d")
        return await _read_series_safe(t, _days_before(mention, 7))

    latest_list, series_list = await asyncio.gather(
        asyncio.gather(*[_latest_close_safe(t) for t in distinct_tickers]),
        asyncio.gather(*[_series_safe(t) for t in distinct_tickers]),
    )
    latest = dict(zip(distinct_tickers, latest_list))
    series_map = dict(zip(distinct_tickers, series_list))

    async def _win_safe(t: str, ms: int) -> dict:
        try:
            return await asyncio.wait_for(
                _window_returns(t, ms, latest.get(t), series=series_map.get(t)), timeout=15,
            )
        except (asyncio.TimeoutError, Exception):
            logger.warning(
                "window returns failed for %s@%s", t,
                datetime.utcfromtimestamp(ms / 1000).strftime("%Y-%m-%d"), exc_info=True,
            )
            return {"baseline": None, "d7": None, "d30": None, "d90": None, "since": None}

    results = await asyncio.gather(*[_win_safe(t, ms) for t, ms in pairs])
    out = {f"{t}:{ms}": r for (t, ms), r in zip(pairs, results)}

    # Shorter TTL when most picks have no usable data (likely upstream API issues).
    non_null = sum(
        1 for r in out.values()
        if any(r.get(k) is not None for k in ("d7", "d30", "d90", "since"))
    )
    ttl = 1800 if non_null > len(out) * 0.3 else _NULL_CACHE_TTL
    try:
        await cache_set(resp_cache_key, json.dumps(out), ttl)
    except Exception:
        pass
    return out


# ── Trailing performance windows (sector / stock cards) ──────────────────────
# Backward-looking 1/7/30/90D close-to-close returns, anchored on each ticker's
# latest stored close, plus a recent close series for sparklines. Powers the
# /sector/:id member mini-cards.
TRAILING_WINDOWS = (7, 30, 90)


def _batch_read_dated_closes(tickers: List[str], limit: int = 120) -> dict:
    """Per-ticker ``[(iso_date, close)]`` lists (date asc), last ``limit`` points.

    Opens its own DB session (it's called via asyncio.to_thread) so it never shares
    the request session across threads. ``date`` is an ISO 'YYYY-MM-DD' string column,
    so ordering and comparisons are plain lexicographic.
    """
    out: dict = {}
    if not tickers:
        return out
    for session in get_session():
        try:
            rows = (
                session.query(
                    StockDailyClose.ticker, StockDailyClose.date, StockDailyClose.close
                )
                .filter(StockDailyClose.ticker.in_(tickers))
                .order_by(StockDailyClose.ticker.asc(), StockDailyClose.date.asc())
                .all()
            )
            for ticker, date, close in rows:
                out.setdefault(ticker, []).append((date, close))
        except Exception as exc:
            logger.debug(f"trailing dated-close read failed: {exc}")
        break
    return {t: pairs[-limit:] for t, pairs in out.items()}


async def _trailing_returns(ticker: str, pairs: list, last_break: Optional[str] = None) -> dict:
    """Trailing 1/7/30/90D close-to-close % returns, anchored on the latest close.

    ``pairs`` is the ticker's ``[(iso_date, close)]`` list (date asc) from the DB. All
    windows share the same latest close so they stay mutually consistent. ``d1`` is the
    change vs the previous stored trading day. ``d7/d30/d90`` anchor on the close
    on-or-before (latest_date − N days): taken from the series when present, otherwise
    fetched via ``_get_reference_close`` (DB → Redis → API) so deep windows fill in even
    when the local table is shallow. A window stays ``None`` when its anchor is missing.

    Split guard: closes are unadjusted, so a window whose anchor predates *last_break*
    (the newest price-break date in the ticker's series, see ``_break_dates``) is ``None``.
    """
    result: dict = {"price": None, "d1": None, "d7": None, "d30": None, "d90": None}
    if not pairs:
        return result
    dates = [p[0] for p in pairs]
    closes = [p[1] for p in pairs]
    latest = closes[-1]
    if not latest or latest <= 0:
        return result
    result["price"] = latest

    # d1 — vs the previous stored trading day (gap-robust; not a fixed calendar day).
    if len(closes) >= 2 and closes[-2] and closes[-2] > 0 and not (last_break and last_break > dates[-2]):
        result["d1"] = round((latest - closes[-2]) / closes[-2] * 100, 2)

    try:
        latest_dt = datetime.strptime(dates[-1], "%Y-%m-%d")
    except (ValueError, TypeError):
        latest_dt = None

    for n in TRAILING_WINDOWS:
        anchor: Optional[float] = None
        if latest_dt is not None:
            target = (latest_dt - timedelta(days=n)).strftime("%Y-%m-%d")
            # Most recent close in the series on-or-before the target date.
            anchor_date = target  # a fetched anchor is the newest close on/before target
            for d, c in zip(reversed(dates), reversed(closes)):
                if d <= target:
                    anchor, anchor_date = c, d
                    break
            # Target predates our series → fetch the anchor (DB → Redis → API).
            if anchor is None and dates and target < dates[0]:
                anchor = await _get_reference_close(ticker, target)
            if last_break and last_break > anchor_date:
                continue
        if anchor and anchor > 0:
            result[f"d{n}"] = round((latest - anchor) / anchor * 100, 2)
    return result


class BatchTrailingRequest(BaseModel):
    tickers: List[str] = Field(default_factory=list)


@router.post("/batch-prices-trailing")
async def get_batch_prices_trailing(
    body: BatchTrailingRequest,
):
    """Trailing 1/7/30/90D returns (+ recent close series) per ticker.

    Keyed by upper-cased ticker → ``{price, d1, d7, d30, d90, series}``. Powers the
    /sector/:id member performance cards. DB-first (one batch read) with an API
    fallback only for deep anchors; the whole response is cached in Redis.
    """
    tickers = list({t.strip().upper() for t in body.tickers if t and t.strip()})[:60]
    if not tickers:
        return {}

    # v3: a pre-split-guard body must not outlive the deploy.
    resp_cache_key = "batch_trailing:v3:" + hashlib.md5(
        ",".join(sorted(tickers)).encode()
    ).hexdigest()
    cached_resp = await cache_get(resp_cache_key)
    if cached_resp:
        try:
            return json.loads(cached_resp)
        except Exception:
            pass

    dated = await asyncio.to_thread(_batch_read_dated_closes, tickers, 120)

    # Split guard: one DB-only series read per ticker, covering the d90 anchor's 7-day
    # lookback. A failed read fails closed — every return for that ticker is null.
    async def _last_break(t: str):
        if not dated.get(t):
            return None
        series = await _read_series_safe(t, _days_before(dated[t][-1][0], 100))
        if series is _SERIES_READ_FAILED:
            return _SERIES_READ_FAILED
        breaks = _break_dates(series)
        return breaks[-1] if breaks else None

    last_breaks = dict(zip(tickers, await asyncio.gather(*[_last_break(t) for t in tickers])))

    async def _safe(t: str) -> dict:
        try:
            if last_breaks[t] is _SERIES_READ_FAILED:
                raise RuntimeError(f"split-guard series unavailable for {t}")
            return await asyncio.wait_for(
                _trailing_returns(t, dated.get(t, []), last_breaks[t]), timeout=15,
            )
        except (asyncio.TimeoutError, Exception):
            return {"price": None, "d1": None, "d7": None, "d30": None, "d90": None}

    results = await asyncio.gather(*[_safe(t) for t in tickers])
    out: dict = {}
    for t, r in zip(tickers, results):
        r = dict(r)
        # The sparkline starts at the last break, so a split doesn't draw as a crash.
        brk = last_breaks[t] if isinstance(last_breaks[t], str) else ""
        closes = [c for d, c in dated.get(t, []) if d >= brk]
        r["series"] = closes[-30:] if len(closes) >= 2 else []
        out[t] = r

    non_null = sum(
        1 for r in out.values()
        if any(r.get(k) is not None for k in ("d1", "d7", "d30", "d90"))
    )
    ttl = 1800 if non_null > len(out) * 0.3 else _NULL_CACHE_TTL
    try:
        await cache_set(resp_cache_key, json.dumps(out), ttl)
    except Exception:
        pass
    return out


@router.get("/batch-summary")
async def get_batch_summary(
    tickers: str = Query(description="Comma-separated ticker symbols (max 100)"),
    db: Session = Depends(get_session),
):
    """
    Return display metadata (name + market + brand_color) for a set of tickers.
    Used by watchlist / index rows to render Chinese-name labels without N round-trips.
    Returns a list of {ticker, name, market, brand_color}; entries missing in upstream
    data still appear with name=ticker so callers can render.
    """
    requested_tickers = [t.strip().upper() for t in tickers.split(',') if t.strip()][:100]
    if not requested_tickers:
        return []
    lookup_tickers = [t.split(".")[0] for t in requested_tickers]

    rows = await asyncio.to_thread(
        lambda: db.query(StockTranslation)
        .filter(StockTranslation.ticker.in_(lookup_tickers))
        .all()
    )
    translations: dict[str, StockTranslation] = {}
    for row in rows:
        inferred_market = infer_market(row.ticker)
        existing = translations.get(row.ticker)
        if existing is None or row.market == inferred_market:
            translations[row.ticker] = row

    out = []
    for requested, lookup in zip(requested_tickers, lookup_tickers):
        market = infer_market(lookup)
        row = translations.get(lookup)
        out.append({
            "ticker": requested,
            "name": _translation_display_name(row) if row else lookup,
            "market": market,
            "brand_color": row.brand_color if row else None,
        })
    return out


@router.get("/{ticker}", response_model=CompanyDetail)
async def get_stock_by_ticker(
    ticker: str,
    timeframe: Optional[str] = Query(
        default=None,
        description="Timeframe filter: 1H, 1D, 1W, 1M, 3M, 6M, 1Y, YTD, ALL",
        regex="^(1H|1D|1W|1M|3M|6M|1Y|YTD|ALL)$"
    ),
    before: Optional[int] = Query(
        default=None,
        description="Fetch data before this Unix timestamp (ms) for infinite scroll"
    )
):
    """
    Get stock by ticker
    
    Returns full stock information including chart data filtered by timeframe.
    
    Query Parameters:
    - timeframe: Optional timeframe filter. Valid options:
      - 1H: Last 1 hour (limited data availability with daily aggregates)
      - 1D: Last 24 hours
      - 1W: Last 7 days
      - 1M: Last 30 days
      - 3M: Last 90 days
      - 6M: Last 180 days
      - 1Y: Last 365 days
      - YTD: Year to date (from January 1st)
      - ALL: All available data (default if not specified)
    - before: Optional Unix timestamp (ms). Fetch historical data ending before this time.
      Used for infinite scroll / lazy loading of older data.
    """
    # Validate timeframe if provided
    if timeframe:
        from src.utils.timeframe import is_valid_timeframe
        if not is_valid_timeframe(timeframe):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid timeframe: {timeframe}. Valid options: 1H, 1D, 1W, 1M, 3M, 6M, 1Y, YTD, ALL"
            )
    
    stock = await stock_service.get_stock_info_async(ticker.upper(), timeframe=timeframe, before=before)
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock {ticker} not found")
    return stock


@router.get("/{ticker}/basic")
async def get_stock_basic_info(ticker: str):
    """
    Get basic stock information only (no chart data)
    """
    stock_info = await stock_service.get_stock_basic_info_async(ticker.upper())
    if not stock_info:
        raise HTTPException(status_code=404, detail=f"Stock {ticker} not found")
    return stock_info


@router.get("/{ticker}/institutional")
async def get_stock_institutional(
    ticker: str,
    days: int = Query(60, ge=5, le=_MAX_RANGE_DAYS, description="Trading-day window, newest last"),
    db: Session = Depends(get_session),
):
    """Public per-ticker 三大法人 daily net shares for the stock page chart (TW only).

    Reads the warm ``stock_institutional_daily`` table — the same rows the internal
    ``/daily-institutional`` bulk feed serves, scoped to one ticker so it needs no key.
    US tickers and tickers with no rows return an empty list rather than 404: the card
    is additive and simply hides.
    """
    sym = ticker.upper()
    if infer_market(sym) != "TW":
        return {"ticker": sym, "rows": []}
    cache_key = f"stock:institutional:v1:{sym}:{days}"
    cached = await cache_get(cache_key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass
    rows = (
        db.query(StockInstitutionalDaily)
        .filter(StockInstitutionalDaily.ticker == sym)
        .order_by(StockInstitutionalDaily.date.desc())
        .limit(days)
        .all()
    )
    payload = {
        "ticker": sym,
        "rows": [
            {
                "date": r.date,
                "foreign_net_shares": r.foreign_net_shares,
                "trust_net_shares": r.trust_net_shares,
                "total_net_shares": r.total_net_shares,
            }
            for r in reversed(rows)
        ],
    }
    try:
        await cache_set(cache_key, json.dumps(payload), CACHE_TTL["stock_history"])
    except Exception:
        pass
    return payload


@router.get("/{ticker}/history")
async def get_stock_history(
    ticker: str,
    timeframe: Optional[str] = Query(
        default=None,
        description="Timeframe filter: 1H, 1D, 1W, 1M, 3M, 6M, 1Y, YTD, ALL",
        regex="^(1H|1D|1W|1M|3M|6M|1Y|YTD|ALL)$"
    )
):
    """
    Get stock price history for sparklines
    
    Returns lightweight price history data extracted from chart data.
    
    Query Parameters:
    - timeframe: Optional timeframe filter. Valid options:
      - 1H: Last 1 hour
      - 1D: Last 24 hours
      - 1W: Last 7 days
      - 1M: Last 30 days
      - 3M: Last 90 days
      - 6M: Last 180 days
      - 1Y: Last 365 days
      - YTD: Year to date
      - ALL: All available data (default)
    """
    # Validate timeframe if provided
    if timeframe:
        from src.utils.timeframe import is_valid_timeframe
        if not is_valid_timeframe(timeframe):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid timeframe: {timeframe}. Valid options: 1H, 1D, 1W, 1M, 3M, 6M, 1Y, YTD, ALL"
            )
    
    # Get full stock info with chart data
    stock = await stock_service.get_stock_info_async(ticker.upper(), timeframe=timeframe)
    if not stock:
        raise HTTPException(status_code=404, detail=f"Stock {ticker} not found")
    
    # Extract history from chartData
    chart_data = stock.chartData if hasattr(stock, 'chartData') else []
    
    # Convert to lightweight format
    history_data = [
        {
            "time": point.date,
            "price": point.close
        }
        for point in chart_data
    ]
    
    return {
        "symbol": ticker.upper(),
        "data": history_data
    }


@router.websocket("/{ticker}/ohlcv")
async def websocket_ohlcv(websocket: WebSocket, ticker: str):
    """
    WebSocket endpoint for OHLCV data streaming using Redis pub/sub
    
    Streams real-time OHLCV updates for the specified ticker
    """
    await websocket.accept()
    ticker_upper = ticker.upper()
    
    subscriber = None
    try:
        # Create subscriber manager
        subscriber = WebSocketSubscriber(websocket)
        
        # Subscribe to ticker updates
        if not await subscriber.subscribe(ticker_upper):
            await websocket.close(code=1011, reason="Failed to subscribe to updates")
            return
        
        # Start listening for messages
        await subscriber.start_listening()
        
        # Keep connection alive and handle client messages (optional)
        while True:
            try:
                # Wait for client message or timeout
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # Handle client messages if needed (e.g., unsubscribe, change ticker)
                logger.debug(f"Received message from client: {data}")
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_json({"type": "ping"})
            except WebSocketDisconnect:
                break
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for {ticker_upper}")
    except Exception as e:
        logger.error(f"Error in WebSocket for {ticker_upper}: {e}")
        await websocket.close(code=1011, reason=str(e))
    finally:
        # Cleanup subscription
        if subscriber:
            await subscriber.stop()

