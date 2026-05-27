"""
Unit tests for news service
"""
import pytest
from src.services.news import NewsService
from src.database.news_db import create_news


class TestNewsService:
    """Test news service operations"""

    @pytest.mark.asyncio
    async def test_get_news_by_id(self, test_db, sample_news_data):
        """Test getting news by ID"""
        create_news(news_id="test-news", **sample_news_data)
        service = NewsService()
        news = await service.get_news_by_id("test-news")
        assert news is not None
        assert news.id == "test-news"
        assert news.title == "Test Earnings Report"

    @pytest.mark.asyncio
    async def test_get_sorted_news(self, test_db, sample_news_data):
        """Test getting sorted news"""
        create_news(news_id="news-1", **sample_news_data)

        sample_news_data["title"] = "Second News"
        sample_news_data["date"] = 1704153600000
        create_news(news_id="news-2", **sample_news_data)

        service = NewsService()
        news_list = await service.get_sorted_news(sort_by="date")
        assert len(news_list) == 2
        assert news_list[0].date >= news_list[1].date

    @pytest.mark.asyncio
    async def test_create_news(self, test_db, sample_news_data):
        """Test creating news"""
        service = NewsService()
        news_id = await service.create_news(**sample_news_data)
        assert news_id is not None

        news = await service.get_news_by_id(news_id)
        assert news is not None
        assert news.title == "Test Earnings Report"

    @pytest.mark.asyncio
    async def test_update_news(self, test_db, sample_news_data):
        """Test updating news"""
        create_news(news_id="test-news", **sample_news_data)
        service = NewsService()
        result = await service.update_news(
            news_id="test-news",
            title="Updated Title",
            description="Updated Description",
        )
        assert result is True

        news = await service.get_news_by_id("test-news")
        assert news.title == "Updated Title"
        assert news.description == "Updated Description"

    @pytest.mark.asyncio
    async def test_delete_news(self, test_db, sample_news_data):
        """Test deleting news"""
        create_news(news_id="test-news", **sample_news_data)
        service = NewsService()
        result = await service.delete_news("test-news")
        assert result is True

        news = await service.get_news_by_id("test-news")
        assert news is None

    def test_get_news_by_tickers(self, test_db, sample_news_data):
        """Test getting news by tickers"""
        create_news(news_id="news-1", **sample_news_data)

        sample_news_data["related_tickers"] = ["AAPL"]
        create_news(news_id="news-2", **sample_news_data)

        service = NewsService()
        news_list = service.get_news_by_tickers(["TEST", "NVDA"])
        assert len(news_list) == 1
        assert news_list[0].id == "news-1"
