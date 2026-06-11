"""
FinMind API service wrapper.

This module provides a wrapper around the FinMind API with:
- Error handling and fallback mechanisms
- Data transformation to match MassiveAPIService interface
- Rate limiting support
"""

import logging
import time
import hashlib
import requests
import pandas as pd
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from src.config import settings
from src.services import finmind_budget

logger = logging.getLogger(__name__)

# The TaiwanStockInfo table (the full stock-id ↔ name/industry registry) is near-static
# — it changes at most weekly — but get_ticker_details/list_tickers re-downloaded it on
# every cold miss, which was the single biggest FinMind-quota waster. Cache it in-process.
_STOCK_INFO_TTL_SECONDS = 6 * 3600
_stock_info_cache: dict = {"df": None, "ts": 0.0}


class FinMindAPIError(Exception):
    """Custom exception for FinMind API errors."""
    pass


class FinMindAPIService:
    """Service wrapper for FinMind API."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize FinMind API service.
        
        Args:
            api_key: FinMind API key. If None, reads from FINMIND_API_KEY env var
        """
        # Pool of keys to rotate across (each has its own hourly free-tier quota).
        # An explicitly-passed key wins; otherwise use the configured pool.
        if api_key:
            self.api_keys = [api_key]
        else:
            self.api_keys = settings.finmind_api_key_pool
        # Backward-compatible single-key handle (DataLoader logs in with the first key).
        self.api_key = self.api_keys[0] if self.api_keys else None
        self.api_base_url = "https://api.finmindtrade.com/api/v4/data"

        if not self.api_keys:
            logger.warning("FinMind API key not configured. API calls will fail.")
        elif len(self.api_keys) > 1:
            logger.info(f"FinMind: rotating across {len(self.api_keys)} keys (pooled quota).")

        # Try to initialize DataLoader for Python SDK (optional)
        self.dataloader = None
        try:
            from FinMind.data import DataLoader
            self.dataloader = DataLoader()
            if self.api_key:
                self.dataloader.login_by_token(api_token=self.api_key)
        except ImportError:
            logger.debug("FinMind DataLoader not available, using REST API only")
        except Exception as e:
            logger.warning(f"Failed to initialize FinMind DataLoader: {e}")
    
    def _check_api_key(self) -> None:
        """Check if at least one API key is configured."""
        if not self.api_keys:
            raise FinMindAPIError("FinMind API key not configured. Check API key configuration.")

    @staticmethod
    def _bucket(key: str) -> str:
        """Stable per-key budget bucket id (never the raw key — it's used in Redis keys/logs)."""
        return hashlib.sha256(key.encode()).hexdigest()[:12]

    def _acquire_key(self) -> Optional[str]:
        """
        Pick the first key in the pool that still has hourly budget, consuming one unit
        of its quota. Returns None when every key's hourly budget is exhausted.
        """
        for key in self.api_keys:
            if finmind_budget.consume(self._bucket(key)):
                return key
        return None
    
    def _make_request(self, params: Dict[str, Any], timeout: int = 10) -> Optional[Dict[str, Any]]:
        """
        Make HTTP request to FinMind API.
        
        Args:
            params: Request parameters
            timeout: Request timeout in seconds
            
        Returns:
            Response JSON data or None if error
        """
        try:
            self._check_api_key()

            # Hard-cap FinMind usage against each key's free-tier hourly quota, rotating to
            # the next key when one is spent. When ALL keys are exhausted, bail out (callers
            # degrade to cached/"unavailable") instead of burning quota on 402s.
            key = self._acquire_key()
            if key is None:
                return None

            headers = {"Authorization": f"Bearer {key}"}

            response = requests.get(self.api_base_url, headers=headers, params=params, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            
            if data.get("status") == 200:
                return data
            else:
                error_msg = data.get("msg", "Unknown error")
                logger.error(f"FinMind API error: {error_msg}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"FinMind API request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in FinMind API request: {e}")
            return None
    
    def _get_stock_info_df(self) -> Optional["pd.DataFrame"]:
        """
        Return the (cached) TaiwanStockInfo table.

        Cached in-process for _STOCK_INFO_TTL_SECONDS so the full-table download happens
        at most a few times a day instead of on every cold ticker load. Tries the
        DataLoader SDK first (budget-counted manually, since it bypasses _make_request),
        then the REST endpoint (budget-counted inside _make_request).
        """
        cached = _stock_info_cache.get("df")
        if cached is not None and (time.time() - _stock_info_cache["ts"]) < _STOCK_INFO_TTL_SECONDS:
            return cached

        df = None
        if self.dataloader and self.api_key:
            # DataLoader is logged in with the first key and bypasses _make_request, so
            # account for the request against that key's bucket explicitly.
            if not finmind_budget.consume(self._bucket(self.api_key)):
                return cached  # that key's budget exhausted — serve whatever we last had
            try:
                df = self.dataloader.taiwan_stock_info()
            except Exception as e:
                logger.debug(f"DataLoader taiwan_stock_info failed, trying REST: {e}")
                df = None

        if df is None or getattr(df, "empty", True):
            data = self._make_request({"dataset": "TaiwanStockInfo"})
            if data and data.get("data"):
                df = pd.DataFrame(data["data"])

        if df is not None and not df.empty:
            _stock_info_cache["df"] = df
            _stock_info_cache["ts"] = time.time()
            return df
        return cached

    def get_ticker_details(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get ticker details from FinMind API.

        Args:
            ticker: Stock ticker symbol (e.g., "2330" for TSMC)

        Returns:
            Ticker details dict or None if error/not found
        """
        try:
            df = self._get_stock_info_df()
            if df is not None and not df.empty:
                stock_info = df[df['stock_id'] == ticker]
                if not stock_info.empty:
                    row = stock_info.iloc[0]
                    return {
                        "ticker": ticker,
                        "name": str(row.get("stock_name", ticker)),
                        "market_cap": None,
                        "description": "",
                        "currency": "TWD",
                        "industry": str(row.get("industry_category", "Unknown")),
                        "shares_outstanding": None,
                        "icon_url": None,
                        "logo_url": None,
                        "icon_image": None,
                        "logo_image": None,
                    }
            return None
        except Exception as e:
            logger.error(f"Error fetching ticker details for {ticker}: {e}")
            return None
    
    def get_ticker_snapshot(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Get latest ticker snapshot (real-time OHLCV).
        Uses taiwan_stock_tick_snapshot for latest price.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Snapshot dict with latest price data or None if error
        """
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            
            params = {
                "dataset": "taiwan_stock_tick_snapshot",
                "data_id": ticker,
                "date": today,
            }
            
            data = self._make_request(params)
            if data and data.get("data"):
                df = pd.DataFrame(data["data"])
                if not df.empty:
                    # Get the latest record
                    latest = df.iloc[-1]
                    deal_price = latest.get("deal_price")
                    volume = latest.get("volume", 0)
                    
                    # Use deal_price as close price
                    return {
                        "ticker": ticker,
                        "open": deal_price,  # Approximate
                        "high": deal_price,  # Approximate
                        "low": deal_price,  # Approximate
                        "close": deal_price,
                        "price": deal_price,
                        "volume": int(volume) if pd.notna(volume) else 0,
                    }
            
            # Fallback to daily price if tick snapshot not available
            return self._get_latest_daily_price(ticker)
        except Exception as e:
            logger.error(f"Error fetching ticker snapshot for {ticker}: {e}")
            return None
    
    def _get_latest_daily_price(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Get latest daily price as fallback."""
        try:
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
            
            params = {
                "dataset": "TaiwanStockPrice",
                "data_id": ticker,
                "start_date": start_date,
                "end_date": end_date,
            }
            
            data = self._make_request(params)
            if data and data.get("data"):
                df = pd.DataFrame(data["data"])
                if not df.empty:
                    latest = df.iloc[-1]
                    return {
                        "ticker": ticker,
                        "open": float(latest.get("open", 0)),
                        "high": float(latest.get("max", 0)),
                        "low": float(latest.get("min", 0)),
                        "close": float(latest.get("close", 0)),
                        "price": float(latest.get("close", 0)),
                        "volume": int(latest.get("Trading_Volume", 0)),
                    }
            return None
        except Exception as e:
            logger.debug(f"Error fetching latest daily price for {ticker}: {e}")
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
            if date is None:
                date = datetime.now().strftime("%Y-%m-%d")
            
            params = {
                "dataset": "TaiwanStockPrice",
                "data_id": ticker,
                "start_date": date,
                "end_date": date,
            }
            
            data = self._make_request(params)
            summaries = []
            if data and data.get("data"):
                df = pd.DataFrame(data["data"])
                for _, row in df.iterrows():
                    summaries.append({
                        "date": str(row.get("date", date)),
                        "open": float(row.get("open", 0)),
                        "high": float(row.get("max", 0)),
                        "low": float(row.get("min", 0)),
                        "close": float(row.get("close", 0)),
                        "volume": int(row.get("Trading_Volume", 0)),
                    })
            return summaries
        except Exception as e:
            logger.error(f"Error fetching daily summary for {ticker} on {date}: {e}")
            return []
    
    def list_daily_ticker_summary_range(self, ticker: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """Get daily OHLCV rows for a date range, sorted by date ascending."""
        try:
            params = {
                "dataset": "TaiwanStockPrice",
                "data_id": ticker,
                "start_date": start_date,
                "end_date": end_date,
            }
            data = self._make_request(params)
            summaries = []
            if data and data.get("data"):
                df = pd.DataFrame(data["data"]).sort_values("date")
                for _, row in df.iterrows():
                    summaries.append({
                        "date": str(row.get("date", end_date)),
                        "open": float(row.get("open", 0)),
                        "high": float(row.get("max", 0)),
                        "low": float(row.get("min", 0)),
                        "close": float(row.get("close", 0)),
                        "volume": int(row.get("Trading_Volume", 0)),
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
            List of income statement dicts (empty if not available)
        """
        try:
            # FinMind may have financial statements, but it's not always available
            # Return empty list for now
            logger.debug(f"Income statements not available for {ticker} via FinMind")
            return []
        except Exception as e:
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
            end_date = datetime.now().strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
            
            params = {
                "dataset": "TaiwanStockPER",
                "data_id": ticker,
                "start_date": start_date,
                "end_date": end_date,
            }
            
            data = self._make_request(params)
            ratios = []
            if data and data.get("data"):
                df = pd.DataFrame(data["data"])
                if not df.empty:
                    latest = df.iloc[-1]
                    ratios.append({
                        "calculation_date": str(latest.get("date", end_date)),
                        "pe_ratio": float(latest.get("PER", 0)) if pd.notna(latest.get("PER")) else None,
                        "dividend_yield": None,  # Not available in TaiwanStockPER
                    })
            return ratios
        except Exception as e:
            logger.warning(f"Error fetching ratios for {ticker}: {e}")
            return []
    
    def list_top_movers(self, direction: str = "gainers") -> List[Dict[str, Any]]:
        """
        Get top market movers.
        Note: FinMind doesn't have a direct top movers endpoint.
        Returns empty list as this feature may not be available.
        
        Args:
            direction: "gainers" or "losers"
            
        Returns:
            List of top mover dicts (empty if not available)
        """
        try:
            logger.debug("Top movers endpoint not available in FinMind API")
            return []
        except Exception as e:
            logger.error(f"Error fetching top movers ({direction}): {e}")
            return []
    
    def list_tickers(self, market: str = "stocks", active: bool = True, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        List all available tickers.
        
        Args:
            market: Market type (e.g., "stocks") - ignored for Taiwan stocks
            active: Only return active tickers - ignored for Taiwan stocks
            limit: Maximum number of tickers to return
            
        Returns:
            List of ticker metadata dicts
        """
        try:
            tickers = []
            actual_limit = min(limit, 1000)

            # Reuse the cached TaiwanStockInfo table (same source the REST/DataLoader
            # paths used) so listing tickers doesn't re-download the full table.
            df = self._get_stock_info_df()
            if df is not None and not df.empty:
                for _, row in df.head(actual_limit).iterrows():
                    tickers.append({
                        "ticker": str(row.get("stock_id", "")),
                        "name": str(row.get("stock_name", "")),
                        "market": "tpex",
                        "currency": "TWD",
                        "active": True,
                    })
            return tickers
        except Exception as e:
            logger.error(f"Error listing tickers: {e}")
            return []
    
    def list_news(self, ticker: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get news articles for a ticker.
        Note: FinMind doesn't provide news data.
        Returns empty list.
        
        Args:
            ticker: Stock ticker symbol
            limit: Maximum number of articles to return
            
        Returns:
            Empty list (news not available in FinMind)
        """
        logger.debug(f"News not available for {ticker} via FinMind API")
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
            if not from_date:
                from_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
            if not to_date:
                to_date = datetime.now().strftime("%Y-%m-%d")
            
            params = {
                "dataset": "TaiwanStockKBar",
                "data_id": ticker,
                "start_date": from_date,
                "end_date": to_date,
                "freq": "1min",
            }
            
            data = self._make_request(params)
            bars = []
            if data and data.get("data"):
                df = pd.DataFrame(data["data"])
                for _, row in df.head(limit).iterrows():
                    # Convert date to timestamp
                    try:
                        date_str = str(row.get("date", ""))
                        if "T" in date_str:
                            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        else:
                            dt = datetime.strptime(date_str, "%Y-%m-%d")
                        timestamp = int(dt.timestamp() * 1000)
                    except:
                        timestamp = int(datetime.now().timestamp() * 1000)
                    
                    bars.append({
                        "ticker": ticker,
                        "timestamp": timestamp,
                        "open": float(row.get("open", 0)),
                        "high": float(row.get("high", 0)),
                        "low": float(row.get("low", 0)),
                        "close": float(row.get("close", 0)),
                        "volume": int(row.get("volume", 0)),
                        "vwap": None,
                        "transactions": None,
                    })
            return bars
        except Exception as e:
            logger.error(f"Error fetching minute aggregates for {ticker}: {e}")
            return []
    
    def get_daily_aggregates(
        self,
        ticker: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 50000
    ) -> List[Dict[str, Any]]:
        """
        Get daily aggregate bars (OHLCV).
        
        Args:
            ticker: Stock ticker symbol
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            limit: Maximum number of bars to return
            
        Returns:
            List of daily bar dicts with OHLCV data
        """
        try:
            if not from_date:
                from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            if not to_date:
                to_date = datetime.now().strftime("%Y-%m-%d")
            
            params = {
                "dataset": "TaiwanStockPrice",
                "data_id": ticker,
                "start_date": from_date,
                "end_date": to_date,
            }
            
            data = self._make_request(params)
            bars = []
            if data and data.get("data"):
                df = pd.DataFrame(data["data"])
                for _, row in df.head(limit).iterrows():
                    # Convert date to timestamp
                    try:
                        date_str = str(row.get("date", ""))
                        dt = datetime.strptime(date_str, "%Y-%m-%d")
                        timestamp = int(dt.timestamp() * 1000)
                    except:
                        timestamp = int(datetime.now().timestamp() * 1000)
                    
                    bars.append({
                        "ticker": ticker,
                        "timestamp": timestamp,
                        "open": float(row.get("open", 0)),
                        "high": float(row.get("max", 0)),
                        "low": float(row.get("min", 0)),
                        "close": float(row.get("close", 0)),
                        "volume": int(row.get("Trading_Volume", 0)),
                        "vwap": None,
                        "transactions": None,
                    })
            return bars
        except Exception as e:
            logger.error(f"Error fetching daily aggregates for {ticker}: {e}")
            return []

