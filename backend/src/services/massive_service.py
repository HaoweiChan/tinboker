"""
Massive API service wrapper.

This module provides a wrapper around the Massive API client with:
- Error handling and fallback mechanisms
- Data transformation to Pydantic models
- Rate limiting support
"""

import logging
import os
import time
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from massive import RESTClient
from src.config import settings
import requests
import base64

logger = logging.getLogger(__name__)

# In-process cache for company branding images (base64). The image URLs are authenticated
# (need the Massive key), so the frontend can't load them directly — they're fetched +
# base64-encoded server-side. They were being re-fetched on EVERY ticker-details call,
# which burned the Massive rate limit and made the real price/data calls 429. Company
# logos are static, so cache hits permanently; cache misses are negatively cached briefly
# so a rate-limited (429) image isn't retried on every request (which would keep the quota
# pinned and starve price data). {url: (b64_or_None, expires_at_or_None)}.
_IMG_CACHE: dict = {}
_IMG_CACHE_MAX = 4000
_IMG_FAIL_TTL = 600  # seconds to skip a URL after a failed fetch (e.g. 429)

# Massive (Polygon) free tier is ~5 requests/min PER KEY (per-key, not per-IP), so a pool
# of keys genuinely multiplies the ceiling. We track a per-key per-minute budget in-process
# and hand out the first key with remaining budget for each SDK call — load-balancing across
# keys. A key that 429s anyway just raises (caller serves stale); the next call rotates.
_MASSIVE_PER_MIN = int(os.getenv("MASSIVE_PER_MIN_LIMIT", "5"))
_minute_counts: dict = {}  # key_id -> [minute, count]


