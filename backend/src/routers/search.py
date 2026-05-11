"""
Search API router
"""
from fastapi import APIRouter, Query
from src.schemas.search import SearchResponse, SearchResultItem
from src.services.stock import StockService
from src.services.podcast import PodcastService
from src.cache.cdn_cache import cdn_cache_trending
import asyncio
import logging
import re

router = APIRouter(prefix="/api/search", tags=["search"])

# Initialize services
stock_service = StockService()
podcast_service = PodcastService()

@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(default=5, ge=1, le=20, description="Max results per category")
):
    """
    Unified search endpoint.
    Returns results for stocks, podcasts, episodes, and tags matching the query.
    """
    if not q.strip():
        return SearchResponse()
        
    query = q.strip()
    
    # Execute searches in parallel
    results = await asyncio.gather(
        stock_service.search_stocks(query, limit),
        podcast_service.search_podcasts(query, limit),
        podcast_service.search_episodes(query, limit),
        podcast_service.search_tags(query, limit),
        return_exceptions=True
    )
    
    # Process results
    stocks_result = results[0] if not isinstance(results[0], Exception) else []
    podcasts_result = results[1] if not isinstance(results[1], Exception) else []
    episodes_result = results[2] if not isinstance(results[2], Exception) else []
    tags_result = results[3] if not isinstance(results[3], Exception) else []
    
    # Log errors if any
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            print(f"Search error in category {i}: {res}")

    return SearchResponse(
        stocks=stocks_result,
        podcasts=podcasts_result,
        episodes=episodes_result,
        tags=tags_result
    )

@router.get("/suggest", response_model=SearchResponse)
async def suggest(
    q: str = Query(..., min_length=1, description="Prefix query"),
    limit: int = Query(default=8, ge=1, le=20)
):
    """
    Fast typeahead suggestions.
    Returns instant suggestions for autocomplete. Target <50ms.
    """
    if not q.strip():
        return SearchResponse()
    
    from src.services.suggestion_index import SuggestionIndex
    index = SuggestionIndex()

    # Fall back to full search if index hasn't been built yet
    if not index.is_initialized:
        asyncio.create_task(build_search_index())
        return await search(q=q, limit=limit)

    suggestions = index.suggest(q.strip(), limit=limit)

    return SearchResponse(
        stocks=[s for s in suggestions if s.type == "stock"],
        podcasts=[s for s in suggestions if s.type == "podcast"],
        episodes=[s for s in suggestions if s.type == "episode"],
        tags=[s for s in suggestions if s.type == "tag"]
    )

async def init_search_index():
    """Initialize search index — called from main.py startup."""
    asyncio.create_task(build_search_index())

async def build_search_index():
    """Build the in-memory suggestion index from all sources."""
    from src.services.suggestion_index import SuggestionIndex
    from src.schemas.search import SearchResultItem
    
    logger = logging.getLogger(__name__)
    logger.info("Building search index...")
    index = SuggestionIndex()
    
    try:
        # 1. Fetch all stocks (cached version is fast)
        stocks = await stock_service.get_sorted_stocks_async(limit=2000)
        for stock in stocks:
            item = SearchResultItem(
                id=f"stock-{stock.get('ticker')}",
                type="stock",
                title=stock.get("ticker"),
                subtitle=stock.get("name"),
                link=f"/stock/{stock.get('ticker')}",
                icon_url=None, # Frontend handles stock icons
                metadata={"price": stock.get("price"), "change_percent": stock.get("change_percent")}
            )
            # Index by Ticker, Full Name, and Short Name (in parentheses)
            keywords = [stock.get("ticker"), stock.get("name")]
            # Extract short name from parentheses e.g. "聯華電子股份有限公司 (聯電)" -> "聯電"
            name = stock.get("name") or ""
            short_names = re.findall(r'[（(]([^)）]+)[)）]', name)
            keywords.extend(short_names)
            await index.add_item(item, keywords=keywords)
            
        # 2. Fetch podcasts
        podcasts = await podcast_service.get_all_podcasts(limit=1000)
        for podcast in podcasts:
            item = SearchResultItem(
                id=f"podcast-{podcast.id}",
                type="podcast",
                title=podcast.name,
                subtitle=f"{podcast.episode_count} episodes",
                link=f"/podcaster/{podcast.name}",
                icon_url=podcast.image_url
            )
            await index.add_item(item, keywords=[podcast.name])
            
        # 3. Fetch tags
        tags = await podcast_service.get_all_tags()
        for tag in tags:
            tag_name = tag.get("name")
            item = SearchResultItem(
                id=f"tag-{tag.get('id')}",
                type="tag",
                title=tag_name,
                subtitle=f"{tag.get('episode_count')} episodes",
                link=f"/tag/{tag_name}"
            )
            await index.add_item(item, keywords=[tag_name])
            
        index.mark_initialized()
        logger.info("Search index built successfully.")
        
    except Exception as e:
        logger.error(f"Failed to build search index: {e}")

@router.get("/popular", response_model=SearchResponse)
@cdn_cache_trending
async def get_popular():
    """
    Get popular/trending items for search suggestions.
    Returns categorized popular items (Stocks and Podcasts).
    
    CDN Cache: 1 hour
    """
    from src.services.trending import TrendingService
    trending_service = TrendingService(podcast_service=podcast_service, stock_service=stock_service)
    
    # Fetch trending data in parallel
    trending_stocks, active_podcasts, all_tags = await asyncio.gather(
        trending_service.get_trending_stocks(days=7, limit=5),
        trending_service.get_active_podcasters(limit=5),
        podcast_service.get_all_tags(),
        return_exceptions=True
    )
    
    stocks = trending_stocks if not isinstance(trending_stocks, Exception) else []
    podcasts = active_podcasts if not isinstance(active_podcasts, Exception) else []
    
    # Process tags (simple sort by episode count)
    tags = []
    if not isinstance(all_tags, Exception) and all_tags:
        # Sort by episode count desc
        sorted_tags = sorted(all_tags, key=lambda x: x.get('episode_count', 0), reverse=True)
        # Convert to SearchResultItem
        for tag in sorted_tags[:8]:
            tags.append(SearchResultItem(
                id=f"tag-{tag.get('id')}",
                type="tag",
                title=tag.get('name'),
                subtitle=f"{tag.get('episode_count')} episodes",
                link=f"/tag/{tag.get('name')}"
            ))

    return SearchResponse(
        stocks=stocks,
        podcasts=podcasts,
        episodes=[], # Trending episodes not yet implemented/required
        tags=tags
    )
