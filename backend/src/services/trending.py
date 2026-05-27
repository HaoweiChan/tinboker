"""
Trending service for aggregating trending data from platform activity
"""
import logging
import json
import asyncio
from datetime import datetime, timedelta
from typing import List, Optional, Dict
from collections import Counter

from src.services.podcast import PodcastService
from src.services.stock import StockService
from src.cache.redis_client import cache_get, cache_set, get_redis
from src.schemas.search import SearchResultItem
from src.database.postgres import SessionLocal, init_engine
from src.database.models import StockTranslation


def _infer_market(ticker: str) -> str:
    return "TW" if ticker.split(".")[0].isdigit() else "US"

logger = logging.getLogger(__name__)

# Cache TTL: 1 hour for trending data as it doesn't change second-by-second
TRENDING_CACHE_TTL = 3600
# Cache TTL for translations (24 hours - translations rarely change)
TRANSLATION_CACHE_TTL = 86400

class TrendingService:
    """Service for aggregating trending stocks and podcasters"""

    def __init__(self, podcast_service: Optional[PodcastService] = None, stock_service: Optional[StockService] = None):
        self.podcast_service = podcast_service or PodcastService()
        self.stock_service = stock_service or StockService()

    async def _get_translations_batch(self, tickers: List[str]) -> Dict[str, str]:
        """
        Batch fetch Chinese translations for tickers with caching.
        Returns dict mapping ticker -> Chinese name (or empty string if not found)
        """
        if not tickers:
            return {}
        # Check cache first
        cache_key = "translations:batch:" + ":".join(sorted(tickers))
        cached = await cache_get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass
        # Fetch from database
        translations = {}
        try:
            init_engine()
            db = SessionLocal()
            try:
                for ticker in tickers:
                    # Determine market based on ticker format
                    clean_ticker = ticker.split('.')[0]
                    market = "TW" if clean_ticker.isdigit() else "US"
                    result = db.query(StockTranslation).filter(
                        StockTranslation.ticker == clean_ticker.upper(),
                        StockTranslation.market == market
                    ).first()
                    if result and result.name_zh_tw:
                        translations[ticker] = result.name_zh_tw
                    else:
                        translations[ticker] = ""
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"Failed to fetch translations: {e}")
        # Cache the results
        try:
            await cache_set(cache_key, json.dumps(translations), TRANSLATION_CACHE_TTL)
        except Exception:
            pass
        return translations

    async def get_trending_stocks(self, days: int = 7, limit: int = 5) -> List[SearchResultItem]:
        """
        Get trending stocks based on mentions in recent episodes
        
        Args:
            days: Number of days to look back
            limit: Maximum number of results
            
        Returns:
            List of SearchResultItem objects
        """
        cache_key = f"trending:stocks:{days}:{limit}:v4"
        cached = await cache_get(cache_key)
        if cached:
            try:
                data = json.loads(cached)
                return [SearchResultItem(**item) for item in data]
            except Exception as e:
                logger.warning(f"Failed to deserialize trending stocks cache: {e}")
        # 1. Fetch recent episodes
        now = datetime.now()
        cutoff_time = now - timedelta(days=days)
        cutoff_timestamp = int(cutoff_time.timestamp() * 1000)
        recent_episodes = await self.podcast_service.get_recent_episodes(limit=500, enrich_content=False)
        ticker_counts = Counter()
        for episode in recent_episodes:
            if (episode.created_time or 0) < cutoff_timestamp:
                continue
            if episode.related_tickers:
                for ticker in episode.related_tickers:
                    ticker_counts[ticker] += 1
        # Get top N tickers
        top_tickers = [ticker for ticker, count in ticker_counts.most_common(limit)]
        if not top_tickers:
            return []
        # Batch fetch translations for Chinese names
        translations = await self._get_translations_batch(top_tickers)
        results = []

        async def fetch_stock_for_trending(ticker):
            """Optimized: fetch basic info and chart data separately"""
            try:
                # Fetch basic info (fast, cached separately)
                basic_info = await self.stock_service.get_stock_basic_info_async(ticker)
                # Fetch chart data for sparkline (uses existing cached full stock data)
                # Check if we have cached chart data first
                chart_cache_key = f"stock:{ticker.upper()}:info:ALL:daily"
                chart_cached = await cache_get(chart_cache_key)
                sparkline = []
                change_percent_30d = 0.0
                if chart_cached:
                    try:
                        chart_data = json.loads(chart_cached)
                        if chart_data.get("chartData"):
                            sorted_data = sorted(chart_data["chartData"], key=lambda x: x.get("timestamp", 0))
                            last_30 = sorted_data[-30:]
                            sparkline = [p.get("close", 0) for p in last_30]
                            if len(sparkline) >= 2 and sparkline[0] != 0:
                                change_percent_30d = round(((sparkline[-1] - sparkline[0]) / sparkline[0]) * 100, 2)
                    except Exception:
                        pass
                # If no cached chart, try fetching full info (will populate cache for next time)
                if not sparkline:
                    full_info = await self.stock_service.get_stock_info_async(ticker)
                    if full_info and full_info.chartData:
                        sorted_data = sorted(full_info.chartData, key=lambda x: x.timestamp)
                        last_30 = sorted_data[-30:]
                        sparkline = [p.close for p in last_30]
                        if len(sparkline) >= 2 and sparkline[0] != 0:
                            change_percent_30d = round(((sparkline[-1] - sparkline[0]) / sparkline[0]) * 100, 2)
                # Get Chinese name from translations, fallback to API name
                chinese_name = translations.get(ticker, "")
                display_name = chinese_name if chinese_name else (basic_info.get("name", ticker) if basic_info else ticker)
                market = _infer_market(ticker)
                if basic_info:
                    return SearchResultItem(
                        id=f"stock-{ticker}",
                        type="stock",
                        title=ticker,
                        subtitle=display_name,
                        link=f"/stock/{ticker}",
                        market=market,
                        metadata={
                            "price": basic_info.get("price", 0),
                            "change": basic_info.get("change", 0),
                            "change_percent": basic_info.get("changePercent", 0),
                            "change_percent_30d": change_percent_30d,
                            "mentions": ticker_counts[ticker],
                            "sparkline": sparkline
                        }
                    )
                else:
                    return SearchResultItem(
                        id=f"stock-{ticker}",
                        type="stock",
                        title=ticker,
                        subtitle=display_name,
                        link=f"/stock/{ticker}",
                        market=market,
                        metadata={
                            "mentions": ticker_counts[ticker],
                            "sparkline": [],
                            "change_percent_30d": 0.0
                        }
                    )
            except Exception as e:
                logger.warning(f"Error fetching details for trending ticker {ticker}: {e}")
                return None
        # Fetch all in parallel
        stock_results = await asyncio.gather(*[fetch_stock_for_trending(t) for t in top_tickers])
        results = [r for r in stock_results if r]
        # Cache results
        try:
            await cache_set(
                cache_key,
                json.dumps([r.dict() for r in results], default=str),
                TRENDING_CACHE_TTL
            )
        except Exception as e:
            logger.warning(f"Failed to cache trending stocks: {e}")
        return results

    async def get_active_podcasters(self, limit: int = 5) -> List[SearchResultItem]:
        """
        Get trending podcasters based on user clicks (activity).
        Falls back to 'updated_at' if no click data is available or empty.
        """
        cache_key = f"trending:podcasters:{limit}"
        cached = await cache_get(cache_key)
        if cached:
            try:
                data = json.loads(cached)
                return [SearchResultItem(**item) for item in data]
            except Exception as e:
                logger.warning(f"Failed to deserialize trending podcasters cache: {e}")

        # 1. Fetch top clicks from Redis
        try:
            # Key: "analytics:clicks:podcast"
            # Return list of [(b'id', score), ...]
            redis = await get_redis()
            if redis:
                top_ids_with_scores = await redis.zrevrange("analytics:clicks:podcast", 0, limit - 1, withscores=True)
                top_ids = [mid.decode("utf-8") if isinstance(mid, bytes) else mid for mid, score in top_ids_with_scores]
            else:
                top_ids = []
        except Exception as e:
            logger.warning(f"Failed to fetch trending clicks: {e}")
            top_ids = []

        results = []
        
        # 2. Get Podcast Details
        # Scenario A: We have click data
        if top_ids:
            # We need a method to get podcasts by IDs. get_podcast(id) loop is okay for small N.
            for pid in top_ids:
                try:
                    # Handle unclean IDs (sometimes ID might be "podcast-123")
                    clean_id = pid.replace("podcast-", "") if pid else ""
                    if not clean_id:
                        continue
                        
                    podcast = await self.podcast_service.get_podcast_by_name(clean_id)
                    if not podcast:
                        continue
                        
                    results.append(SearchResultItem(
                        id=f"podcast-{podcast.id}",
                        type="podcast",
                        title=podcast.name,
                        subtitle=f"{podcast.episode_count} Episodes",
                        link=f"/podcaster/{podcast.name}",
                        icon_url=podcast.image_url,
                        metadata={"clicks": "hot"} # Could add score here
                    ))
                except Exception as e:
                    logger.warning(f"Error fetching trending podcast {pid}: {e}")
            
        
        # Scenario B: Backfill with Recency if needed
        # If we didn't get enough results from clicks, fill the rest with recent podcasts
        if len(results) < limit:
             try:
                 # Fetch more than limit to account for potential duplicates
                 podcasts = await self.podcast_service.get_all_podcasts(
                    sort_by="updated_at", 
                    order="desc", 
                    limit=limit * 2 
                )
                 
                 # Track existing titles to avoid duplicates
                 existing_titles = {r.title for r in results}
                 
                 for podcast in podcasts:
                    if len(results) >= limit:
                        break
                        
                    if podcast.name in existing_titles:
                        continue
                        
                    results.append(SearchResultItem(
                        id=f"podcast-{podcast.id}",
                        type="podcast",
                        title=podcast.name,
                        subtitle=f"{podcast.episode_count} Episodes",
                        link=f"/podcaster/{podcast.name}",
                        icon_url=podcast.image_url,
                        metadata={"updated_at": podcast.updated_at}
                    ))
                    existing_titles.add(podcast.name)
                    
             except Exception as e:
                 logger.error(f"Fallback to recent podcasts failed: {e}")

        # 3. Cache results
        try:
            if results:
                await cache_set(
                    cache_key, 
                    json.dumps([r.dict() for r in results], default=str), 
                    TRENDING_CACHE_TTL
                )
        except Exception as e:
            logger.warning(f"Failed to cache trending podcasters: {e}")
            
        return results
