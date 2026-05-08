import os
import requests
import pandas as pd
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from src.models.schemas import StockMetadataCollection, Stock, StockMetadata, StockPriceHistory, StockPriceRecord


class CompanyDataService(ABC):
    """Abstract base class for company data services"""
    
    @abstractmethod
    def get_company_list(self) -> StockMetadataCollection:
        """Retrieve list of all companies as StockMetadataCollection"""
        pass
    
    @abstractmethod
    def get_company_detail(self, stock_id: str) -> Optional[Stock]:
        """Retrieve detailed information for a specific company as Stock object"""
        pass
    
    @abstractmethod
    def get_top_movers(self) -> List[Dict]:
        """Retrieve top moving stocks"""
        pass


class FinMindCompanyDataService(CompanyDataService):
    """FinMind API implementation of CompanyDataService"""
    
    def __init__(self, api_token: Optional[str] = None):
        """
        Initialize FinMind service
        
        Args:
            api_token: FinMind API token. If None, reads from FINMIND_API_KEY env var
        """
        try:
            from FinMind.data import DataLoader
        except ImportError:
            raise ImportError(
                "FinMind package not installed. Install with: pip install FinMind"
            )
        
        self.api = DataLoader()
        
        # Get API token from parameter or environment and store for US REST API calls
        # Check both FINMIND_API_KEY and FINMIND_API_TOKEN for compatibility
        self.api_token = api_token or os.getenv("FINMIND_API_KEY") or os.getenv("FINMIND_API_TOKEN")
        if self.api_token:
            self.api.login_by_token(api_token=self.api_token)
        
        # US API endpoint
        self.us_api_url = 'https://api.finmindtrade.com/api/v4/data'
    
    def get_company_list_TW(self) -> StockMetadataCollection:
        """Retrieve Taiwan stock list from FinMind API"""
        try:
            # Get Taiwan stock info with timeout protection
            df = self.api.taiwan_stock_info()
            
            if df is None or df.empty:
                return StockMetadataCollection()
            
            collection = StockMetadataCollection()
            
            # Convert DataFrame to StockMetadata objects
            for _, row in df.iterrows():
                # Skip ETFs and other non-standard stocks if needed
                if "ETF" in str(row.get("industry_category", "")):
                    continue
                
                metadata = StockMetadata(
                    stock_id=str(row["stock_id"]),
                    ticker=str(row["stock_id"]),  # Taiwan stocks use stock_id as ticker
                    stock_name=str(row["stock_name"]),
                    industry_category=str(row["industry_category"]),
                    currency="TWD"  # Taiwan Dollar
                )
                
                try:
                    collection.add(metadata)
                except ValueError:
                    # Skip duplicates
                    continue
            
            return collection
        except Exception as e:
            # If FinMind API fails or times out, log and return empty
            print(f"Error fetching TW stock list from FinMind: {e}")
            return StockMetadataCollection()
    
    def get_company_list_US(self) -> StockMetadataCollection:
        """Retrieve US stock list from FinMind REST API"""
        collection = StockMetadataCollection()
        
        try:
            headers = {"Authorization": f"Bearer {self.api_token}"} if self.api_token else {}
            parameter = {
                "dataset": "USStockInfo"
            }
            
            response = requests.get(self.us_api_url, headers=headers, params=parameter, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if 'data' in data and data['data']:
                df = pd.DataFrame(data['data'])
                
                # Get the latest entry for each stock (by stock_id)
                # Group by stock_id and take the most recent date
                if not df.empty and 'date' in df.columns and 'stock_id' in df.columns:
                    df = df.sort_values('date', ascending=False)
                    df = df.drop_duplicates(subset='stock_id', keep='first')
                
                for _, row in df.iterrows():
                    # Map US schema to StockMetadata
                    stock_id = str(row.get("stock_id", ""))
                    stock_name = str(row.get("stock_name", ""))
                    subsector = str(row.get("Subsector", "Unknown"))
                    
                    if not stock_id or not stock_name:
                        continue
                    
                    metadata = StockMetadata(
                        stock_id=stock_id,
                        ticker=stock_id,  # US stocks use ticker as stock_id
                        stock_name=stock_name,
                        industry_category=subsector,
                        currency="USD"
                    )
                    
                    try:
                        collection.add(metadata)
                    except ValueError:
                        # Skip duplicates
                        continue
        except Exception as e:
            # Log error but return empty collection gracefully
            print(f"Error fetching US stock list: {e}")
        
        return collection
    
    def get_company_list(self) -> StockMetadataCollection:
        """Retrieve aggregated list of Taiwan and US stocks from FinMind API"""
        # Get both TW and US stocks
        tw_collection = self.get_company_list_TW()
        us_collection = self.get_company_list_US()
        
        # Merge collections
        merged_collection = StockMetadataCollection()
        
        # Add TW stocks
        for stock in tw_collection.stocks:
            try:
                merged_collection.add(stock)
            except ValueError:
                # Skip duplicates (shouldn't happen, but safe)
                continue
        
        # Add US stocks
        for stock in us_collection.stocks:
            try:
                merged_collection.add(stock)
            except ValueError:
                # Skip duplicates if stock_id conflicts
                continue
        
        return merged_collection
    
    def get_company_detail_TW(self, stock_id: str) -> Optional[Stock]:
        """
        Retrieve detailed Taiwan stock information from FinMind API
        
        Args:
            stock_id: Taiwan stock ID (e.g., "2330" for TSMC)
        
        Returns:
            Stock object with metadata and price history, or None if not found
        """
        # Get company metadata
        df_info = self.api.taiwan_stock_info()
        
        if df_info is None or df_info.empty:
            return None
        
        # Find the stock in the info dataframe
        stock_info = df_info[df_info["stock_id"] == stock_id]
        
        if stock_info.empty:
            return None
        
        # Get the first matching row
        info_row = stock_info.iloc[0]
        
        # Create metadata
        metadata = StockMetadata(
            stock_id=str(info_row["stock_id"]),
            ticker=str(info_row["stock_id"]),
            stock_name=str(info_row["stock_name"]),
            industry_category=str(info_row["industry_category"]),
            currency="TWD"
        )
        
        # Get price history (last 30 days)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        df_price = self.api.taiwan_stock_daily(
            stock_id=stock_id,
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d")
        )
        
        # Create price history
        price_history = StockPriceHistory()
        
        if df_price is not None and not df_price.empty:
            # Sort by date ascending
            df_price = df_price.sort_values("date")
            
            for _, row in df_price.iterrows():
                record = StockPriceRecord(
                    date=str(row["date"]),
                    Trading_Volume=int(row["Trading_Volume"]),
                    Trading_money=float(row["Trading_money"]),
                    open=float(row["open"]),
                    max=float(row["max"]),
                    min=float(row["min"]),
                    close=float(row["close"]),
                    spread=float(row["spread"]),
                    Trading_turnover=float(row["Trading_turnover"])
                )
                price_history.add_record(record)
        # Create and return Stock object
        return Stock(
            stock_id=stock_id,
            metadata=metadata,
            stock_price_history=price_history
        )
    
    def get_company_detail_US(self, stock_id: str) -> Optional[Stock]:
        """
        Retrieve detailed US stock information from FinMind REST API
        
        Args:
            stock_id: US stock ticker (e.g., "AAPL" for Apple)
        
        Returns:
            Stock object with metadata and price history, or None if not found
        """
        try:
            # Get company metadata from US stock list
            us_collection = self.get_company_list_US()
            metadata_obj = us_collection.get_by_stock_id(stock_id.upper())
            
            if not metadata_obj:
                return None
            
            # Get price history (last 30 days)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            
            headers = {"Authorization": f"Bearer {self.api_token}"} if self.api_token else {}
            parameter = {
                "dataset": "USStockPrice",
                "data_id": stock_id.upper(),
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d")
            }
            
            if self.api_token:
                parameter["token"] = self.api_token
            
            response = requests.get(self.us_api_url, headers=headers, params=parameter, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Create price history
            price_history = StockPriceHistory()
            
            if 'data' in data and data['data']:
                df_price = pd.DataFrame(data['data'])
                
                if not df_price.empty:
                    # Sort by date ascending
                    df_price = df_price.sort_values("date")
                    
                    for _, row in df_price.iterrows():
                        # Map US schema to StockPriceRecord
                        # US API returns: date, stock_id, Close, High, Low, Open, Volume (capitalized)
                        volume = int(row.get("Volume", row.get("volume", 0)))
                        close_price = float(row.get("Close", row.get("close", 0)))
                        high_price = float(row.get("High", row.get("high", 0)))
                        low_price = float(row.get("Low", row.get("low", 0)))
                        open_price = float(row.get("Open", row.get("open", 0)))
                        
                        # Calculate missing fields
                        spread = high_price - low_price
                        trading_money = volume * close_price  # Estimated
                        trading_turnover = 0.0  # Not available in US API
                        
                        record = StockPriceRecord(
                            date=str(row["date"]),
                            Trading_Volume=volume,
                            Trading_money=trading_money,
                            open=open_price,
                            max=high_price,
                            min=low_price,
                            close=close_price,
                            spread=spread,
                            Trading_turnover=trading_turnover
                        )
                        price_history.add_record(record)
            
            # Create and return Stock object
            return Stock(
                stock_id=stock_id.upper(),
                metadata=metadata_obj,
                stock_price_history=price_history
            )
            
        except Exception as e:
            # Log error but return None gracefully
            print(f"Error fetching US stock detail for {stock_id}: {e}")
            return None
    
    def get_company_detail(self, stock_id: str) -> Optional[Stock]:
        """
        Retrieve detailed stock information from FinMind API
        
        Routes to TW or US API based on stock_id format:
        - Numeric stock_id (e.g., "2330") → Taiwan stocks
        - Alphabetic stock_id (e.g., "AAPL") → US stocks
        
        Args:
            stock_id: Stock ID or ticker (e.g., "2330" for TSMC, "AAPL" for Apple)
        
        Returns:
            Stock object with metadata and price history, or None if not found
        """
        # Detect stock type: numeric → TW, alphabetic → US
        if stock_id.isdigit():
            return self.get_company_detail_TW(stock_id)
        else:
            return self.get_company_detail_US(stock_id)
    
    def get_top_movers(self) -> List[Dict]:
        """
        Retrieve top moving stocks from FinMind API
        
        Returns:
            List of top movers with ticker, name, price, change, and changePercent
        """
        # Get today's and yesterday's data for major stocks
        end_date = datetime.now()
        start_date = end_date - timedelta(days=2)
        
        # Get stock list
        collection = self.get_company_list()
        
        movers = []
        
        # Sample major stocks (could be made configurable)
        major_stocks = ["2330", "2317", "2454", "2412", "2308", "6505", "2881", "2882"]
        
        for stock_id in major_stocks:
            stock_metadata = collection.get_by_stock_id(stock_id)
            if not stock_metadata:
                continue
            
            # Get recent price data
            df_price = self.api.taiwan_stock_daily(
                stock_id=stock_id,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d")
            )
            
            if df_price is None or len(df_price) < 2:
                continue
            
            # Sort by date and get last two days
            df_price = df_price.sort_values("date")
            latest = df_price.iloc[-1]
            previous = df_price.iloc[-2] if len(df_price) > 1 else latest
            
            current_price = float(latest["close"])
            previous_price = float(previous["close"])
            change = current_price - previous_price
            change_percent = (change / previous_price * 100) if previous_price > 0 else 0
            
            movers.append({
                "ticker": stock_id,
                "name": stock_metadata.stock_name,
                "price": round(current_price, 2),
                "change": round(change, 2),
                "changePercent": round(change_percent, 2)
            })
        
        # Sort by absolute change percent
        movers.sort(key=lambda x: abs(x["changePercent"]), reverse=True)
        
        return movers[:5]  # Return top 5

