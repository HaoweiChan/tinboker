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
from src.database.models import StockTranslation, StockDailyClose
from src.utils.market import infer_market
from src.cache.redis_client import cache_get, cache_set
from src.cache.cache_config import CACHE_TTL

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

    Serves end-of-day change% from the warm stock_daily_closes table (no external API),
    falling back to the live per-ticker path only for tickers not yet stored.
    Returns {TICKER: changePercent} — null if unavailable.
    """
    ticker_list = [t.strip().upper() for t in tickers.split(',') if t.strip()][:100]
    if not ticker_list:
        return {}

    from src.services.stock_close_refresh import get_eod_change_pct

    async def _change(t: str):
        # 1. EOD change from Postgres — no external call, immune to the free-tier limits.
        eod = await get_eod_change_pct(t)
        if eod is not None:
            return eod
        # 2. Fallback for not-yet-stored tickers: the live (rate-limited) path, which
        #    itself serves last-known-good when the upstream is throttled.
        try:
            info = await asyncio.wait_for(stock_service.get_stock_basic_info_async(t), timeout=8)
        except (asyncio.TimeoutError, Exception):
            info = None
        return info.get('changePercent') if isinstance(info, dict) else None

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


async def _get_reference_close(
    ticker: str,
    ref_date_str: str,
    db: Session,
) -> Optional[float]:
    """Return the closing price on or just before *ref_date_str*.

    Lookup order:
      1. PostgreSQL ``stock_daily_closes`` table (permanent, never expires)
      2. Redis cache (catches recent API results; 24 h TTL)
      3. External API (FinMind for TW, Massive for US) — result persisted to both DB + Redis
    """
    # --- 1. DB lookup (permanent store, 7-day window) ---
    window_start = (datetime.strptime(ref_date_str, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
    row = (
        db.query(StockDailyClose)
        .filter(
            StockDailyClose.ticker == ticker,
            StockDailyClose.date >= window_start,
            StockDailyClose.date <= ref_date_str,
        )
        .order_by(StockDailyClose.date.desc())
        .first()
    )
    if row is not None:
        return row.close

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

    # --- 3. External API (rate-limited) ---
    async with _ext_api_sem:
        loop = asyncio.get_event_loop()
        is_tw = ticker.split(".")[0].isdigit()
        start = (datetime.strptime(ref_date_str, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
        try:
            if is_tw:
                from src.services.finmind_service import FinMindAPIService
                svc = FinMindAPIService()
                rows = await loop.run_in_executor(
                    None, lambda: svc.list_daily_ticker_summary_range(ticker.split(".")[0], start, ref_date_str),
                )
            else:
                from src.services.massive_service import MassiveAPIService
                svc = MassiveAPIService()
                rows = await loop.run_in_executor(
                    None, lambda: svc.list_daily_ticker_summary_range(ticker, start, ref_date_str),
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
    try:
        existing = (
            db.query(StockDailyClose)
            .filter(StockDailyClose.ticker == ticker, StockDailyClose.date == actual_date)
            .first()
        )
        if not existing:
            db.add(StockDailyClose(ticker=ticker, date=actual_date, close=close))
            db.commit()
    except Exception:
        db.rollback()

    await cache_set(cache_key, str(close), CACHE_TTL["stock_history"])
    return close


@router.post("/batch-prices-since")
async def get_batch_prices_since(
    body: BatchPricesSinceRequest,
    db: Session = Depends(get_session),
):
    """Return % change from each ticker's reference date to its current price.

    Uses a DB-first strategy for historical closes to minimise external API calls.
    The full response is cached in Redis for 15 min.
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
    resp_cache_key = f"batch_since:{hashlib.md5(pairs_key.encode()).hexdigest()}"
    cached_resp = await cache_get(resp_cache_key)
    if cached_resp:
        try:
            return json.loads(cached_resp)
        except Exception:
            pass

    # Fetch reference closes (DB → Redis → API) and current prices concurrently.
    # 10s timeout per ticker to avoid hanging when external APIs are rate-limited.
    async def _ref_close_safe(t, d):
        try:
            return await asyncio.wait_for(_get_reference_close(t, d, db), timeout=10)
        except (asyncio.TimeoutError, Exception):
            return None

    async def _basic_safe(t):
        try:
            return await asyncio.wait_for(stock_service.get_stock_basic_info_async(t), timeout=10)
        except (asyncio.TimeoutError, Exception):
            return None

    ref_closes, basics = await asyncio.gather(
        asyncio.gather(*[_ref_close_safe(t, earliest[t]) for t in tickers]),
        asyncio.gather(*[_basic_safe(t) for t in tickers]),
    )
    out: dict[str, Optional[float]] = {}
    for ticker, ref_close, basic in zip(tickers, ref_closes, basics):
        if isinstance(ref_close, Exception) or isinstance(basic, Exception):
            out[ticker] = None
            continue
        current_price = basic.get("price") if isinstance(basic, dict) else None
        if ref_close and current_price and ref_close > 0:
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


async def _window_returns(
    ticker: str,
    reference_ms: int,
    current_price: Optional[float],
    db: Session,
) -> dict:
    """Forward 7/30/90D returns measured *from* the mention date, plus mention→now.

    ``dN`` = ``close@(mention + N calendar days) / baseline − 1``. A window is left
    ``None`` until it has fully elapsed (so the UI can render "—" like the competitor),
    or when a close is missing. Reuses ``_get_reference_close`` (DB → Redis → API), so
    after warm-up this costs no external calls.
    """
    result: dict[str, Optional[float]] = {
        "baseline": None, "d7": None, "d30": None, "d90": None, "since": None,
    }
    mention_dt = datetime.utcfromtimestamp(reference_ms / 1000)
    baseline = await _get_reference_close(ticker, mention_dt.strftime("%Y-%m-%d"), db)
    if not baseline or baseline <= 0:
        return result
    result["baseline"] = baseline

    now = datetime.utcnow()
    for n in WINDOW_DAYS:
        end_dt = mention_dt + timedelta(days=n)
        if end_dt > now:
            continue  # window not complete yet → leave None ("—")
        end_close = await _get_reference_close(ticker, end_dt.strftime("%Y-%m-%d"), db)
        if end_close and end_close > 0:
            result[f"d{n}"] = round((end_close - baseline) / baseline * 100, 2)

    if current_price and current_price > 0:
        result["since"] = round((current_price - baseline) / baseline * 100, 2)
    return result


@router.post("/batch-prices-windows")
async def get_batch_prices_windows(
    body: BatchPricesSinceRequest,
    db: Session = Depends(get_session),
):
    """Forward 7/30/90D (+ since) returns per *pick*, keyed by ``"{TICKER}:{reference_ms}"``.

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
    pairs_key = ",".join(f"{t}:{ms}" for t, ms in sorted(pairs))
    resp_cache_key = f"batch_windows:{hashlib.md5(pairs_key.encode()).hexdigest()}"
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
            return await asyncio.wait_for(_get_reference_close(t, today_str, db), timeout=12)
        except (asyncio.TimeoutError, Exception):
            return None

    latest_list = await asyncio.gather(*[_latest_close_safe(t) for t in distinct_tickers])
    latest = dict(zip(distinct_tickers, latest_list))

    async def _win_safe(t: str, ms: int) -> dict:
        try:
            return await asyncio.wait_for(_window_returns(t, ms, latest.get(t), db), timeout=15)
        except (asyncio.TimeoutError, Exception):
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

    rows = (
        db.query(StockTranslation)
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

