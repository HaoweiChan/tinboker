"""
Stock service for managing stock data
Always fetches from Massive API (with mock data fallback), never from database.
Database is only used for graph/news relationships.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
import time
import json
import logging
from src.services.data_collection_service import DataCollectionService
from src.models.stock import CompanyDetail, ChartDataPoint
from src.schemas.search import SearchResultItem
from src.cache.redis_client import cache_get, cache_set, cache_delete, cache_delete_pattern
from src.cache.cache_config import CACHE_TTL

logger = logging.getLogger(__name__)

# Long-lived "last known good" copy, served when the upstream API is rate-limited
# (FinMind's free tier is per-IP capped at ~300 req/hr, so heavy hours exhaust it).
# Serving a stale price beats a 404/blank card.
_STALE_TTL = 60 * 60 * 24 * 7  # 7 days


class StockService:
    """Service for stock operations - always uses Massive API"""
    
    def __init__(self, data_collection_service: Optional[DataCollectionService] = None):
        """
        Initialize stock service
        
        Args:
            data_collection_service: Optional data collection service for external API calls
        """
        self.data_collection_service = data_collection_service or DataCollectionService()
    
    def get_stock_info(self, ticker: str) -> Optional[CompanyDetail]:
        """
        Get stock information from Massive API (with mock data fallback)
        Synchronous version - calls async version internally
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            CompanyDetail object or None if not found
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.get_stock_info_async(ticker))
        except RuntimeError:
            return asyncio.run(self.get_stock_info_async(ticker))
    
    async def get_stock_info_async(self, ticker: str, timeframe: Optional[str] = None, before: Optional[int] = None) -> Optional[CompanyDetail]:
        """
        Get stock information from Massive API (with mock data fallback) with caching
        
        Args:
            ticker: Stock ticker symbol
            timeframe: Optional timeframe filter (1H, 1D, 1W, 1M, 3M, 6M, 1Y, YTD, ALL)
            before: Optional Unix timestamp (ms). Fetch data ending before this time for infinite scroll.
            
        Returns:
            CompanyDetail object or None if not found
        """
        # Include timeframe in cache key
        # For 1H, we fetch minute data, so differentiate in cache key
        timeframe_key = timeframe or 'ALL'
        granularity = 'minute' if timeframe in ['1H'] else 'daily'
        cache_key = f"stock:{ticker.upper()}:info:{timeframe_key}:{granularity}:v3"
        
        # Skip cache if 'before' is provided (pagination request for older data)
        if not before:
            # Check cache first
            cached = await cache_get(cache_key)
            if cached:
                try:
                    data = json.loads(cached)
                    return CompanyDetail(**data)
                except Exception:
                    pass  # If deserialization fails, fetch fresh data
        
        # Cache miss or pagination request - fetch from external API
        # Pass timeframe and before to data collection for appropriate granularity
        
        # Offload synchronous blocking call to thread pool
        import asyncio
        loop = asyncio.get_event_loop()
        stock_data = await loop.run_in_executor(
            None, 
            lambda: self.data_collection_service.collect_stock_data(ticker, timeframe=timeframe, before=before)
        )
        
        if stock_data:
            # Convert to CompanyDetail format
            result = self._convert_stock_to_company_detail(stock_data)

            # Apply timeframe filtering if provided (for non-standard timeframes that need date filtering)
            # 1H is handled by minute fetch
            # 1D, 1W, 1M are handled by aggregate fetch with specific lookbacks
            if result and timeframe and timeframe not in ['1H', '1D', '1W', '1M']:
                from src.utils.timeframe import filter_chart_data_by_timeframe
                try:
                    # CPU-bound but fast, can stay in main thread or offload too if heavy
                    result.chartData = filter_chart_data_by_timeframe(result.chartData, timeframe)
                except ValueError as e:
                    # Invalid timeframe - log and return unfiltered data
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Invalid timeframe '{timeframe}': {e}. Returning unfiltered data.")
            
            # Pagination requests fetch older chart data — return as-is, never cached.
            if before:
                return result

            # Only treat this as a usable result when we actually got a price. A 0/None
            # price means the snapshot/history fetch failed (only the static ticker
            # details came through) — caching that would mask the real price for a full
            # TTL, so fall through to the last known-good (stale) copy instead.
            if result and (result.price or 0) > 0:
                try:
                    payload = json.dumps(result.dict(), default=str)
                    await cache_set(cache_key, payload, CACHE_TTL["stock_info"])
                    # Long-lived stale copy: served when the upstream is rate-limited
                    # (FinMind free tier is per-IP capped ~300/hr) so prices still render.
                    await cache_set(f"{cache_key}:stale", payload, _STALE_TTL)
                except Exception:
                    pass  # Cache failure shouldn't break the request
                return result

        # Upstream returned nothing usable (rate-limited / no price). Serve the last
        # known-good value rather than 404 / a price-less blank.
        if not before:
            stale = await cache_get(f"{cache_key}:stale")
            if stale:
                try:
                    return CompanyDetail(**json.loads(stale))
                except Exception:
                    pass
        return None
    
    
    def get_stock_basic_info(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get basic stock information from Massive API (no chart data)
        Synchronous version - calls async version internally
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Dict with basic stock info or None
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.get_stock_basic_info_async(ticker))
        except RuntimeError:
            return asyncio.run(self.get_stock_basic_info_async(ticker))
    
    async def get_stock_basic_info_async(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get basic stock information from Massive API (no chart data) with caching
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Dict with basic stock info or None
        """
        cache_key = f"stock:{ticker.upper()}:basic"
        
        # Check cache first
        cached = await cache_get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass  # If deserialization fails, fetch fresh data
        
        # Cache miss - fetch from external API
        import asyncio
        loop = asyncio.get_event_loop()
        stock_data = await loop.run_in_executor(
            None, 
            lambda: self.data_collection_service.collect_stock_data(ticker)
        )
        if stock_data:
            result = {
                "ticker": stock_data.stock_id,
                "name": stock_data.metadata.stock_name,
                "price": stock_data.price or 0.0,
                # Keep change/changePercent honest: None (not 0.0) when the day-over-day
                # change couldn't be computed (e.g. <2 days of history). batch-prices then
                # returns null so the card shows no badge, instead of a misleading "0.00%".
                "change": stock_data.change,
                "changePercent": stock_data.changePercent,
                "marketCap": stock_data.marketCap or 0,
                "revenue": stock_data.revenue or 0,
                "pe": stock_data.pe or 0.0,
                "dividendYield": stock_data.dividendYield or 0.0,
                "about": stock_data.about or "",
                "stats": {
                    "volume": stock_data.stats.volume if stock_data.stats else 0,
                    "beta": stock_data.stats.beta if stock_data.stats else 0.0,
                    "volatility": stock_data.stats.volatility if stock_data.stats else 0.0,
                }
            }
            
            # Only cache/return when we actually got a price. price=0 means the
            # snapshot/history fetch failed (details alone came through) — caching it
            # would serve a "$0 / 0.00%" card for a full TTL, so fall through to stale.
            if (result.get("price") or 0) > 0:
                try:
                    payload = json.dumps(result, default=str)
                    await cache_set(cache_key, payload, CACHE_TTL["stock_basic"])
                    await cache_set(f"{cache_key}:stale", payload, _STALE_TTL)
                except Exception:
                    pass  # Cache failure shouldn't break the request
                return result

        # No usable price (rate-limited / failed fetch) — serve the last known-good value.
        stale = await cache_get(f"{cache_key}:stale")
        if stale:
            try:
                return json.loads(stale)
            except Exception:
                pass
        return None
    
    
    def get_sorted_stocks(self, sort_by: str = "ticker", limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get sorted stocks list from Massive API
        Synchronous version - calls async version internally
        
        Args:
            sort_by: Sort field (ticker, name, price, change_percent, market_cap)
            limit: Maximum number of stocks to return (default: 50, max: 200)
            
        Returns:
            List of stock dictionaries
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.get_sorted_stocks_async(sort_by=sort_by, limit=limit))
        except RuntimeError:
            return asyncio.run(self.get_sorted_stocks_async(sort_by=sort_by, limit=limit))
    
    async def get_sorted_stocks_async(self, sort_by: str = "ticker", limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get sorted stocks list from Massive API with caching
        
        Args:
            sort_by: Sort field (ticker, name, price, change_percent, market_cap)
            limit: Maximum number of stocks to return (default: 50, max: 200)
            
        Returns:
            List of stock dictionaries
        """
        cache_key = f"stock:list:{sort_by}:{limit}:v3"
        
        # Check cache first
        cached = await cache_get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass  # If deserialization fails, fetch fresh data
        
        # Cache miss - fetch from external API
        stocks_data = self.data_collection_service.get_all_stocks(limit=limit)
        
        # Convert to dict format
        stocks_list = []
        for stock_data in stocks_data:
            stocks_list.append({
                "ticker": stock_data.stock_id,
                "name": stock_data.metadata.stock_name,
                "price": stock_data.price,
                "change": stock_data.change,
                "change_percent": stock_data.changePercent,
                "market_cap": stock_data.marketCap,
                "revenue": stock_data.revenue,
                "pe": stock_data.pe,
                "dividend_yield": stock_data.dividendYield,
                "about": stock_data.about,
                "volume": stock_data.stats.volume if stock_data.stats else 0,
                "beta": stock_data.stats.beta if stock_data.stats else 0.0,
                "volatility": stock_data.stats.volatility if stock_data.stats else 0.0,
                "updated_at": datetime.now().isoformat(),
            })
        
        # Sort the list
        sort_key_map = {
            "ticker": lambda x: x["ticker"],
            "name": lambda x: x["name"],
            "price": lambda x: x["price"] or 0,
            "change_percent": lambda x: x["change_percent"] or 0,
            "market_cap": lambda x: x["market_cap"] or 0,
        }
        
        sort_key = sort_key_map.get(sort_by, sort_key_map["ticker"])
        stocks_list.sort(key=sort_key)
        
        # Store in cache
        try:
            await cache_set(
                cache_key,
                json.dumps(stocks_list, default=str),
                CACHE_TTL["stock_list"]
            )
        except Exception:
            pass  # Cache failure shouldn't break the request
        
        return stocks_list
    
    
    async def invalidate_stock_cache(self, ticker: str) -> None:
        """
        Invalidate cache for a specific stock
        
        Args:
            ticker: Stock ticker symbol
        """
        ticker_upper = ticker.upper()
        await cache_delete(f"stock:{ticker_upper}:info")
        await cache_delete(f"stock:{ticker_upper}:basic")
        await cache_delete_pattern("stock:list:*")
    
    def update_stock_price(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Update stock price from Massive API
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Updated price data dict or None if error
        """
        snapshot = self.data_collection_service.update_stock_price(ticker)
        return snapshot
    
    def get_ohlcv_data(
        self,
        ticker: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[ChartDataPoint]:
        """
        Get historical OHLCV data from Massive API
        
        Args:
            ticker: Stock ticker symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            limit: Maximum number of records
            
        Returns:
            List of ChartDataPoint objects
        """
        # Fetch stock data which includes historical prices
        stock_data = self.data_collection_service.collect_stock_data(ticker)
        if not stock_data or not stock_data.stock_price_history:
            return []
        
        # Convert to ChartDataPoint list
        chart_data = []
        for record in stock_data.stock_price_history.day:
            timestamp = record.timestamp if hasattr(record, 'timestamp') else int(
                datetime.strptime(record.date, "%Y-%m-%d").timestamp() * 1000
            )
            chart_data.append(ChartDataPoint(
                timestamp=timestamp,
                price=record.close,
                date=record.date,
                open=record.open,
                high=record.max,
                low=record.min,
                close=record.close,
                volume=record.Trading_Volume,
            ))
        
        # Apply filters
        if start_date:
            chart_data = [p for p in chart_data if p.date >= start_date]
        if end_date:
            chart_data = [p for p in chart_data if p.date <= end_date]
        if limit:
            chart_data = chart_data[:limit]
        
        return chart_data
    
    def stream_ohlcv_updates(self, ticker: str):
        """
        Generator for WebSocket streaming of OHLCV updates
        Generates mock real-time data for demonstration
        
        Args:
            ticker: Stock ticker symbol
            
        Yields:
            ChartDataPoint objects as updates arrive
        """
        # Get initial stock data to have a baseline price
        stock_data = self.data_collection_service.collect_stock_data(ticker)
        if not stock_data:
            return
        
        base_price = stock_data.price or 100.0
        
        # In a real implementation, this would subscribe to Massive API WebSocket or Redis pub/sub
        # For now, generate mock real-time updates
        # TODO: Implement Redis pub/sub for real-time updates
        import random
        
        while True:
            # Generate realistic price movement
            change_percent = random.uniform(-0.5, 0.5) / 100  # -0.5% to +0.5%
            new_price = base_price * (1 + change_percent)
            
            # Generate OHLCV data point
            open_price = base_price
            high_price = max(open_price, new_price) * random.uniform(1.0, 1.002)
            low_price = min(open_price, new_price) * random.uniform(0.998, 1.0)
            close_price = new_price
            volume = random.randint(100000, 1000000)
            
            timestamp = int(datetime.now().timestamp() * 1000)
            date = datetime.now().strftime("%Y-%m-%d")
            
            yield ChartDataPoint(
                timestamp=timestamp,
                price=close_price,
                date=date,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
            )
            
            # Update base price for next iteration
            base_price = new_price
            
            # Wait before next update
            time.sleep(5)  # Send update every 5 seconds
    
    def _convert_stock_to_company_detail(self, stock_data) -> CompanyDetail:
        """Helper to convert Stock object to CompanyDetail"""
        from src.models.stock import StockStats
        
        # Convert price history to chart data
        # Works for both daily and minute-level data (both stored in .day list)
        chart_data = []
        if stock_data.stock_price_history and stock_data.stock_price_history.day:
            for record in stock_data.stock_price_history.day:
                # Use timestamp if available (minute data has precise timestamps)
                # Otherwise calculate from date string (daily data)
                if record.timestamp:
                    timestamp = record.timestamp
                else:
                    timestamp = int(datetime.strptime(record.date, "%Y-%m-%d").timestamp() * 1000)
                
                chart_data.append(ChartDataPoint(
                    timestamp=timestamp,
                    price=record.close,
                    date=record.date,  # Date portion (YYYY-MM-DD) - works for both daily and minute data
                    open=record.open,
                    high=record.max,
                    low=record.min,
                    close=record.close,
                    volume=record.Trading_Volume,
                ))
        
        stats = StockStats(
            volume=stock_data.stats.volume if stock_data.stats else 0,
            beta=stock_data.stats.beta if stock_data.stats else 0.0,
            volatility=stock_data.stats.volatility if stock_data.stats else 0.0,
        )
        
        # Get image data from appropriate API
        # FinMind doesn't provide images, so skip for Taiwan stocks
        icon_url = None
        logo_url = None
        icon_image = None
        logo_image = None
        
        # Check if this is a Taiwan stock (numeric ticker)
        is_taiwan_stock = stock_data.stock_id.isdigit()
        
        if not is_taiwan_stock:
            # US stock - try to get images from Massive API
            try:
                details = self.data_collection_service.massive_service.get_ticker_details(stock_data.stock_id)
                if details:
                    icon_url = details.get("icon_url")
                    logo_url = details.get("logo_url")
                    icon_image = details.get("icon_image")
                    logo_image = details.get("logo_image")
                    logger.debug(f"Fetched image data for {stock_data.stock_id}: icon={bool(icon_image)}, logo={bool(logo_image)}")
            except Exception as e:
                logger.warning(f"Could not fetch image data for {stock_data.stock_id}: {e}")
        else:
            # Taiwan stock - FinMind doesn't provide images
            logger.debug(f"Skipping image fetch for Taiwan stock {stock_data.stock_id} (not available in FinMind)")
        
        return CompanyDetail(
            ticker=stock_data.stock_id,
            name=stock_data.metadata.stock_name,
            price=stock_data.price or 0.0,
            change=stock_data.change or 0.0,
            changePercent=stock_data.changePercent or 0.0,
            marketCap=stock_data.marketCap or 0,
            revenue=stock_data.revenue or 0,
            pe=stock_data.pe or 0.0,
            dividendYield=stock_data.dividendYield or 0.0,
            about=stock_data.about or "",
            stats=stats,
            chartData=chart_data,
            icon_url=icon_url,
            logo_url=logo_url,
            icon_image=icon_image,
            logo_image=logo_image,
        )

    async def search_stocks(self, query: str, limit: int = 5) -> List[SearchResultItem]:
        """
        Search stocks by ticker or name

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of SearchResultItem objects
        """
        # Get all stocks (using a large limit to cache mostly everything)
        # We use 1000 as a reasonable upper bound for "all interesting stocks"
        all_stocks = await self.get_sorted_stocks_async(limit=1000)

        query_lower = query.lower()
        results = []
        for stock in all_stocks:
            ticker = stock.get("ticker", "")
            name = stock.get("name", "")
            if query_lower not in ticker.lower() and query_lower not in name.lower():
                continue
            market = "TW" if ticker.split(".")[0].isdigit() else "US"
            results.append(SearchResultItem(
                id=f"stock-{ticker}",
                type="stock",
                title=ticker,
                subtitle=name,
                link=f"/stock/{ticker}",
                market=market,
                metadata={
                    "price": stock.get("price"),
                    "change_percent": stock.get("change_percent")
                }
            ))
            if len(results) >= limit:
                break
        return results

