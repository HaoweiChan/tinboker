"""
Unit tests for stock service
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from src.services.stock import StockService
from src.models.stock import CompanyDetail, ChartDataPoint


def _mock_stock_data(ticker="TEST", name="Test Company", price=100.0):
    """Build a mock external stock_data object matching Massive API shape."""
    stats = Mock()
    stats.volume = 1000000
    stats.beta = 1.2
    stats.volatility = 0.3

    metadata = Mock()
    metadata.stock_name = name

    stock_data = Mock()
    stock_data.stock_id = ticker
    stock_data.metadata = metadata
    stock_data.price = price
    stock_data.change = 5.0
    stock_data.changePercent = 5.26
    stock_data.marketCap = 1000000000
    stock_data.revenue = 50000000
    stock_data.pe = 20.0
    stock_data.dividendYield = 2.5
    stock_data.about = "A test company"
    stock_data.stats = stats
    stock_data.stock_price_history = Mock()
    stock_data.stock_price_history.day = []
    return stock_data


def _mock_dcs(stock_data=None):
    """Build a mock DataCollectionService with massive_service stubbed."""
    dcs = Mock()
    dcs.collect_stock_data.return_value = stock_data or _mock_stock_data()
    dcs.massive_service.get_ticker_details.return_value = {
        "icon_url": "https://example.com/icon.png",
        "logo_url": "https://example.com/logo.png",
        "icon_image": "https://example.com/icon.png",
        "logo_image": "https://example.com/logo.png",
    }
    return dcs


class TestStockService:
    """Test stock service operations"""

    @pytest.mark.asyncio
    @patch("src.services.stock.cache_get", new_callable=AsyncMock, return_value=None)
    @patch("src.services.stock.cache_set", new_callable=AsyncMock)
    async def test_get_stock_info(self, mock_cache_set, mock_cache_get):
        """Test getting stock info via mocked external API"""
        dcs = _mock_dcs()
        service = StockService(data_collection_service=dcs)
        stock = await service.get_stock_info_async("TEST")

        assert stock is not None
        assert stock.ticker == "TEST"
        dcs.collect_stock_data.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.services.stock.cache_get", new_callable=AsyncMock, return_value=None)
    @patch("src.services.stock.cache_set", new_callable=AsyncMock)
    async def test_get_stock_basic_info(self, mock_cache_set, mock_cache_get):
        """Test getting basic stock info (no chart data)"""
        dcs = _mock_dcs()
        service = StockService(data_collection_service=dcs)
        info = await service.get_stock_basic_info_async("TEST")

        assert info is not None
        assert info["ticker"] == "TEST"
        assert info["name"] == "Test Company"

    @pytest.mark.asyncio
    @patch("src.services.stock.cache_get", new_callable=AsyncMock, return_value=None)
    @patch("src.services.stock.cache_set", new_callable=AsyncMock)
    async def test_get_sorted_stocks(self, mock_cache_set, mock_cache_get):
        """Test getting sorted stocks list"""
        stock_a = _mock_stock_data(ticker="AAA", name="AAA Company", price=100.0)
        stock_b = _mock_stock_data(ticker="BBB", name="BBB Company", price=50.0)
        dcs = _mock_dcs()
        dcs.get_all_stocks.return_value = [stock_b, stock_a]

        service = StockService(data_collection_service=dcs)
        stocks = await service.get_sorted_stocks_async(sort_by="ticker")

        assert len(stocks) == 2
        assert stocks[0]["ticker"] == "AAA"
        assert stocks[1]["ticker"] == "BBB"

    def test_get_ohlcv_data(self):
        """Test getting OHLCV data from mocked external API"""
        day1 = Mock()
        day1.date = "2024-01-01"
        day1.timestamp = 1704067200000
        day1.close = 102.0
        day1.open = 100.0
        day1.max = 105.0
        day1.min = 95.0
        day1.Trading_Volume = 1000000

        day2 = Mock()
        day2.date = "2024-01-02"
        day2.timestamp = 1704153600000
        day2.close = 105.0
        day2.open = 102.0
        day2.max = 107.0
        day2.min = 100.0
        day2.Trading_Volume = 1200000

        stock_data = _mock_stock_data()
        stock_data.stock_price_history = Mock()
        stock_data.stock_price_history.day = [day1, day2]

        dcs = _mock_dcs(stock_data)
        service = StockService(data_collection_service=dcs)
        ohlcv = service.get_ohlcv_data("TEST")

        assert len(ohlcv) == 2
        assert ohlcv[0].date == "2024-01-01"
        assert ohlcv[1].date == "2024-01-02"

    @pytest.mark.asyncio
    @patch("src.services.stock.cache_get", new_callable=AsyncMock, return_value=None)
    @patch("src.services.stock.cache_set", new_callable=AsyncMock)
    async def test_get_stock_info_returns_none_when_api_fails(self, mock_cache_set, mock_cache_get):
        """Test graceful handling when external API returns nothing"""
        dcs = _mock_dcs()
        dcs.collect_stock_data.return_value = None
        service = StockService(data_collection_service=dcs)
        stock = await service.get_stock_info_async("MISSING")

        assert stock is None
