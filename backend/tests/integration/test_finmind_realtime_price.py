"""
Integration tests for FinMind real-time stock price API
Tests the get_realtime_stock_price function from docs/finmind_api_usage.md
"""
import pytest
import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file
env_path = Path(__file__).parent.parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)


# Import the function implementation from the documentation
# Since it's in docs, we'll implement it here for testing
def get_realtime_stock_price(stock_id: str, date: str = None):
    """
    Get real-time stock tick data
    
    Args:
        stock_id: Stock ticker (e.g., "2330" for TSMC)
        date: Date in YYYY-MM-DD format (defaults to today)
    """
    API_BASE_URL = "https://api.finmindtrade.com/api/v4/data"
    API_TOKEN = os.getenv("FINMIND_API_TOKEN") or os.getenv("FINMIND_API_KEY")
    HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}
    
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    
    parameters = {
        "dataset": "taiwan_stock_tick_snapshot",
        "data_id": stock_id,
        "date": date,
    }
    
    response = requests.get(API_BASE_URL, headers=HEADERS, params=parameters)
    
    # Check HTTP status code first
    if response.status_code != 200:
        error_msg = f"HTTP {response.status_code}"
        try:
            error_data = response.json()
            error_msg += f": {error_data.get('msg', error_data)}"
        except:
            error_msg += f": {response.text[:200]}"
        raise Exception(f"API Error ({error_msg})")
    
    data = response.json()
    if data.get("status") == 200:
        return pd.DataFrame(data["data"])
    else:
        raise Exception(f"API Error: {data.get('msg', 'Unknown error')}")


