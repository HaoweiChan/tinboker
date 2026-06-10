"""
News API router
"""
from fastapi import APIRouter, HTTPException, Path, Query, Depends
from typing import List
from src.services.news import NewsService
from src.models.news import StockEvent
from src.cache.cdn_cache import cdn_cache_news
from src.auth.admin_auth import get_content_write_access, AdminAccess

router = APIRouter(prefix="/api/news", tags=["news"])

# Initialize service
news_service = NewsService()


@router.get("", response_model=List[StockEvent])
@cdn_cache_news
async def get_sorted_news(sort_by: str = Query(default="date", description="Sort field")):
    """
    Get sorted news list
    
    Query params:
    - sort_by: Sort field (date, created_at, updated_at, title)
    
    CDN Cache: 10 minutes
    """
    news_list = await news_service.get_sorted_news(sort_by=sort_by)
    return news_list


@router.get("/{news_id}", response_model=StockEvent)
@cdn_cache_news
async def get_news_by_id(news_id: str = Path(..., description="News ID")):
    """
    Get news by ID
    
    Returns complete news event with related tickers
    
    CDN Cache: 10 minutes
    """
    news = await news_service.get_news_by_id(news_id)
    if not news:
        raise HTTPException(status_code=404, detail=f"News {news_id} not found")
    return news


@router.post("/fetch/{ticker}", response_model=dict)
async def fetch_news_from_massive(
    ticker: str = Path(..., description="Stock ticker symbol"),
    limit: int = Query(default=10, ge=1, le=50, description="Maximum number of articles to fetch (1-50)"),
    _admin: AdminAccess = Depends(get_content_write_access),
):
    """
    Fetch news from Massive API for a ticker and save to database
    
    Args:
        ticker: Stock ticker symbol (e.g., "NVDA", "AAPL")
        limit: Maximum number of articles to fetch (default: 10)
        
    Returns:
        Dict with count of news articles fetched and their IDs
    """
    try:
        # Note: fetch_and_save_news_from_massive uses create_news internally which invalidates cache
        news_ids = news_service.fetch_and_save_news_from_massive(ticker.upper(), limit=limit)
        return {
            "ticker": ticker.upper(),
            "count": len(news_ids),
            "news_ids": news_ids,
            "message": f"Successfully fetched and saved {len(news_ids)} news articles"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching news: {str(e)}")
