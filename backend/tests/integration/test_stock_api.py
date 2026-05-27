"""
Integration tests for stock API endpoints
"""
import os
import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.database.stock_db import create_or_update_stock, add_price_history


@pytest.fixture
def client(test_db):
    """Create test client"""
    return TestClient(app)


# These endpoints route through data_collection_service which calls Massive API
# before checking local DB. Without a Massive key, lookups return 404 even when
# rows exist in the local DB. Skip until the route gains a local-first fallback
# (matches the FinMind dataloader skipif pattern).
_REQUIRES_MASSIVE = pytest.mark.skipif(
    not os.getenv("MASSIVE_API_KEY"),
    reason="MASSIVE_API_KEY not set; stock_api routes go through Massive first",
)


@_REQUIRES_MASSIVE
class TestStockAPI:
    """Test stock API endpoints"""

    def test_get_sorted_stocks(self, client, test_db):
        """Test GET /api/stocks"""
        # Create test stocks
        create_or_update_stock(
            ticker="AAA",
            name="AAA Company",
            price=100.0,
            change=5.0,
            change_percent=5.26,
            market_cap=1000000000,
            revenue=50000000,
            pe=20.0,
            dividend_yield=2.5,
            about="AAA company",
            volume=1000000,
            beta=1.2,
            volatility=0.3,
        )
        create_or_update_stock(
            ticker="BBB",
            name="BBB Company",
            price=50.0,
            change=0.0,
            change_percent=0.0,
            market_cap=500000000,
            revenue=25000000,
            pe=15.0,
            dividend_yield=1.0,
            about="BBB company",
            volume=500000,
            beta=1.0,
            volatility=0.2,
        )
        
        response = client.get("/api/stocks?sort_by=ticker")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["ticker"] == "AAA"
        assert data[1]["ticker"] == "BBB"
    
    def test_get_stock_by_ticker(self, client, test_db):
        """Test GET /api/stocks/{ticker}"""
        create_or_update_stock(
            ticker="TEST",
            name="Test Company",
            price=100.0,
            change=5.0,
            change_percent=5.26,
            market_cap=1000000000,
            revenue=50000000,
            pe=20.0,
            dividend_yield=2.5,
            about="Test company",
            volume=1000000,
            beta=1.2,
            volatility=0.3,
        )
        add_price_history("TEST", 1704067200000, "2024-01-01", 100.0, 105.0, 95.0, 102.0, 1000000)
        
        response = client.get("/api/stocks/TEST")
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "TEST"
        assert data["name"] == "Test Company"
        assert "chartData" in data
        assert len(data["chartData"]) == 1
    
    def test_get_stock_not_found(self, client, test_db):
        """Test GET /api/stocks/{ticker} with non-existent ticker"""
        response = client.get("/api/stocks/NONEXISTENT")
        assert response.status_code == 404
    
    def test_get_stock_basic_info(self, client, test_db):
        """Test GET /api/stocks/{ticker}/basic"""
        create_or_update_stock(
            ticker="TEST",
            name="Test Company",
            price=100.0,
            change=5.0,
            change_percent=5.26,
            market_cap=1000000000,
            revenue=50000000,
            pe=20.0,
            dividend_yield=2.5,
            about="Test company",
            volume=1000000,
            beta=1.2,
            volatility=0.3,
        )
        
        response = client.get("/api/stocks/TEST/basic")
        assert response.status_code == 200
        data = response.json()
        assert data["ticker"] == "TEST"
        assert data["name"] == "Test Company"
        # Should not include chartData in basic info
        assert "chartData" not in data