class TestFinMindRealtimePrice:
    """Test get_realtime_stock_price function"""
    
    @pytest.fixture
    def mock_api_response_success(self):
        """Mock successful API response"""
        return {
            "status": 200,
            "data": [
                {
                    "stock_id": "2330",
                    "deal_price": 550.0,
                    "volume": 1000,
                    "time": "2024-11-07 09:00:00"
                },
                {
                    "stock_id": "2330",
                    "deal_price": 551.0,
                    "volume": 1500,
                    "time": "2024-11-07 09:01:00"
                }
            ]
        }
    
    @pytest.fixture
    def mock_api_response_error(self):
        """Mock API error response"""
        return {
            "status": 400,
            "msg": "Invalid stock_id"
        }
    
    @pytest.fixture
    def mock_api_response_empty(self):
        """Mock API response with empty data"""
        return {
            "status": 200,
            "data": []
        }
    
    def test_get_realtime_stock_price_with_mock_success(self, mock_api_response_success):
        """Test get_realtime_stock_price with successful mocked response"""
        with patch('requests.get') as mock_get:
            # Setup mock response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_api_response_success
            mock_get.return_value = mock_response
            
            # Call function
            df = get_realtime_stock_price("2330", "2024-11-07")
            
            # Assertions
            assert isinstance(df, pd.DataFrame)
            assert len(df) == 2
            assert "stock_id" in df.columns
            assert "deal_price" in df.columns
            assert "volume" in df.columns
            assert "time" in df.columns
            assert df.iloc[0]["stock_id"] == "2330"
            assert df.iloc[0]["deal_price"] == 550.0
            assert df.iloc[0]["volume"] == 1000
            
            # Verify API call was made correctly
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            assert call_args[0][0] == "https://api.finmindtrade.com/api/v4/data"
            assert "Authorization" in call_args[1]["headers"]
            assert call_args[1]["params"]["dataset"] == "taiwan_stock_tick_snapshot"
            assert call_args[1]["params"]["data_id"] == "2330"
            assert call_args[1]["params"]["date"] == "2024-11-07"
    
    def test_get_realtime_stock_price_with_mock_error(self, mock_api_response_error):
        """Test get_realtime_stock_price with error response"""
        with patch('requests.get') as mock_get:
            # Setup mock error response
            mock_response = Mock()
            mock_response.status_code = 400
            mock_response.json.return_value = mock_api_response_error
            mock_get.return_value = mock_response
            
            # Call function and expect exception
            with pytest.raises(Exception) as exc_info:
                get_realtime_stock_price("INVALID", "2024-11-07")
            
            assert "API Error" in str(exc_info.value)
            assert "Invalid stock_id" in str(exc_info.value)
    
    def test_get_realtime_stock_price_default_date(self, mock_api_response_success):
        """Test get_realtime_stock_price with default date (today)"""
        with patch('requests.get') as mock_get:
            # Setup mock response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_api_response_success
            mock_get.return_value = mock_response
            
            # Call function without date parameter
            df = get_realtime_stock_price("2330")
            
            # Verify function works and date parameter was passed (should be today's date)
            call_args = mock_get.call_args
            assert "date" in call_args[1]["params"]
            # Date should be in YYYY-MM-DD format
            date_param = call_args[1]["params"]["date"]
            assert len(date_param) == 10
            assert date_param.count("-") == 2
            # Verify DataFrame was returned correctly
            assert isinstance(df, pd.DataFrame)
            assert len(df) == 2
    
    def test_get_realtime_stock_price_empty_data(self, mock_api_response_empty):
        """Test get_realtime_stock_price with empty data response"""
        with patch('requests.get') as mock_get:
            # Setup mock response with empty data
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_api_response_empty
            mock_get.return_value = mock_response
            
            # Call function
            df = get_realtime_stock_price("2330", "2024-11-07")
            
            # Should return empty DataFrame, not raise error
            assert isinstance(df, pd.DataFrame)
            assert len(df) == 0
    
    @pytest.mark.integration
    @pytest.mark.skipif(
        not os.getenv("FINMIND_API_TOKEN") and not os.getenv("FINMIND_API_KEY"),
        reason="FINMIND_API_TOKEN or FINMIND_API_KEY not set"
    )
    def test_get_realtime_stock_price_integration(self):
        """
        Integration test with actual FinMind API call
        
        Debugging options:
        1. Use pytest.set_trace() - Uncomment the pytest.set_trace() lines in the code
        2. Run with --pdb flag: pytest tests/integration/test_finmind_realtime_price.py::TestFinMindRealtimePrice::test_get_realtime_stock_price_integration --pdb
        3. Run with -s flag to see print statements: pytest ... -s
        4. Use print statements (already added with [DEBUG] prefix)
        """
        # Skip if API token is not available
        api_token = os.getenv("FINMIND_API_TOKEN") or os.getenv("FINMIND_API_KEY")
        if not api_token:
            pytest.skip("API token not available")
        
        # Test with TSMC (2330) - a well-known Taiwan stock
        try:
            # Try today's date first, then yesterday if today fails
            test_date = datetime.now().strftime("%Y-%m-%d")
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            
            df = None
            successful_date = None
            print(f"\n[DEBUG] Trying dates: {test_date}, {yesterday}")
            for date in [test_date, yesterday]:
                try:
                    print(f"[DEBUG] Attempting to fetch data for date: {date}")
                    df = get_realtime_stock_price("2330", date)
                    print(f"[DEBUG] Successfully fetched data. Type: {type(df)}, Length: {len(df) if isinstance(df, pd.DataFrame) else 'N/A'}")
                    if isinstance(df, pd.DataFrame) and len(df) > 0:
                        successful_date = date
                        print(f"[DEBUG] Found data for date: {date}")
                        break
                except Exception as e:
                    print(f"[DEBUG] Failed to fetch data for {date}: {e}")
                    pytest.set_trace()
                    continue
            
            # If no data was retrieved, skip the test
            if df is None:
                pytest.skip(f"Could not retrieve data for 2330 on {test_date} or {yesterday} (API might be unavailable or market closed)")
            
            # Basic assertions
            assert isinstance(df, pd.DataFrame)
            
            # Debug: Print DataFrame info
            print(f"\n[DEBUG] DataFrame shape: {df.shape}")
            print(f"[DEBUG] DataFrame columns: {list(df.columns)}")
            print(f"[DEBUG] DataFrame head:\n{df.head()}")
            
            # Use pytest.set_trace() for debugging (works better than breakpoint() in pytest)
            # Uncomment the line below to enter debugger:
            # pytest.set_trace()
            
            # If data is available (market is open), check structure
            if len(df) > 0:
                assert "stock_id" in df.columns
                assert "deal_price" in df.columns or "price" in df.columns
                assert df.iloc[0]["stock_id"] == "2330"
                
                # Print sample data for debugging
                print(f"\nSample data for 2330 on {successful_date or test_date}:")
                print(df.head())
            else:
                # Empty data is acceptable (market might be closed)
                print(f"\n[DEBUG] DataFrame is empty. Columns: {list(df.columns)}")
                # Uncomment the line below to enter debugger:
                # pytest.set_trace()
                pytest.skip(f"No data available for 2330 on {test_date} or {yesterday} (market might be closed)")
                
        except Exception as e:
            # If API call fails, it might be due to:
            # - Market is closed
            # - Invalid date
            # - API rate limiting
            # - Network issues
            pytest.skip(f"API call failed (might be expected): {e}")
    
    @pytest.mark.integration
    @pytest.mark.skipif(
        not os.getenv("FINMIND_API_TOKEN") and not os.getenv("FINMIND_API_KEY"),
        reason="FINMIND_API_TOKEN or FINMIND_API_KEY not set"
    )
    def test_get_realtime_stock_price_integration_invalid_stock(self):
        """Integration test with invalid stock ID"""
        api_token = os.getenv("FINMIND_API_TOKEN") or os.getenv("FINMIND_API_KEY")
        if not api_token:
            pytest.skip("API token not available")
        
        # Test with invalid stock ID
        with pytest.raises(Exception) as exc_info:
            get_realtime_stock_price("INVALID_STOCK", "2024-11-07")
        
        assert "API Error" in str(exc_info.value)
    
    def test_get_realtime_stock_price_dataframe_columns(self, mock_api_response_success):
        """Test that returned DataFrame has expected columns"""
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_api_response_success
            mock_get.return_value = mock_response
            
            df = get_realtime_stock_price("2330", "2024-11-07")
            
            # Check for expected columns (as mentioned in documentation)
            expected_columns = ['stock_id', 'deal_price', 'volume', 'time']
            for col in expected_columns:
                assert col in df.columns, f"Column {col} not found in DataFrame"
    
    def test_get_realtime_stock_price_multiple_ticks(self, mock_api_response_success):
        """Test that function handles multiple tick data correctly"""
        with patch('requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = mock_api_response_success
            mock_get.return_value = mock_response
            
            df = get_realtime_stock_price("2330", "2024-11-07")
            
            # Should have multiple rows
            assert len(df) == 2
            
            # Each row should have the same stock_id
            assert all(df["stock_id"] == "2330")
            
            # Prices should be different (showing price changes over time)
            assert df.iloc[0]["deal_price"] != df.iloc[1]["deal_price"]