def _consume_minute(key_id: str) -> bool:
    minute = int(time.time() // 60)
    entry = _minute_counts.get(key_id)
    if entry is None or entry[0] != minute:
        entry = [minute, 0]
        _minute_counts[key_id] = entry
    entry[1] += 1
    return entry[1] <= _MASSIVE_PER_MIN


class MassiveAPIError(Exception):
    """Custom exception for Massive API errors."""
    pass


class MassiveAPIService:
    """Service wrapper for Massive API."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Massive API service.
        
        Args:
            api_key: Massive API key. If None, reads from MASSIVE_API_KEY env var
        """
        # Pool of keys (Massive/Polygon limits per key, so a pool multiplies the ceiling).
        # An explicitly-passed key wins; otherwise use the configured pool.
        pool = [api_key] if api_key else settings.massive_api_key_pool
        # First key is also used for the (cached) branding-image auth header.
        self.api_key = pool[0] if pool else None
        self._clients = []  # list of (key_id, RESTClient)
        for i, key in enumerate(pool):
            try:
                self._clients.append((str(i), RESTClient(key)))
            except Exception as e:
                logger.error(f"Failed to initialize Massive API client #{i}: {e}")
        if not self._clients:
            logger.warning("Massive API key not configured. API calls will fail.")
        elif len(self._clients) > 1:
            logger.info(f"Massive: rotating across {len(self._clients)} keys (~{_MASSIVE_PER_MIN}/min each).")

    @property
    def client(self):
        """A RESTClient for a key with remaining per-minute budget (rotates/load-balances).

        Accessing this consumes one unit of the chosen key's minute budget, so every
        existing ``self.client.xxx()`` call automatically spreads across the pool. When all
        keys are spent for the current minute, returns the first client anyway (it may 429,
        and the caller degrades to cached/stale data).
        """
        if not self._clients:
            return None
        for key_id, cl in self._clients:
            if _consume_minute(key_id):
                return cl
        return self._clients[0][1]

    def _check_client(self) -> None:
        """Check that at least one client is configured."""
        if not self._clients:
            raise MassiveAPIError("Massive API client not initialized. Check API key configuration.")

    def _fetch_image_b64(self, url: Optional[str]) -> Optional[str]:
        """Fetch a branding image as base64, cached in-process.

        Successes are cached for the process lifetime (logos are static); failures are
        negatively cached for _IMG_FAIL_TTL so a rate-limited image isn't re-requested on
        every call (which would keep Massive's quota pinned and starve price data).
        """
        if not url:
            return None
        now = time.time()
        hit = _IMG_CACHE.get(url)
        if hit is not None:
            b64, expires_at = hit
            if expires_at is None or now < expires_at:
                return b64  # cached success (no expiry) or still-valid negative cache (None)

        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            b64 = base64.b64encode(response.content).decode("utf-8")
            if len(_IMG_CACHE) < _IMG_CACHE_MAX:
                _IMG_CACHE[url] = (b64, None)  # cache static image for the process lifetime
            return b64
        except Exception as e:
            logger.warning(f"Error fetching branding image {url}: {e}")
            if len(_IMG_CACHE) < _IMG_CACHE_MAX:
                _IMG_CACHE[url] = (None, now + _IMG_FAIL_TTL)  # back off; don't retry every call
            return None
    
    def get_ticker_details(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get ticker details from Massive API.
        
        Args:
            ticker: Stock ticker symbol (e.g., "NVDA", "AAPL")
            
        Returns:
            Ticker details dict or None if error/not found
        """
        try:
            self._check_client()
            details = self.client.get_ticker_details(ticker)
            if details:
                # Extract branding information (icon and logo URLs)
                icon_url = None
                logo_url = None
                branding = getattr(details, 'branding', None)
                if branding:
                    icon_url = getattr(branding, 'icon_url', None)  # PNG format
                    logo_url = getattr(branding, 'logo_url', None)   # SVG format
                
                # Fetch branding images (base64), cached in-process — see _fetch_image_b64.
                icon_image = self._fetch_image_b64(icon_url)
                logo_image = self._fetch_image_b64(logo_url)

                return {
                    "ticker": details.ticker,
                    "name": details.name,
                    "market_cap": details.market_cap,
                    "description": details.description or "",
                    "currency": details.currency_name or "USD",
                    "industry": getattr(details, 'sic_description', None),
                    "shares_outstanding": getattr(details, 'weighted_shares_outstanding', None),
                    "icon_url": icon_url,
                    "logo_url": logo_url,
                    "icon_image": icon_image,  # Base64 encoded PNG
                    "logo_image": logo_image,  # Base64 encoded SVG
                }
        except Exception as e:
            logger.error(f"Error fetching ticker details for {ticker}: {e}")
            return None
    
    def get_ticker_snapshot(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get latest ticker snapshot (real-time OHLCV).
        Uses most recent day's data from aggregates.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Snapshot dict with latest price data or None if error
        """
        try:
            self._check_client()
            # Get the most recent day's data from aggregates
            # Try last 5 days to find the most recent trading day
            to_date = datetime.now().strftime("%Y-%m-%d")
            from_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
            
            # Get daily aggregates and take the most recent one
            aggregates = list(self.client.list_aggs(
                ticker=ticker,
                multiplier=1,
                timespan='day',
                from_=from_date,
                to=to_date,
                limit=5,
                sort='desc'  # Most recent first
            ))
            
            if aggregates and len(aggregates) > 0:
                bar = aggregates[0]  # Most recent bar
                return {
                    "ticker": ticker,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "price": bar.close,  # Use close as current price
                    "volume": getattr(bar, 'volume', 0),
                }
            return None
        except Exception as e:
            logger.error(f"Error fetching ticker snapshot for {ticker}: {e}")
            return None
    
    def list_daily_ticker_summary(self, ticker: str, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get daily ticker summary (OHLC) for a specific date.
        
        Args:
            ticker: Stock ticker symbol
            date: Date in YYYY-MM-DD format. If None, uses today
            
        Returns:
            List of daily summary dicts
        """
        try:
            self._check_client()
            if date is None:
                date = datetime.now().strftime("%Y-%m-%d")
            
            summaries = []
            # Use list_aggs with timespan='day' to get daily OHLCV data
            for agg in self.client.list_aggs(
                ticker=ticker,
                multiplier=1,
                timespan='day',
                from_=date,
                to=date,
                limit=1
            ):
                # Convert timestamp to date string
                agg_date = date
                if hasattr(agg, 'timestamp'):
                    try:
                        agg_date = datetime.fromtimestamp(agg.timestamp / 1000).strftime("%Y-%m-%d")
                    except:
                        pass
                
                summaries.append({
                    "date": agg_date,
                    "open": agg.open,
                    "high": agg.high,
                    "low": agg.low,
                    "close": agg.close,
                    "volume": getattr(agg, 'volume', 0),
                })
            return summaries
        except Exception as e:
            logger.error(f"Error fetching daily summary for {ticker} on {date}: {e}")
            return []
    
    def list_daily_ticker_summary_range(self, ticker: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """Get daily OHLCV bars for a date range, sorted by date ascending."""
        try:
            self._check_client()
            summaries = []
            for agg in self.client.list_aggs(
                ticker=ticker, multiplier=1, timespan='day',
                from_=start_date, to=end_date, limit=50, sort='asc',
            ):
                agg_date = end_date
                if hasattr(agg, 'timestamp'):
                    try:
                        agg_date = datetime.fromtimestamp(agg.timestamp / 1000).strftime("%Y-%m-%d")
                    except Exception:
                        pass
                summaries.append({
                    "date": agg_date,
                    "open": agg.open,
                    "high": agg.high,
                    "low": agg.low,
                    "close": agg.close,
                    "volume": getattr(agg, 'volume', 0),
                })
            return summaries
        except Exception as e:
            logger.error(f"Error fetching daily range for {ticker} ({start_date}–{end_date}): {e}")
            return []

    def list_financials_income_statements(self, ticker: str) -> List[Dict[str, Any]]:
        """
        Get income statements for a ticker.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            List of income statement dicts
        """
        try:
            self._check_client()
            statements = []
            for stmt in self.client.list_financials_income_statements(tickers=ticker, limit=10):
                statements.append({
                    "period_end": stmt.period_end,
                    "fiscal_year": stmt.fiscal_year,
                    "fiscal_quarter": getattr(stmt, 'fiscal_quarter', None),
                    "revenue": stmt.data.revenue if stmt.data else None,
                    "net_income": stmt.data.net_income if stmt.data else None,
                })
            return statements
        except Exception as e:
            error_str = str(e)
            # Financials data requires higher tier plan - log at debug level instead of error
            if "NOT_AUTHORIZED" in error_str or "not entitled" in error_str.lower():
                logger.debug(f"Financials data not available for {ticker} (requires higher plan): {e}")
            else:
                logger.warning(f"Error fetching income statements for {ticker}: {e}")
            return []
    
    def list_financials_ratios(self, ticker: str) -> List[Dict[str, Any]]:
        """
        Get financial ratios for a ticker.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            List of ratio dicts
        """
        try:
            self._check_client()
            ratios = []
            for ratio in self.client.list_financials_ratios(ticker=ticker, limit=1):
                if ratio.data:
                    ratios.append({
                        "calculation_date": ratio.calculation_date,
                        "pe_ratio": ratio.data.pe_ratio,
                        "dividend_yield": getattr(ratio.data, 'dividend_yield', None),
                    })
            return ratios
        except Exception as e:
            error_str = str(e)
            # Financials data requires higher tier plan - log at debug level instead of error
            if "NOT_AUTHORIZED" in error_str or "not entitled" in error_str.lower():
                logger.debug(f"Financials ratios not available for {ticker} (requires higher plan): {e}")
            else:
                logger.warning(f"Error fetching ratios for {ticker}: {e}")
            return []
    
    def list_top_movers(self, direction: str = "gainers") -> List[Dict[str, Any]]:
        """
        Get top market movers.
        Note: Massive API doesn't have a direct top movers endpoint in Starter plan.
        Returns empty list as this feature may not be available.
        
        Args:
            direction: "gainers" or "losers"
            
        Returns:
            List of top mover dicts (empty if not available)
        """
        try:
            self._check_client()
            # Massive API Starter plan doesn't have list_top_movers endpoint
            # Would need to calculate from aggregates data
            logger.warning("Top movers endpoint not available in Massive API Starter plan")
            return []
        except Exception as e:
            logger.error(f"Error fetching top movers ({direction}): {e}")
            return []
    
    def list_tickers(self, market: str = "stocks", active: bool = True, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        List all available tickers.
        
        Args:
            market: Market type (e.g., "stocks")
            active: Only return active tickers
            limit: Maximum number of tickers to return (max 1000)
            
        Returns:
            List of ticker metadata dicts
        """
        try:
            self._check_client()
            tickers = []
            # Massive API expects limit as int, max 1000
            actual_limit = min(limit, 1000)
            
            # Add timeout protection using threading
            import threading
            import queue
            
            result_queue = queue.Queue()
            exception_queue = queue.Queue()
            
            def fetch_tickers():
                try:
                    ticker_list = []
                    count = 0
                    for ticker in self.client.list_tickers(
                        market=market, 
                        active=str(active).lower(), 
                        limit=actual_limit
                    ):
                        if count >= actual_limit:
                            break
                        ticker_list.append({
                            "ticker": ticker.ticker,
                            "name": ticker.name,
                            "market": ticker.market,
                            "currency": ticker.currency_name,
                            "active": ticker.active,
                        })
                        count += 1
                    result_queue.put(ticker_list)
                except Exception as e:
                    exception_queue.put(e)
            
            # Start thread with timeout
            thread = threading.Thread(target=fetch_tickers, daemon=True)
            thread.start()
            thread.join(timeout=0.5)  # 0.5 second timeout
            
            if thread.is_alive():
                logger.warning("list_tickers timed out after 0.5 seconds")
                return []  # Return empty list on timeout
            
            # Check for exceptions
            if not exception_queue.empty():
                raise exception_queue.get()
            
            # Get results
            if not result_queue.empty():
                return result_queue.get()
            
            return []
        except Exception as e:
            logger.error(f"Error listing tickers: {e}")
            return []
    
    def list_news(self, ticker: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get news articles for a ticker.
        
        Args:
            ticker: Stock ticker symbol
            limit: Maximum number of articles to return
            
        Returns:
            List of news article dicts
        """
        try:
            self._check_client()
            logger.info(f"Fetching news for {ticker} with limit {limit}")
            articles = []
            
            # list_ticker_news returns an iterator - convert to list
            # Note: The iterator may block on HTTP requests, so this should be run in executor
            try:
                news_iter = self.client.list_ticker_news(ticker=ticker, limit=limit)
                logger.info(f"Got news iterator for {ticker}, starting iteration...")
                
                count = 0
                # Use next() with default to avoid infinite iteration
                try:
                    while count < limit:
                        article = next(news_iter, None)
                        if article is None:
                            break
                        
                        try:
                            # Extract all available fields
                            article_dict = {
                                "id": getattr(article, 'id', None),
                                "title": getattr(article, 'title', ''),
                                "description": getattr(article, 'description', getattr(article, 'title', '')),
                                "published_utc": getattr(article, 'published_utc', None),
                                "article_url": getattr(article, 'article_url', None),
                                "content": getattr(article, 'content', None),
                                "author": getattr(article, 'author', None),
                                "image_url": getattr(article, 'image_url', None),
                                "amp_url": getattr(article, 'amp_url', None),
                            }
                            
                            # Extract tickers list (important - contains all related tickers)
                            tickers = getattr(article, 'tickers', None)
                            if tickers:
                                article_dict["tickers"] = list(tickers) if isinstance(tickers, (list, tuple)) else [tickers]
                            else:
                                article_dict["tickers"] = []
                            
                            # Extract keywords list
                            keywords = getattr(article, 'keywords', None)
                            if keywords:
                                article_dict["keywords"] = list(keywords) if isinstance(keywords, (list, tuple)) else [keywords]
                            else:
                                article_dict["keywords"] = []
                            
                            # Extract publisher information
                            publisher = getattr(article, 'publisher', None)
                            if publisher:
                                article_dict["publisher"] = {
                                    "name": getattr(publisher, 'name', None),
                                    "homepage_url": getattr(publisher, 'homepage_url', None),
                                    "favicon_url": getattr(publisher, 'favicon_url', None),
                                    "logo_url": getattr(publisher, 'logo_url', None),
                                }
                            else:
                                article_dict["publisher"] = None
                            
                            # Extract insights (sentiment analysis)
                            insights = getattr(article, 'insights', None)
                            if insights:
                                insights_list = []
                                for insight in insights:
                                    insights_list.append({
                                        "sentiment": getattr(insight, 'sentiment', None),
                                        "sentiment_reasoning": getattr(insight, 'sentiment_reasoning', None),
                                    })
                                article_dict["insights"] = insights_list
                            else:
                                article_dict["insights"] = []
                            
                            articles.append(article_dict)
                            count += 1
                            logger.debug(f"Processed article {count}/{limit}")
                        except Exception as e:
                            logger.warning(f"Error processing article {count}: {e}")
                            continue
                except StopIteration:
                    # Iterator exhausted, that's fine
                    pass
                
                logger.info(f"Successfully fetched {len(articles)} articles for {ticker}")
            except Exception as iter_error:
                logger.error(f"Error iterating news for {ticker}: {iter_error}", exc_info=True)
                # Return empty list if iteration fails
                return []
            
            return articles
        except Exception as e:
            logger.error(f"Error fetching news for {ticker}: {e}", exc_info=True)
            return []
    
    def list_trades(
        self, 
        ticker: str, 
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
        limit: int = 50000
    ) -> List[Dict[str, Any]]:
        """
        Get tick-level trade data for a ticker.
        
        Args:
            ticker: Stock ticker symbol
            from_time: Start timestamp (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
            to_time: End timestamp
            limit: Maximum number of trades to return
            
        Returns:
            List of trade dicts with price, size, timestamp, exchange, conditions
        """
        try:
            self._check_client()
            
            # Default to last trading day if not specified
            if not from_time:
                from_time = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            if not to_time:
                to_time = datetime.now().strftime("%Y-%m-%d")
            
            trades = []
            for trade in self.client.list_trades(
                ticker=ticker,
                timestamp_gte=from_time,
                timestamp_lte=to_time,
                limit=limit
            ):
                trades.append({
                    "ticker": ticker,
                    "price": trade.price,
                    "size": trade.size,
                    "timestamp": trade.timestamp,
                    "exchange": getattr(trade, 'exchange', None),
                    "conditions": getattr(trade, 'conditions', None),
                    "tape": getattr(trade, 'tape', None),
                    "id": getattr(trade, 'id', None),
                })
            return trades
        except Exception as e:
            logger.error(f"Error fetching trades for {ticker}: {e}")
            return []
    
    def get_minute_aggregates(
        self,
        ticker: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 50000
    ) -> List[Dict[str, Any]]:
        """
        Get minute-level aggregate bars (OHLCV).
        
        Args:
            ticker: Stock ticker symbol
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            limit: Maximum number of bars to return
            
        Returns:
            List of minute bar dicts with OHLCV data
        """
        try:
            self._check_client()
            
            # Default to last 5 days
            if not from_date:
                from_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
            if not to_date:
                to_date = datetime.now().strftime("%Y-%m-%d")
            
            bars = []
            for bar in self.client.list_aggs(
                ticker=ticker,
                multiplier=1,
                timespan="minute",
                from_=from_date,
                to=to_date,
                limit=limit
            ):
                bars.append({
                    "ticker": ticker,
                    "timestamp": bar.timestamp,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "vwap": getattr(bar, 'vwap', None),
                    "transactions": getattr(bar, 'transactions', None),
                })
            return bars
        except Exception as e:
            logger.error(f"Error fetching minute aggregates for {ticker}: {e}")
            return []
    
    def get_second_aggregates(
        self,
        ticker: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 50000
    ) -> List[Dict[str, Any]]:
        """
        Get second-level aggregate bars (OHLCV).
        
        Args:
            ticker: Stock ticker symbol
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            limit: Maximum number of bars to return
            
        Returns:
            List of second bar dicts with OHLCV data
        """
        try:
            self._check_client()
            
            # Default to today only (second data is high volume)
            if not from_date:
                from_date = datetime.now().strftime("%Y-%m-%d")
            if not to_date:
                to_date = datetime.now().strftime("%Y-%m-%d")
            
            bars = []
            for bar in self.client.list_aggs(
                ticker=ticker,
                multiplier=1,
                timespan="second",
                from_=from_date,
                to=to_date,
                limit=limit
            ):
                bars.append({
                    "ticker": ticker,
                    "timestamp": bar.timestamp,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                    "vwap": getattr(bar, 'vwap', None),
                    "transactions": getattr(bar, 'transactions', None),
                })
            return bars
        except Exception as e:
            logger.error(f"Error fetching second aggregates for {ticker}: {e}")
            return []
    
    def list_exchanges(self) -> List[Dict[str, Any]]:
        """
        Get list of known exchanges.
        Note: Massive API may not have direct exchanges endpoint in Starter plan.
        Returns empty list if not available.
        
        Returns:
            List of exchange dicts with id, name, market, type
        """
        try:
            self._check_client()
            # Check if method exists
            if not hasattr(self.client, 'list_exchanges'):
                logger.warning("list_exchanges not available in Massive API Starter plan")
                return []
            
            exchanges = []
            for exchange in self.client.list_exchanges():
                exchanges.append({
                    "id": exchange.id,
                    "name": exchange.name,
                    "market": getattr(exchange, 'market', None),
                    "type": getattr(exchange, 'type', None),
                    "mic": getattr(exchange, 'mic', None),
                    "operating_mic": getattr(exchange, 'operating_mic', None),
                })
            return exchanges
        except Exception as e:
            logger.error(f"Error fetching exchanges: {e}")
            return []
    
    def get_balance_sheets(self, ticker: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get balance sheet data for a ticker.
        
        Args:
            ticker: Stock ticker symbol
            limit: Number of periods to return
            
        Returns:
            List of balance sheet dicts
        """
        try:
            self._check_client()
            sheets = []
            for sheet in self.client.list_financials_balance_sheets(tickers=ticker, limit=limit):
                data = {}
                if hasattr(sheet, 'data') and sheet.data:
                    data = {
                        "total_assets": getattr(sheet.data, 'total_assets', None),
                        "total_liabilities": getattr(sheet.data, 'total_liabilities', None),
                        "stockholders_equity": getattr(sheet.data, 'stockholders_equity', None),
                        "current_assets": getattr(sheet.data, 'current_assets', None),
                        "current_liabilities": getattr(sheet.data, 'current_liabilities', None),
                        "cash": getattr(sheet.data, 'cash', None),
                    }
                
                sheets.append({
                    "period_end": sheet.period_end,
                    "fiscal_year": sheet.fiscal_year,
                    "fiscal_quarter": getattr(sheet, 'fiscal_quarter', None),
                    "data": data,
                })
            return sheets
        except Exception as e:
            error_str = str(e)
            # Financials data requires higher tier plan - log at debug level instead of error
            if "NOT_AUTHORIZED" in error_str or "not entitled" in error_str.lower():
                logger.debug(f"Balance sheets not available for {ticker} (requires higher plan): {e}")
            else:
                logger.warning(f"Error fetching balance sheets for {ticker}: {e}")
            return []
    
    def get_cash_flow_statements(self, ticker: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get cash flow statement data for a ticker.
        
        Args:
            ticker: Stock ticker symbol
            limit: Number of periods to return
            
        Returns:
            List of cash flow statement dicts
        """
        try:
            self._check_client()
            statements = []
            for stmt in self.client.list_financials_cash_flows(tickers=ticker, limit=limit):
                data = {}
                if hasattr(stmt, 'data') and stmt.data:
                    data = {
                        "operating_cash_flow": getattr(stmt.data, 'net_cash_flow_from_operating_activities', None),
                        "investing_cash_flow": getattr(stmt.data, 'net_cash_flow_from_investing_activities', None),
                        "financing_cash_flow": getattr(stmt.data, 'net_cash_flow_from_financing_activities', None),
                        "free_cash_flow": getattr(stmt.data, 'free_cash_flow', None),
                    }
                
                statements.append({
                    "period_end": stmt.period_end,
                    "fiscal_year": stmt.fiscal_year,
                    "fiscal_quarter": getattr(stmt, 'fiscal_quarter', None),
                    "data": data,
                })
            return statements
        except Exception as e:
            error_str = str(e)
            # Financials data requires higher tier plan - log at debug level instead of error
            if "NOT_AUTHORIZED" in error_str or "not entitled" in error_str.lower():
                logger.debug(f"Cash flow statements not available for {ticker} (requires higher plan): {e}")
            else:
                logger.warning(f"Error fetching cash flow statements for {ticker}: {e}")
            return []

