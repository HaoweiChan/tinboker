"""
Recommendation service: read-only access to ticker recommendations (podcast_db).
Uses Redis cache with 2h TTL. Default timeframe: today − 7 days → today.
"""
import asyncio
import json
import logging
from datetime import date, datetime, timedelta
from typing import List, Optional

from src.cache.redis_client import cache_get, cache_set
from src.cache.cache_config import CACHE_TTL
from src.database.insight_queries import (
    get_by_ticker,
    get_by_podcaster,
    get_most_discussed,
)

logger = logging.getLogger(__name__)

RECOMMENDATION_TTL = 7200  # 2 hours


def _default_start_end() -> tuple:
    """Default timeframe: today − 7 days, today."""
    end = date.today()
    start = end - timedelta(days=7)
    return start, end


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        if "T" in s or " " in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return None


class RecommendationService:
    """Service for ticker/podcaster recommendations and buzz."""

    async def get_recommendations_by_ticker(
        self,
        ticker: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[dict]:
        """Return recommendations for the ticker. Default: last 7 days."""
        start = _parse_date(start_date)
        end = _parse_date(end_date)
        if start is None or end is None:
            start, end = _default_start_end()
        cache_key = f"recommendation:ticker:{ticker}:{start}:{end}"
        cached = await cache_get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception as e:
                logger.warning("Recommendation cache deserialize failed: %s", e)
        result = await asyncio.to_thread(get_by_ticker, ticker, start, end)
        try:
            await cache_set(
                cache_key,
                json.dumps(result, default=str),
                CACHE_TTL.get("recommendation_by_ticker", RECOMMENDATION_TTL),
            )
        except Exception as e:
            logger.warning("Recommendation cache set failed: %s", e)
        return result

    async def get_recommendations_by_podcaster(
        self,
        podcaster: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        podcast_slug: Optional[str] = None,
    ) -> List[dict]:
        """Return recommendations from the podcaster. Default: last 7 days. Optional podcast_slug matches episode_id."""
        start = _parse_date(start_date)
        end = _parse_date(end_date)
        if start is None or end is None:
            start, end = _default_start_end()
        slug_part = (podcast_slug or "").strip() or ""
        cache_key = f"recommendation:podcaster:{podcaster}:{slug_part}:{start}:{end}"
        cached = await cache_get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception as e:
                logger.warning("Recommendation cache deserialize failed: %s", e)
        result = await asyncio.to_thread(
            get_by_podcaster, podcaster, start, end, slug_part or None
        )
        try:
            await cache_set(
                cache_key,
                json.dumps(result, default=str),
                CACHE_TTL.get("recommendation_by_podcaster", RECOMMENDATION_TTL),
            )
        except Exception as e:
            logger.warning("Recommendation cache set failed: %s", e)
        return result

    async def get_most_discussed_tickers(
        self,
        days: int = 30,
        limit: int = 10,
    ) -> List[dict]:
        """Return most-discussed tickers in the last `days` days."""
        end = date.today()
        start = end - timedelta(days=days)
        cache_key = f"recommendation:buzz:{days}:{limit}"
        cached = await cache_get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception as e:
                logger.warning("Recommendation cache deserialize failed: %s", e)
        result = await asyncio.to_thread(
            get_most_discussed, start, end, limit
        )
        try:
            await cache_set(
                cache_key,
                json.dumps(result, default=str),
                CACHE_TTL.get("recommendation_buzz", RECOMMENDATION_TTL),
            )
        except Exception as e:
            logger.warning("Recommendation cache set failed: %s", e)
        return result
