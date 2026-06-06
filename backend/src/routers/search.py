"""
Search API router
"""
from fastapi import APIRouter, Query
from src.schemas.search import SearchResponse, SearchResultItem
from src.services.stock import StockService
from src.services.podcast import PodcastService
from src.cache.cdn_cache import cdn_cache_trending, cdn_cached
from src.utils.market import infer_market
import asyncio
import logging
import re

router = APIRouter(prefix="/api/search", tags=["search"])

# Initialize services
stock_service = StockService()
podcast_service = PodcastService()

@router.get("", response_model=SearchResponse)
# Short edge cache only. These results are query-driven and reflect live prices /
# newly-indexed stocks, so they must NOT inherit the long default TTL the `/api/*`
# Cloudflare cache rule applies to responses that send no Cache-Control header.
@cdn_cached(s_maxage=60, max_age=0, stale=30)
async def search(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(default=5, ge=1, le=20, description="Max results per category")
):
    """
    Unified search endpoint.
    Returns results for stocks, podcasts, episodes, and tags matching the query.

    CDN Cache: 60s edge (short — autocomplete/search must stay fresh).
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
# Short edge cache only. Without an explicit Cache-Control header the `/api/*`
# Cloudflare cache rule edge-cached typeahead for ~24h (stale prices / missing new
# stocks). 60s gives the edge enough to absorb typeahead bursts while staying fresh.
@cdn_cached(s_maxage=60, max_age=0, stale=30)
async def suggest(
    q: str = Query(..., min_length=1, description="Prefix query"),
    limit: int = Query(default=8, ge=1, le=20)
):
    """
    Fast typeahead suggestions.
    Returns instant suggestions for autocomplete. Target <50ms.

    CDN Cache: 60s edge (short — must reflect live prices / new stocks).
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

def _has_cjk(text) -> bool:
    """True if the text contains a CJK character (i.e. a real Chinese name)."""
    if not text:
        return False
    return any("㐀" <= ch <= "鿿" or "豈" <= ch <= "﫿" for ch in text)


def _load_stock_translations(limit: int = 20000):
    """Read translatable stock rows (blocking SQLAlchemy). Run off the event loop.

    Returns lightweight dicts so the caller never touches detached ORM instances.
    """
    from src.database.postgres import get_session
    from src.services.translation_service import TranslationService

    rows = []
    for session in get_session():
        for t in TranslationService(session).get_translatable_rows(limit=limit):
            rows.append({
                "ticker": t.ticker,
                "market": t.market,
                "name_en": t.name_en,
                "name_zh_tw": t.name_zh_tw,
                "name_preference": getattr(t, "name_preference", None) or "auto",
                "aliases": t.aliases or [],
            })
        break
    return rows


async def build_search_index():
    """Build the in-memory suggestion index from all sources."""
    from src.services.suggestion_index import SuggestionIndex
    from src.schemas.search import SearchResultItem

    logger = logging.getLogger(__name__)
    logger.info("Building search index...")
    index = SuggestionIndex()

    try:
        # 1. Fetch all stocks (cached version is fast).
        # NOTE: this universe comes from the Massive API and is US-only with English
        # names. TW stocks (e.g. 2330 / 台積電) and Chinese names are added in step 1b
        # from the stock_translations table.
        stocks = await stock_service.get_sorted_stocks_async(limit=2000)

        # Track which tickers the Massive universe already indexed, so step 1b only
        # enriches existing items (with zh-TW keywords) or adds genuinely new TW ones.
        seen_tickers = set()
        for stock in stocks:
            ticker = stock.get("ticker")
            if not ticker:
                continue
            seen_tickers.add(ticker.upper())
            market = infer_market(ticker)
            item = SearchResultItem(
                id=f"stock-{ticker}",
                type="stock",
                title=ticker,
                subtitle=stock.get("name"),
                link=f"/stock/{ticker}",
                market=market,
                metadata={"price": stock.get("price"), "change_percent": stock.get("change_percent")}
            )
            # Index by Ticker, Full Name, and Short Name (in parentheses)
            keywords = [stock.get("ticker"), stock.get("name")]
            # Extract short name from parentheses e.g. "聯華電子股份有限公司 (聯電)" -> "聯電"
            name = stock.get("name") or ""
            short_names = re.findall(r'[（(]([^)）]+)[)）]', name)
            keywords.extend(short_names)
            await index.add_item(item, keywords=keywords)

        # 1b. Enrich/extend the stock index from stock_translations (zh-TW names,
        # numeric TW tickers, curated aliases). This is what lets 台積電/台積/台/2330
        # surface TSMC; without it the index is US-English-only.
        try:
            translations = await asyncio.to_thread(_load_stock_translations)
        except Exception as e:
            translations = []
            logger.warning(f"Search index: failed to load stock translations: {e}")

        for tr in translations:
            ticker = tr.get("ticker")
            if not ticker:
                continue
            zh = tr.get("name_zh_tw")
            en = tr.get("name_en")
            pref = tr.get("name_preference") or "auto"
            # Show the zh-TW name only when it's a real CJK name and not forced English.
            show_zh = _has_cjk(zh) and pref != "en"
            display = zh if show_zh else (en or ticker)

            # All searchable forms: ticker, both names, and curated aliases.
            keywords = [ticker, en, zh, *tr.get("aliases", [])]

            if ticker.upper() in seen_tickers:
                # Already indexed from Massive — just add the extra (zh-TW/alias) keywords.
                await index.add_keywords(f"stock-{ticker}", keywords)
            else:
                market = (tr.get("market") or "").upper() or infer_market(ticker)
                item = SearchResultItem(
                    id=f"stock-{ticker}",
                    type="stock",
                    title=ticker,
                    subtitle=display,
                    link=f"/stock/{ticker}",
                    market=market,
                    metadata={"price": None, "change_percent": None},
                )
                await index.add_item(item, keywords=keywords)
                seen_tickers.add(ticker.upper())

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
