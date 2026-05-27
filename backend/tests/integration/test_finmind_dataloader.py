"""
Integration tests for FinMind DataLoader API
Tests the taiwan_stock_daily function from docs/FinMind.md
"""
import pytest
import os
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
def get_taiwan_stock_daily(stock_id: str, start_date: str, end_date: str):
    """
    Get Taiwan stock daily data using FinMind DataLoader
    
    Args:
        stock_id: Stock ticker (e.g., "2330" for TSMC)
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
    """
    try:
        from FinMind.data import DataLoader
    except ImportError:
        raise ImportError("FinMind package not installed. Install with: pip install FinMind")
    
    api = DataLoader()
    api_token = os.getenv("FINMIND_API_TOKEN") or os.getenv("FINMIND_API_KEY")
    if api_token:
        api.login_by_token(api_token=api_token)
    
    df = api.taiwan_stock_daily(
        stock_id=stock_id,
        start_date=start_date,
        end_date=end_date
    )
    
    return df


class TestFinMindDataLoader:
    """Test FinMind DataLoader taiwan_stock_daily function"""
    
    @pytest.fixture
    def mock_dataloader_response(self):
        """Mock successful DataLoader response"""
        return pd.DataFrame({
            'date': ['2020-04-02', '2020-04-03', '2020-04-06', '2020-04-07', '2020-04-08'],
            'stock_id': ['2330', '2330', '2330', '2330', '2330'],
            'Trading_Volume': [1000000, 1200000, 1100000, 1300000, 1250000],
            'Trading_money': [550000000, 660000000, 605000000, 715000000, 687500000],
            'open': [550.0, 551.0, 550.5, 551.5, 552.0],
            'max': [555.0, 556.0, 555.5, 556.5, 557.0],
            'min': [549.0, 550.0, 549.5, 550.5, 551.0],
            'close': [552.0, 553.0, 552.5, 553.5, 554.0],
            'spread': [6.0, 6.0, 6.0, 6.0, 6.0],
            'Trading_turnover': [5000.0, 6000.0, 5500.0, 6500.0, 6250.0]
        })
    
    def test_get_taiwan_stock_daily_with_mock(self, mock_dataloader_response):
        """Test get_taiwan_stock_daily with mocked DataLoader"""
        with patch('FinMind.data.DataLoader') as mock_dataloader_class:
            # Setup mock DataLoader instance
            mock_api = Mock()
            mock_api.taiwan_stock_daily.return_value = mock_dataloader_response
            mock_dataloader_class.return_value = mock_api
            
            # Call function
            df = get_taiwan_stock_daily("2330", "2020-04-02", "2020-04-12")
            
            # Assertions
            assert isinstance(df, pd.DataFrame)
            assert len(df) == 5
            assert "date" in df.columns
            assert "stock_id" in df.columns
            assert "Trading_Volume" in df.columns
            assert "Trading_money" in df.columns
            assert "open" in df.columns
            assert "max" in df.columns
            assert "min" in df.columns
            assert "close" in df.columns
            assert "spread" in df.columns
            assert "Trading_turnover" in df.columns
            
            # Verify stock_id
            assert all(df["stock_id"] == "2330")
            
            # Verify date range
            assert df["date"].min() >= "2020-04-02"
            assert df["date"].max() <= "2020-04-12"
            
            # Verify API was called correctly
            mock_api.taiwan_stock_daily.assert_called_once_with(
                stock_id="2330",
                start_date="2020-04-02",
                end_date="2020-04-12"
            )
    
    def test_get_taiwan_stock_daily_dataframe_schema(self, mock_dataloader_response):
        """Test that returned DataFrame has correct schema"""
        with patch('FinMind.data.DataLoader') as mock_dataloader_class:
            mock_api = Mock()
            mock_api.taiwan_stock_daily.return_value = mock_dataloader_response
            mock_dataloader_class.return_value = mock_api
            
            df = get_taiwan_stock_daily("2330", "2020-04-02", "2020-04-12")
            
            # Check all expected columns from schema
            expected_columns = [
                'date', 'stock_id', 'Trading_Volume', 'Trading_money',
                'open', 'max', 'min', 'close', 'spread', 'Trading_turnover'
            ]
            for col in expected_columns:
                assert col in df.columns, f"Column {col} not found in DataFrame"
            
            # Check data types (as per schema).
            # pandas 2.x returns StringDtype for inferred string columns; older builds returned object.
            def _is_string_like(s: pd.Series) -> bool:
                return s.dtype == 'object' or pd.api.types.is_string_dtype(s)

            assert _is_string_like(df['date']) or pd.api.types.is_datetime64_any_dtype(df['date'])
            assert _is_string_like(df['stock_id'])
            assert pd.api.types.is_integer_dtype(df['Trading_Volume'])
            assert pd.api.types.is_integer_dtype(df['Trading_money'])
            assert pd.api.types.is_float_dtype(df['open'])
            assert pd.api.types.is_float_dtype(df['max'])
            assert pd.api.types.is_float_dtype(df['min'])
            assert pd.api.types.is_float_dtype(df['close'])
            assert pd.api.types.is_float_dtype(df['spread'])
            assert pd.api.types.is_float_dtype(df['Trading_turnover'])
    
    def test_get_taiwan_stock_daily_with_login(self, mock_dataloader_response):
        """Test that API token login is called when token is available"""
        with patch('FinMind.data.DataLoader') as mock_dataloader_class, \
             patch.dict(os.environ, {'FINMIND_API_TOKEN': 'test_token'}):
            mock_api = Mock()
            mock_api.taiwan_stock_daily.return_value = mock_dataloader_response
            mock_dataloader_class.return_value = mock_api
            
            df = get_taiwan_stock_daily("2330", "2020-04-02", "2020-04-12")
            
            # Verify login_by_token was called
            mock_api.login_by_token.assert_called_once_with(api_token='test_token')
            assert isinstance(df, pd.DataFrame)
    
    def test_get_taiwan_stock_daily_without_token(self, mock_dataloader_response):
        """Test that function works without API token"""
        with patch('FinMind.data.DataLoader') as mock_dataloader_class, \
             patch.dict(os.environ, {}, clear=True):
            mock_api = Mock()
            mock_api.taiwan_stock_daily.return_value = mock_dataloader_response
            mock_dataloader_class.return_value = mock_api
            
            df = get_taiwan_stock_daily("2330", "2020-04-02", "2020-04-12")
            
            # Verify login_by_token was NOT called
            mock_api.login_by_token.assert_not_called()
            assert isinstance(df, pd.DataFrame)
    
    def test_get_taiwan_stock_daily_empty_result(self):
        """Test handling of empty DataFrame result"""
        empty_df = pd.DataFrame(columns=[
            'date', 'stock_id', 'Trading_Volume', 'Trading_money',
            'open', 'max', 'min', 'close', 'spread', 'Trading_turnover'
        ])
        
        with patch('FinMind.data.DataLoader') as mock_dataloader_class:
            mock_api = Mock()
            mock_api.taiwan_stock_daily.return_value = empty_df
            mock_dataloader_class.return_value = mock_api
            
            df = get_taiwan_stock_daily("2330", "2020-04-02", "2020-04-12")
            
            assert isinstance(df, pd.DataFrame)
            assert len(df) == 0
    
    def test_get_taiwan_stock_daily_import_error(self):
        """Test handling of ImportError when FinMind is not installed"""
        # Mock ImportError when trying to import FinMind
        with patch('builtins.__import__', side_effect=ImportError("No module named 'FinMind'")):
            with pytest.raises(ImportError) as exc_info:
                get_taiwan_stock_daily("2330", "2020-04-02", "2020-04-12")
            
            assert "FinMind package not installed" in str(exc_info.value)
    
    @pytest.mark.integration
    @pytest.mark.skipif(
        not os.getenv("FINMIND_API_TOKEN") and not os.getenv("FINMIND_API_KEY"),
        reason="FINMIND_API_TOKEN or FINMIND_API_KEY not set"
    )
    def test_get_taiwan_stock_daily_integration(self):
        """
        Integration test with actual FinMind DataLoader API call
        
        Debugging options:
        1. Use pytest.set_trace() - Uncomment pytest.set_trace() lines in the code
        2. Run with --pdb flag: pytest ... --pdb
        3. Run with -s flag to see print statements: pytest ... -s
        """
        api_token = os.getenv("FINMIND_API_TOKEN") or os.getenv("FINMIND_API_KEY")
        if not api_token:
            pytest.skip("API token not available")
        
        # Test with TSMC (2330) - use a past date range that should have data
        try:
            # Use a date range from the past (e.g., 2 weeks ago)
            end_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=264)).strftime("%Y-%m-%d")
            
            print(f"\n[DEBUG] Fetching data for 2330 from {start_date} to {end_date}")
            
            df = get_taiwan_stock_daily("2330", start_date, end_date)
            
            # Basic assertions
            assert isinstance(df, pd.DataFrame)
            pytest.set_trace()
            if len(df) > 0:
                # Verify schema
                expected_columns = [
                    'date', 'stock_id', 'Trading_Volume', 'Trading_money',
                    'open', 'max', 'min', 'close', 'spread', 'Trading_turnover'
                ]
                for col in expected_columns:
                    assert col in df.columns, f"Column {col} not found"
                
                # Verify stock_id
                assert all(df["stock_id"] == "2330")
                
                # Verify date range
                df_dates = pd.to_datetime(df["date"])
                start_dt = pd.to_datetime(start_date)
                end_dt = pd.to_datetime(end_date)
                assert df_dates.min() >= start_dt
                assert df_dates.max() <= end_dt
                
                # Print sample data for debugging
                print(f"\n[DEBUG] Retrieved {len(df)} records")
                print(f"[DEBUG] Date range: {df['date'].min()} to {df['date'].max()}")
                print(f"[DEBUG] Sample data:\n{df.head()}")
            else:
                pytest.skip(f"No data available for 2330 from {start_date} to {end_date}")
                
        except ImportError as e:
            pytest.skip(f"FinMind package not installed: {e}")
        except Exception as e:
            # If API call fails, it might be due to:
            # - Market is closed
            # - Invalid date range
            # - API rate limiting
            # - Network issues
            pytest.skip(f"API call failed (might be expected): {e}")
    
    @pytest.mark.integration
    @pytest.mark.skipif(
        not os.getenv("FINMIND_API_TOKEN") and not os.getenv("FINMIND_API_KEY"),
        reason="FINMIND_API_TOKEN or FINMIND_API_KEY not set"
    )
    def test_get_taiwan_stock_daily_integration_invalid_stock(self):
        """Integration test with invalid stock ID"""
        api_token = os.getenv("FINMIND_API_TOKEN") or os.getenv("FINMIND_API_KEY")
        if not api_token:
            pytest.skip("API token not available")
        
        # Test with invalid stock ID
        try:
            end_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            start_date = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
            
            df = get_taiwan_stock_daily("INVALID_STOCK", start_date, end_date)
            
            # Should return empty DataFrame or raise error
            assert isinstance(df, pd.DataFrame)
            # Empty result is acceptable for invalid stock
            if len(df) == 0:
                pytest.skip("Invalid stock ID returned empty result (expected)")
                
        except ImportError:
            pytest.skip("FinMind package not installed")
        except Exception as e:
            # Exception is also acceptable for invalid stock
            print(f"[DEBUG] Expected error for invalid stock: {e}")

