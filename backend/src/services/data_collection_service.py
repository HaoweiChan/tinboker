"""Data collection service for stock data from Massive and FinMind APIs."""
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from src.services.massive_service import MassiveAPIService, MassiveAPIError
from src.services.finmind_service import FinMindAPIService, FinMindAPIError
from src.models.schemas import Stock, StockMetadata, StockPriceRecord, StockPriceHistory, CompanyStats

logger = logging.getLogger(__name__)


class DataCollectionService:
    """Service for collecting stock data from external APIs."""

    def __init__(
        self,
        massive_service: Optional[MassiveAPIService] = None,
        finmind_service: Optional[FinMindAPIService] = None
    ):
        self.massive_service = massive_service or MassiveAPIService()
        self.finmind_service = finmind_service or FinMindAPIService()
    
    def _is_taiwan_stock(self, ticker: str) -> bool:
        """
        Check if ticker is a Taiwan stock (numeric ticker).
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            True if ticker is all digits (Taiwan stock), False otherwise
        """
        # Taiwan stocks use numeric tickers (e.g., "2330" for TSMC)
        # US stocks use alphabetic tickers (e.g., "AAPL", "NVDA")
        return ticker.isdigit()
    
    def collect_stock_data(self, ticker: str, use_mock_fallback: bool = True, timeframe: Optional[str] = None, before: Optional[int] = None) -> Optional[Stock]:
        """
        Collect all data for a stock (cold start scenario).
        
        Routes to FinMind API for Taiwan stocks (numeric tickers) or Massive API for US stocks (alphabetic tickers).
        Falls back to mock data on error.
        
        Args:
            ticker: Stock ticker symbol (e.g., "NVDA", "AAPL" for US, "2330" for Taiwan)
            use_mock_fallback: Whether to fall back to mock data on error
            timeframe: Optional timeframe filter (1H, 1D) - affects data granularity
            before: Optional Unix timestamp (ms). Fetch data ending before this time for infinite scroll.
            
        Returns:
            Stock object with all data or None if not found
        """
        # Route based on ticker type
        if self._is_taiwan_stock(ticker):
            # Taiwan stock - use FinMind API (before supported for daily aggregates)
            try:
                logger.info(f"Collecting data for Taiwan stock {ticker} from FinMind API (timeframe: {timeframe}, before: {before})...")
                stock = self._collect_from_finmind(ticker, timeframe=timeframe, before=before)
                if stock:
                    logger.info(f"Successfully collected data for {ticker} from FinMind API")
                    return stock
            except FinMindAPIError as e:
                logger.warning(f"FinMind API error for {ticker}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error collecting data for {ticker}: {e}")
        else:
            # US stock - use Massive API
            try:
                logger.info(f"Collecting data for US stock {ticker} from Massive API (timeframe: {timeframe}, before: {before})...")
                stock = self._collect_from_massive(ticker, timeframe=timeframe, before=before)
                if stock:
                    logger.info(f"Successfully collected data for {ticker} from Massive API")
                    return stock
            except MassiveAPIError as e:
                logger.warning(f"Massive API error for {ticker}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error collecting data for {ticker}: {e}")
        
        if use_mock_fallback:
            logger.warning(f"No data available for {ticker} from any API source")
        return None
    
    def _collect_from_finmind(self, ticker: str, timeframe: Optional[str] = None, before: Optional[int] = None) -> Optional[Stock]:
        """
        Collect data from FinMind API for Taiwan stocks.
        
        Args:
            ticker: Stock ticker symbol (numeric, e.g., "2330")
            timeframe: Optional timeframe filter (1H, 1D, 1W, 1M, etc.) - determines data granularity
            before: Optional Unix timestamp (ms). When provided, fetch data ending before this time (pagination).
        """
        # Get ticker details
        details = self.finmind_service.get_ticker_details(ticker)
        if not details:
            raise FinMindAPIError(f"Could not fetch ticker details for {ticker}")
        
        # Create metadata
        industry = details.get("industry")
        if industry is None:
            industry = "Unknown"
        
        metadata = StockMetadata(
            stock_id=ticker,
            ticker=ticker,
            stock_name=details.get("name", ticker),
            industry_category=industry,
            currency=details.get("currency", "TWD")
        )
        
        # Get latest snapshot
        snapshot = self.finmind_service.get_ticker_snapshot(ticker)
        
        # Get historical data - fetch minute-level for 1H/1D, daily for others
        price_history = StockPriceHistory()
        
        try:
            if timeframe in ['1H', '1D'] and not before:
                # Fetch minute-level aggregates for intraday timeframes (no before for minute)
                logger.info(f"Fetching minute-level aggregates for {ticker} (timeframe: {timeframe})")
                self._fetch_finmind_minute_aggregates(ticker, timeframe, price_history)
            else:
                # Fetch daily aggregates for longer timeframes or when before is set
                logger.info(f"Fetching daily aggregates for {ticker} (timeframe: {timeframe or 'ALL'}, before: {before})")
                self._fetch_finmind_daily_aggregates(ticker, price_history, timeframe=timeframe, before=before)
        except Exception as e:
            logger.warning(f"Could not fetch historical data for {ticker}: {e}")
            # Continue without historical data
        
        # Get financial data
        income_statements = self.finmind_service.list_financials_income_statements(ticker)
        revenue = None
        if income_statements:
            latest = income_statements[0]
            revenue = latest.get("revenue")
        
        # Get ratios
        ratios = self.finmind_service.list_financials_ratios(ticker)
        pe = None
        dividend_yield = None
        if ratios:
            latest_ratio = ratios[0]
            pe = latest_ratio.get("pe_ratio")
            dividend_yield = latest_ratio.get("dividend_yield")
        
        # Calculate current price and change from snapshot, falling back to chart data
        current_price = None
        change = None
        change_percent = None
        snapshot_volume = 0
        if snapshot:
            current_price = snapshot.get("price") or snapshot.get("close")
            snapshot_volume = int(snapshot.get("volume", 0))
        # Fallback: derive price/change/volume from the most recent chart data entries
        if not current_price and price_history.day:
            last_rec = price_history.day[-1]
            current_price = last_rec.close
            snapshot_volume = int(last_rec.Trading_Volume or 0)
            logger.info(f"Snapshot empty for {ticker}, using last chart entry: price={current_price}, date={last_rec.date}")
        if current_price and price_history.day and len(price_history.day) >= 2:
            last_rec = price_history.day[-1]
            if abs(last_rec.close - current_price) < 0.0001:
                previous_close = price_history.day[-2].close
            else:
                previous_close = last_rec.close
            if previous_close > 0:
                change = current_price - previous_close
                change_percent = (change / previous_close * 100)
        stats = CompanyStats(
            volume=snapshot_volume,
            beta=0.0,
            volatility=0.0,
        )
        # Create Stock object
        market_cap = details.get("market_cap")
        if market_cap is not None:
            market_cap = int(market_cap) if isinstance(market_cap, float) else market_cap
        stock = Stock(
            stock_id=ticker,
            metadata=metadata,
            stock_price_history=price_history,
            price=current_price,
            change=change,
            changePercent=change_percent,
            marketCap=market_cap,
            revenue=revenue,
            pe=pe,
            dividendYield=dividend_yield,
            about=details.get("description", ""),
            stats=stats
        )
        return stock
    
    def _fetch_finmind_daily_aggregates(
        self,
        ticker: str,
        price_history: StockPriceHistory,
        timeframe: Optional[str] = None,
        before: Optional[int] = None,
    ) -> None:
        """Fetch daily aggregates from FinMind. Supports timeframe and before (pagination) like US/Massive."""
        # Align window size with Massive: 1D=365d, 1W~2y, 1M~3y, 3M/6M/1Y, YTD, ALL=5y
        days = 365
        if timeframe == "1W":
            days = 730
        elif timeframe == "1M":
            days = 1095
        elif timeframe in ("3M", "6M"):
            days = 730 if timeframe == "6M" else 1095
        elif timeframe == "1Y":
            days = 365
        elif timeframe == "YTD":
            now = datetime.now()
            start_of_year = datetime(now.year, 1, 1)
            days = (now - start_of_year).days
            if before:
                end_dt = datetime.fromtimestamp(before / 1000)
                days = max((end_dt - datetime(end_dt.year, 1, 1)).days, 1)
        elif timeframe == "ALL":
            days = 1825

        if before:
            end_datetime = datetime.fromtimestamp(before / 1000)
            to_date = end_datetime.strftime("%Y-%m-%d")
            from_date = (end_datetime - timedelta(days=days)).strftime("%Y-%m-%d")
            logger.info(f"Fetching FinMind daily for {ticker} before {to_date} (pagination)")
        else:
            from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            to_date = datetime.now().strftime("%Y-%m-%d")

        limit = min(days + 50, 50000)
        bars = self.finmind_service.get_daily_aggregates(ticker, from_date=from_date, to_date=to_date, limit=limit)
        
        for bar in bars:
            # Convert timestamp to date string
            try:
                agg_date = datetime.fromtimestamp(bar["timestamp"] / 1000).strftime("%Y-%m-%d")
            except:
                agg_date = datetime.now().strftime("%Y-%m-%d")
            
            vol = int(bar.get("volume", 0))
            record = StockPriceRecord(
                date=agg_date,
                timestamp=bar["timestamp"],
                Trading_Volume=vol,
                Trading_money=vol * bar.get("close", 0),
                open=bar.get("open", 0),
                max=bar.get("high", 0),
                min=bar.get("low", 0),
                close=bar.get("close", 0),
                spread=bar.get("high", 0) - bar.get("low", 0),
                Trading_turnover=0.0
            )
            price_history.add_record(record)

    def _fetch_finmind_minute_aggregates(self, ticker: str, timeframe: str, price_history: StockPriceHistory) -> None:
        """
        Fetch minute-level aggregates from FinMind for 1H/1D timeframes.
        
        Note: Falls back to daily aggregates if minute data is not available.
        """
        now = datetime.now()
        
        if timeframe == '1H':
            # Fetch last 60-120 minutes of minute bars
            from_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
            to_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")  # Use yesterday only
            limit = 120  # Last 120 minutes
        elif timeframe == '1D':
            # Fetch last 24 hours of minute bars
            from_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
            to_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")  # Use yesterday only
            limit = 1440  # 24 hours * 60 minutes
        else:
            # Should not happen, but fallback to daily
            self._fetch_finmind_daily_aggregates(ticker, price_history)
            return
        
        try:
            bars = self.finmind_service.get_minute_aggregates(ticker, from_date=from_date, to_date=to_date, limit=limit)
            
            if not bars:
                # No minute data returned - fallback to daily
                logger.warning(
                    f"No minute-level data available for {ticker} (timeframe: {timeframe}). "
                    f"Falling back to daily aggregates."
                )
                self._fetch_finmind_daily_aggregates(ticker, price_history)
            else:
                for bar in bars:
                    # Convert timestamp to date string (for minute data, use the date portion)
                    try:
                        agg_datetime = datetime.fromtimestamp(bar["timestamp"] / 1000)
                        agg_date = agg_datetime.strftime("%Y-%m-%d")
                    except:
                        agg_date = datetime.now().strftime("%Y-%m-%d")
                    
                    vol = int(bar.get("volume", 0))
                    record = StockPriceRecord(
                        date=agg_date,
                        timestamp=bar["timestamp"],
                        Trading_Volume=vol,
                        Trading_money=vol * bar.get("close", 0),
                        open=bar.get("open", 0),
                        max=bar.get("high", 0),
                        min=bar.get("low", 0),
                        close=bar.get("close", 0),
                        spread=bar.get("high", 0) - bar.get("low", 0),
                        Trading_turnover=0.0
                    )
                    price_history.add_record(record)
                
                logger.info(f"Fetched {len(bars)} minute bars for {ticker} (timeframe: {timeframe})")
                
        except Exception as e:
            logger.warning(
                f"Error fetching minute aggregates for {ticker} (timeframe: {timeframe}): {e}. "
                f"Falling back to daily aggregates."
            )
            # Fallback to daily aggregates on any error
            self._fetch_finmind_daily_aggregates(ticker, price_history)
    
    def _collect_from_massive(self, ticker: str, timeframe: Optional[str] = None, before: Optional[int] = None) -> Optional[Stock]:
        """
        Collect data from Massive API.
        
        Args:
            ticker: Stock ticker symbol
            timeframe: Optional timeframe filter (1H, 1D) - determines data granularity
            before: Optional Unix timestamp (ms). Fetch data ending before this time for infinite scroll.
        """
        # Get ticker details
        details = self.massive_service.get_ticker_details(ticker)
        if not details:
            raise MassiveAPIError(f"Could not fetch ticker details for {ticker}")
        
        # Create metadata
        industry = details.get("industry")
        if industry is None:
            industry = "Unknown"
        
        metadata = StockMetadata(
            stock_id=ticker,
            ticker=ticker,
            stock_name=details.get("name", ticker),
            industry_category=industry,
            currency=details.get("currency", "USD")
        )
        
        # Get latest snapshot
        snapshot = self.massive_service.get_ticker_snapshot(ticker)
        
        # Get historical data - fetch minute-level for 1H/1D, daily for others
        price_history = StockPriceHistory()
        
        try:
            if timeframe in ['1H', '1Min']:
                # Fetch minute-level aggregates for intraday timeframes
                logger.info(f"Fetching minute-level aggregates for {ticker} (timeframe: {timeframe})")
                self._fetch_minute_aggregates(ticker, timeframe, price_history)
            else:
                # Fetch aggregates for other timeframes (Day/Week/Month)
                logger.info(f"Fetching aggregates for {ticker} (timeframe: {timeframe or '1D'}, before: {before})")
                self._fetch_aggregates(ticker, price_history, timeframe, before)
        except Exception as e:
            logger.warning(f"Could not fetch historical data for {ticker}: {e}")
            # Continue without historical data
        
        # Get financial data
        income_statements = self.massive_service.list_financials_income_statements(ticker)
        revenue = None
        if income_statements:
            latest = income_statements[0]
            revenue = latest.get("revenue")
        
        # Get ratios
        ratios = self.massive_service.list_financials_ratios(ticker)
        pe = None
        dividend_yield = None
        if ratios:
            latest_ratio = ratios[0]
            pe = latest_ratio.get("pe_ratio")
            dividend_yield = latest_ratio.get("dividend_yield")
        
        # Calculate current price and change from snapshot, falling back to chart data
        current_price = None
        change = None
        change_percent = None
        snapshot_volume = 0
        if snapshot:
            current_price = snapshot.get("price") or snapshot.get("close")
            snapshot_volume = int(snapshot.get("volume", 0))
        # Fallback: derive price/change/volume from the most recent chart data entries
        if not current_price and price_history.day:
            last_rec = price_history.day[-1]
            current_price = last_rec.close
            snapshot_volume = int(last_rec.Trading_Volume or 0)
            logger.info(f"Snapshot empty for {ticker}, using last chart entry: price={current_price}, date={last_rec.date}")
        if current_price and price_history.day and len(price_history.day) >= 2:
            last_rec = price_history.day[-1]
            if abs(last_rec.close - current_price) < 0.0001:
                previous_close = price_history.day[-2].close
            else:
                previous_close = last_rec.close
            if previous_close > 0:
                change = current_price - previous_close
                change_percent = (change / previous_close * 100)
        stats = CompanyStats(
            volume=snapshot_volume,
            beta=0.0,
            volatility=0.0,
        )
        # Create Stock object
        market_cap = details.get("market_cap")
        if market_cap is not None:
            market_cap = int(market_cap) if isinstance(market_cap, float) else market_cap
        stock = Stock(
            stock_id=ticker,
            metadata=metadata,
            stock_price_history=price_history,
            price=current_price,
            change=change,
            changePercent=change_percent,
            marketCap=market_cap,
            revenue=revenue,
            pe=pe,
            dividendYield=dividend_yield,
            about=details.get("description", ""),
            stats=stats
        )
        return stock

    def _fetch_aggregates(self, ticker: str, price_history: StockPriceHistory, timeframe: Optional[str] = None, before: Optional[int] = None) -> None:
        """Fetch aggregates for specified timeframe.
        
        Args:
            ticker: Stock ticker symbol
            price_history: StockPriceHistory object to populate with data
            timeframe: Timeframe filter (1D, 1W, 1M, YTD, ALL)
            before: Optional Unix timestamp (ms). When provided, fetch data ending before this time.
                    Used for infinite scroll / pagination to load older historical data.
        """
        timespan = 'day'
        days = 365  # Default to 1 year
        
        if timeframe == '1W':
            timespan = 'week'
            days = 1825 # 5 years
        elif timeframe == '1M':
            timespan = 'month'
            days = 3650 # 10 years
        elif timeframe == '1D' or timeframe is None:
            timespan = 'day'
            days = 365 # 1 year
        elif timeframe == 'YTD':
            timespan = 'day'
            now = datetime.now()
            start_of_year = datetime(now.year, 1, 1)
            days = (now - start_of_year).days
        elif timeframe == 'ALL':
            timespan = 'day'
            days = 1825  # 5 years
        
        # When 'before' is provided, use it as the end date for pagination
        if before:
            end_datetime = datetime.fromtimestamp(before / 1000)
            to_date = end_datetime.strftime("%Y-%m-%d")
            from_date = (end_datetime - timedelta(days=days)).strftime("%Y-%m-%d")
            logger.info(f"Fetching historical data for {ticker} before {to_date} (pagination mode)")
        else:
            from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
            to_date = datetime.now().strftime("%Y-%m-%d")
        
        if self.massive_service.client is None:
            raise MassiveAPIError("Massive API client not initialized")
        
        # Limit adjustment
        limit = days if timespan == 'day' else (days // 7 if timespan == 'week' else days // 30)
        limit += 50 # Buffer
        
        for agg in self.massive_service.client.list_aggs(
            ticker=ticker,
            multiplier=1,
            timespan=timespan,
            from_=from_date,
            to=to_date,
            limit=limit
        ):
            # Convert timestamp to date string
            try:
                agg_date = datetime.fromtimestamp(agg.timestamp / 1000).strftime("%Y-%m-%d")
            except:
                agg_date = datetime.now().strftime("%Y-%m-%d")
            
            vol = int(getattr(agg, 'volume', 0))
            record = StockPriceRecord(
                date=agg_date,
                timestamp=agg.timestamp,
                Trading_Volume=vol,
                Trading_money=vol * agg.close,
                open=agg.open,
                max=agg.high,
                min=agg.low,
                close=agg.close,
                spread=agg.high - agg.low,
                Trading_turnover=0.0
            )
            price_history.add_record(record)

    def _fetch_minute_aggregates(self, ticker: str, timeframe: str, price_history: StockPriceHistory) -> None:
        """
        Fetch minute-level aggregates for 1H/1D timeframes.
        
        Note: Massive API Starter plan may not include minute-level data.
        Falls back to daily aggregates if minute data is not available.
        """
        now = datetime.now()
        
        if timeframe == '1H':
            # Fetch last 60-120 minutes of minute bars
            # Use yesterday to ensure data is available (15-min delayed data)
            # Starter plan has 15-min delay, so today's data might not be available yet
            from_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
            to_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")  # Use yesterday only
            limit = 120  # Last 120 minutes
        elif timeframe == '1D':
            # Fetch last 24 hours of minute bars
            # Use yesterday to ensure data is available (15-min delayed data)
            from_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
            to_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")  # Use yesterday only
            limit = 1440  # 24 hours * 60 minutes
        else:
            # Should not happen, but fallback to daily
            self._fetch_aggregates(ticker, price_history, timeframe)
            return
        
        if self.massive_service.client is None:
            raise MassiveAPIError("Massive API client not initialized")
        
        try:
            # Try to fetch minute-level aggregates
            # Note: Starter plan may not support minute-level data
            minute_count = 0
            for agg in self.massive_service.client.list_aggs(
                ticker=ticker,
                multiplier=1,
                timespan='minute',
                from_=from_date,
                to=to_date,
                limit=limit
            ):
                # Convert timestamp to date string (for minute data, use the date portion)
                try:
                    agg_datetime = datetime.fromtimestamp(agg.timestamp / 1000)
                    agg_date = agg_datetime.strftime("%Y-%m-%d")
                except:
                    agg_date = datetime.now().strftime("%Y-%m-%d")
                
                vol = int(getattr(agg, 'volume', 0))
                record = StockPriceRecord(
                    date=agg_date,
                    timestamp=agg.timestamp,
                    Trading_Volume=vol,
                    Trading_money=vol * agg.close,
                    open=agg.open,
                    max=agg.high,
                    min=agg.low,
                    close=agg.close,
                    spread=agg.high - agg.low,
                    Trading_turnover=0.0
                )
                price_history.add_record(record)
                minute_count += 1
            
            if minute_count == 0:
                # No minute data returned - likely plan limitation
                logger.warning(
                    f"No minute-level data available for {ticker} (timeframe: {timeframe}). "
                    f"This may be due to plan limitations. Falling back to daily aggregates."
                )
                # Fallback to daily aggregates
                self._fetch_aggregates(ticker, price_history, timeframe)
            else:
                logger.info(f"Fetched {minute_count} minute bars for {ticker} (timeframe: {timeframe})")
                
        except Exception as e:
            error_str = str(e)
            # Check if it's a plan limitation error
            if "NOT_AUTHORIZED" in error_str or "doesn't include this data timeframe" in error_str.lower():
                logger.warning(
                    f"Minute-level data not available for {ticker} due to plan limitations. "
                    f"Falling back to daily aggregates. Error: {error_str}"
                )
            else:
                logger.warning(
                    f"Error fetching minute aggregates for {ticker} (timeframe: {timeframe}): {e}. "
                    f"Falling back to daily aggregates."
                )
            # Fallback to daily aggregates on any error
            self._fetch_aggregates(ticker, price_history, timeframe)
    
    def update_stock_price(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Update stock price data only (for real-time updates).
        
        Routes to FinMind for Taiwan stocks or Massive for US stocks.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Updated price data dict or None if error
        """
        try:
            if self._is_taiwan_stock(ticker):
                # Taiwan stock - use FinMind API
                snapshot = self.finmind_service.get_ticker_snapshot(ticker)
            else:
                # US stock - use Massive API
                snapshot = self.massive_service.get_ticker_snapshot(ticker)
            
            if snapshot:
                return snapshot
        except Exception as e:
            logger.error(f"Error updating stock price for {ticker}: {e}")
        
        return None
    
    def update_stock_financials(self, ticker: str) -> Optional[Dict[str, Any]]:
        """
        Update stock financial data.
        
        Routes to FinMind for Taiwan stocks or Massive for US stocks.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Updated financial data dict or None if error
        """
        try:
            if self._is_taiwan_stock(ticker):
                # Taiwan stock - use FinMind API
                income_statements = self.finmind_service.list_financials_income_statements(ticker)
                ratios = self.finmind_service.list_financials_ratios(ticker)
            else:
                # US stock - use Massive API
                income_statements = self.massive_service.list_financials_income_statements(ticker)
                ratios = self.massive_service.list_financials_ratios(ticker)
            
            return {
                "revenue": income_statements[0].get("revenue") if income_statements else None,
                "pe": ratios[0].get("pe_ratio") if ratios else None,
                "dividend_yield": ratios[0].get("dividend_yield") if ratios else None,
            }
        except Exception as e:
            logger.error(f"Error updating stock financials for {ticker}: {e}")
        
        return None
    
    def get_stock_basic_info_fast(self, ticker: str) -> Optional[Stock]:
        """
        Get basic stock information quickly (for list views).
        Only fetches ticker details (skips snapshot to avoid slow API calls).
        This is much faster but price/volume will be None.
        
        Routes to FinMind for Taiwan stocks or Massive for US stocks.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Stock object with basic info or None
        """
        try:
            # Get ticker details (name, market cap, description) - this is fast
            if self._is_taiwan_stock(ticker):
                details = self.finmind_service.get_ticker_details(ticker)
            else:
                details = self.massive_service.get_ticker_details(ticker)
            
            if not details:
                return None
            
            # Create metadata
            metadata = StockMetadata(
                stock_id=ticker,
                ticker=ticker,
                stock_name=details.get("name", ticker),
                industry_category=details.get("industry", "Unknown"),
                currency=details.get("currency", "USD")
            )
            
            # Skip snapshot call - it's too slow (uses list_aggs which can hang)
            # Price and volume will be None for list view, but that's acceptable for speed
            # Users can get full details from /api/stocks/{ticker} endpoint
            
            # Create Stock object with minimal data
            market_cap = details.get("market_cap")
            if market_cap is not None:
                market_cap = int(market_cap) if isinstance(market_cap, float) else market_cap
            
            stock = Stock(
                stock_id=ticker,
                metadata=metadata,
                stock_price_history=StockPriceHistory(),  # Empty - not needed for list
                price=None,  # Not fetched for speed (use detail endpoint for price)
                change=None,
                changePercent=None,
                marketCap=market_cap,
                revenue=None,  # Not fetched for speed
                pe=None,  # Not fetched for speed
                dividendYield=None,  # Not fetched for speed
                about=details.get("description", ""),
                stats=None  # Not fetched for speed
            )
            
            return stock
        except Exception as e:
            logger.debug(f"Error getting basic info for {ticker}: {e}")
            return None
    
    def get_all_stocks(self, limit: int = 50) -> List[Stock]:
        """
        Get list of available stocks with basic information from Massive API.
        Uses fast method that only fetches essential data (no history, no financials).
        
        Args:
            limit: Maximum number of stocks to return (default: 50, max: 200)
        
        Returns:
            List of Stock objects
        """
        try:
            # Cap limit at 200 to prevent excessive API calls
            actual_limit = min(limit, 200)
            
            # Get ticker list from Massive API
            logger.info(f"Getting stock list from Massive API (limit: {actual_limit})")
            tickers = self.massive_service.list_tickers(market="stocks", active=True, limit=actual_limit)
            
            if not tickers:
                logger.warning("No tickers returned from Massive API")
                raise Exception("No tickers returned from Massive API")
            
            stocks = []
            # Ultra-fast mode: Use only data from list_tickers (no additional API calls per ticker)
            # This is much faster but has limited data (no market cap, description, price)
            for ticker_info in tickers[:actual_limit]:
                ticker = ticker_info.get("ticker")
                if ticker:
                    try:
                        # Create minimal Stock object from ticker list data only
                        metadata = StockMetadata(
                            stock_id=ticker,
                            ticker=ticker,
                            stock_name=ticker_info.get("name", ticker),
                            industry_category="Unknown",
                            currency=ticker_info.get("currency", "USD")
                        )
                        
                        stock = Stock(
                            stock_id=ticker,
                            metadata=metadata,
                            stock_price_history=StockPriceHistory(),
                            price=None,  # Not available from list_tickers
                            change=None,
                            changePercent=None,
                            marketCap=None,  # Not available from list_tickers
                            revenue=None,
                            pe=None,
                            dividendYield=None,
                            about="",
                            stats=None
                        )
                        stocks.append(stock)
                    except Exception as e:
                        logger.debug(f"Error creating stock for {ticker}: {e}")
                        continue
            
            logger.info(f"Successfully collected data for {len(stocks)} stocks from Massive API")
            return stocks
        except Exception as e:
            logger.error(f"Error getting all stocks from Massive API: {e}")
            
            # Fallback to mock data
            logger.info("Falling back to mock data for stock list")
            try:
                mock_collection = self.mock_service.get_company_list()
                mock_stocks = []
                for metadata in mock_collection.stocks:
                    try:
                        # Create minimal Stock object from mock metadata
                        stock = Stock(
                            stock_id=metadata.stock_id,
                            metadata=metadata,
                            stock_price_history=StockPriceHistory(),  # Empty
                            price=None,
                            change=None,
                            changePercent=None,
                            marketCap=None,
                            revenue=None,
                            pe=None,
                            dividendYield=None,
                            about="",
                            stats=None
                        )
                        mock_stocks.append(stock)
                    except Exception as e_mock:
                        logger.debug(f"Error creating mock stock for {metadata.stock_id}: {e_mock}")
                
                logger.info(f"Successfully collected {len(mock_stocks)} stocks from mock data")
                return mock_stocks
            except Exception as e_fallback:
                logger.error(f"Error getting mock stock list: {e_fallback}")
                return []

