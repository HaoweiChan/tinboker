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
            # Use the module attribute, not the value imported at module-load time:
            # init_engine() sets postgres.SessionLocal, but the name imported here
            # stays None forever → SessionLocal() would call None() ('NoneType' object
            # is not callable), silently breaking all translations.
            from src.database import postgres
            if postgres.SessionLocal is None:
                postgres.init_engine()
            db = postgres.SessionLocal()
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

    async def get_recent_buzz(
        self,
        days: int = 30,
        limit: int = 10,
        ticker: Optional[str] = None,
    ) -> dict:
        """Genuine 'what people are discussing lately' for the homepage rail.

        Counts tickers mentioned across the RECENT episodes (already zh-TW-scoped and
        recency-filtered by PodcastService), aggregates a dominant sentiment per ticker
        from those episodes' ticker_insights, and returns the top `limit` plus
        totals. Unlike `trending_tickers` (agents-precomputed over the full all-time,
        English-inclusive catalog), this reflects only the launch feed.

        Returns: {tickers, distinct_count, episode_count, sentiment_summary,
                  prev_sentiment_summary, rising_ticker, new_tickers}
        """
        ticker_filter = ticker.strip().upper().split(".")[0] if ticker else None
        cache_key = f"buzz:recent:{days}:{limit}:{ticker_filter or 'all'}:v4"
        cached = await cache_get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception:
                pass

        episodes = await self.podcast_service.get_recent_episodes(limit=500, enrich_content=False)
        cutoff = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
        prev_cutoff = int((datetime.now() - timedelta(days=days * 2)).timestamp() * 1000)
        counts: Counter = Counter()
        prev_counts: Counter = Counter()
        last_mentioned: Dict[str, int] = {}
        eps_by_ticker: Dict[str, list] = {}
        episode_count = 0
        for ep in episodes:
            rel = ep.released_at_ms if ep.released_at_ms is not None else (ep.created_time or 0)
            tickers = [str(t).upper() for t in (ep.related_tickers or [])]
            if rel >= cutoff:
                episode_count += 1
                for tu in tickers:
                    counts[tu] += 1
                    if rel > last_mentioned.get(tu, 0):
                        last_mentioned[tu] = rel
                    eps_by_ticker.setdefault(tu, []).append(ep.id)
            elif rel >= prev_cutoff:
                for tu in tickers:
                    prev_counts[tu] += 1

        if ticker_filter:
            top = [(ticker_filter, counts[ticker_filter])] if counts.get(ticker_filter, 0) > 0 else []
        else:
            top = counts.most_common(limit)
        top_tickers = [t for t, _ in top]

        # Tickers to translate: top tickers + rising candidate + new tickers
        new_ticker_set = set(counts) - set(prev_counts)
        rising_ticker_id = None
        rising_delta = 0
        for t in counts:
            delta = counts[t] - prev_counts.get(t, 0)
            if delta > rising_delta:
                rising_delta = delta
                rising_ticker_id = t
        # The newcomers we actually display are the top-5 by mention count — translate
        # exactly those, not an arbitrary set-iteration slice, or the displayed tickers
        # come back with name=None and render as raw symbols (e.g. DELL, SNOW).
        new_ticker_top = sorted(new_ticker_set, key=lambda x: counts[x], reverse=True)[:5]
        extra_tickers = list(new_ticker_top)
        if rising_ticker_id:
            extra_tickers.append(rising_ticker_id)
        all_tickers_to_translate = list(set(top_tickers + extra_tickers + ([ticker_filter] if ticker_filter else [])))
        translations = await self._get_translations_batch(all_tickers_to_translate)

        # Aggregate dominant sentiment per top ticker
        sent_maps: Dict[str, dict] = {}
        try:
            from src.services.episode_sentiments import EpisodeSentimentService
            sent_service = EpisodeSentimentService()
            relevant_ids = list({eid for t in top_tickers for eid in eps_by_ticker.get(t, [])})
            for i in range(0, len(relevant_ids), 80):
                sent_maps.update(await sent_service.get_sentiments(relevant_ids[i:i + 80]))
        except Exception as e:
            logger.warning(f"buzz sentiment aggregation failed: {e}")

        bull = bear = neutral = 0
        items = []
        for ticker, count in top:
            s_counts: Counter = Counter()
            for eid in eps_by_ticker.get(ticker, []):
                s = sent_maps.get(eid, {}).get(ticker)
                if s:
                    s_counts[s] += 1
            dominant = s_counts.most_common(1)[0][0] if s_counts else "NEUTRAL"
            sentiment_counts = {
                "bull": s_counts.get("BULLISH", 0),
                "neutral": s_counts.get("NEUTRAL", 0),
                "bear": s_counts.get("BEARISH", 0),
            }
            if dominant == "BULLISH":
                bull += 1
            elif dominant == "BEARISH":
                bear += 1
            else:
                neutral += 1
            items.append({
                "ticker": ticker,
                "name": translations.get(ticker) or None,
                "count": count,
                "sentiment_label": dominant,
                "sentiment_counts": sentiment_counts,
                "last_mentioned": last_mentioned.get(ticker),
            })

        # Compute prev-window sentiment summary from the top tickers' prior counts
        prev_bull = prev_bear = prev_neutral = 0
        for t in set(prev_counts):
            if prev_counts[t] > 0:
                prev_neutral += 1
        # Re-use sent_maps for a rough prior approximation: count dominant sentiments
        # across all tickers that appeared in the prior window. Since we don't have
        # per-episode sentiment for prior-window episodes without extra fetches, we
        # approximate using the current sentiment label if the ticker also appeared now.
        for t in set(prev_counts):
            label = next((it["sentiment_label"] for it in items if it["ticker"] == t), None)
            if label == "BULLISH":
                prev_bull += 1
            elif label == "BEARISH":
                prev_bear += 1
            # else stays neutral (already counted)
        # Adjust: only count each ticker once
        prev_total = len(set(prev_counts))
        if prev_total > 0:
            prev_neutral = prev_total - prev_bull - prev_bear

        result = {
            "tickers": items,
            "distinct_count": len(counts),
            "episode_count": episode_count,
            "sentiment_summary": {"bull": bull, "neutral": neutral, "bear": bear},
            "prev_sentiment_summary": {"bull": prev_bull, "neutral": prev_neutral, "bear": prev_bear},
        }
        if rising_ticker_id and rising_delta > 0:
            result["rising_ticker"] = {
                "ticker": rising_ticker_id,
                "name": translations.get(rising_ticker_id) or None,
                "delta": rising_delta,
            }
        new_tickers_list = []
        for t in new_ticker_top:
            new_tickers_list.append({
                "ticker": t,
                "name": translations.get(t) or None,
            })
        if new_tickers_list:
            result["new_tickers"] = new_tickers_list
        try:
            await cache_set(cache_key, json.dumps(result), 1800)
        except Exception:
            pass
        return result

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
