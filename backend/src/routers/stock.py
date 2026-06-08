"""
Stock API router
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from src.services.stock import StockService
from src.models.stock import CompanyDetail
from src.services.websocket_subscriber import WebSocketSubscriber
from src.database.postgres import get_session
from src.database.models import StockTranslation
from src.utils.market import infer_market
from src.cache.redis_client import cache_get, cache_set
from src.cache.cache_config import CACHE_TTL

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stocks", tags=["stocks"])

# Initialize service
stock_service = StockService()


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
    Uses the same per-ticker Redis cache as /{ticker}/basic.
    Returns {TICKER: changePercent} — null if not found.
    """
    ticker_list = [t.strip().upper() for t in tickers.split(',') if t.strip()][:100]
    if not ticker_list:
        return {}
    results = await asyncio.gather(
        *[stock_service.get_stock_basic_info_async(t) for t in ticker_list],
        return_exceptions=True,
    )
    return {
        ticker: (info.get('changePercent') if isinstance(info, dict) else None)
        for ticker, info in zip(ticker_list, results)
    }


class TickerDatePair(BaseModel):
    ticker: str
    reference_ms: int = Field(..., description="Episode release timestamp (Unix ms)")


class BatchPricesSinceRequest(BaseModel):
    items: list[TickerDatePair] = Field(..., max_length=100)


async def _get_reference_close(ticker: str, ref_date_str: str) -> Optional[float]:
    """Fetch the closing price on or just before `ref_date_str` for a single ticker.

    Tries a 7-day window ending on ref_date to account for weekends/holidays.
    Caches the result for 24 h since historical prices don't change.
    """
    cache_key = f"stock:{ticker}:close:{ref_date_str}"
    cached = await cache_get(cache_key)
    if cached is not None:
        try:
            return float(cached)
        except (ValueError, TypeError):
            pass
    loop = asyncio.get_event_loop()
    is_tw = ticker.split(".")[0].isdigit()
    if is_tw:
        from src.services.finmind_service import FinMindAPIService
        svc = FinMindAPIService()
        start = (datetime.strptime(ref_date_str, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
        rows = await loop.run_in_executor(None, lambda: svc.list_daily_ticker_summary_range(ticker.split(".")[0], start, ref_date_str))
    else:
        from src.services.massive_service import MassiveAPIService
        svc = MassiveAPIService()
        start = (datetime.strptime(ref_date_str, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
        rows = await loop.run_in_executor(None, lambda: svc.list_daily_ticker_summary_range(ticker, start, ref_date_str))
    if not rows:
        return None
    close = rows[-1].get("close")
    if close is not None:
        await cache_set(cache_key, str(close), CACHE_TTL["stock_history"])
    return close


@router.post("/batch-prices-since")
async def get_batch_prices_since(body: BatchPricesSinceRequest):
    """Return % change from each ticker's reference date to its current price.

    Used by episode cards to show "price change since episode aired" instead of
    today's intraday change.  Returns ``{TICKER: changePercent}`` — ``null`` when
    historical data is unavailable.
    """
    # Deduplicate: same ticker may appear in multiple episodes; pick earliest date
    earliest: dict[str, str] = {}
    for item in body.items:
        t = item.ticker.upper()
        d = datetime.utcfromtimestamp(item.reference_ms / 1000).strftime("%Y-%m-%d")
        if t not in earliest or d < earliest[t]:
            earliest[t] = d
    tickers = list(earliest.keys())
    if not tickers:
        return {}
    ref_closes, basics = await asyncio.gather(
        asyncio.gather(*[_get_reference_close(t, earliest[t]) for t in tickers], return_exceptions=True),
        asyncio.gather(*[stock_service.get_stock_basic_info_async(t) for t in tickers], return_exceptions=True),
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
    ticker_list = [t.strip().upper() for t in tickers.split(',') if t.strip()][:100]
    if not ticker_list:
        return []

    # Fetch brand colors from translations table (one query)
    translations = db.query(StockTranslation).filter(
        StockTranslation.ticker.in_(ticker_list)
    ).all()
    brand_colors: dict[str, str] = {
        t.ticker: t.brand_color for t in translations if t.brand_color
    }

    basic_results = await asyncio.gather(
        *[stock_service.get_stock_basic_info_async(t) for t in ticker_list],
        return_exceptions=True,
    )

    out = []
    for ticker, info in zip(ticker_list, basic_results):
        market = infer_market(ticker)
        name = info.get("name") if isinstance(info, dict) else None
        out.append({
            "ticker": ticker,
            "name": name or ticker,
            "market": market,
            "brand_color": brand_colors.get(ticker),
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



