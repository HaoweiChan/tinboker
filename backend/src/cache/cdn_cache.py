"""
CDN Cache Headers Utility

Adds Cache-Control headers to responses for Cloudflare CDN caching.
This works alongside Redis caching - CDN caches at edge, Redis at origin.

Cache-Control directives:
- public: Response can be cached by CDN and browsers
- s-maxage: CDN cache duration (Cloudflare respects this)
- max-age: Browser cache duration
- stale-while-revalidate: Serve stale while fetching fresh in background
"""
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from functools import wraps
import logging
import os
from typing import Callable, List, Optional
import httpx
from fastapi import Response
from fastapi.responses import JSONResponse


def _make_json_serializable(obj):
    """Recursively convert Decimal/datetime to JSON-serializable types."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _make_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_json_serializable(v) for v in obj]
    return obj


class CacheProfile(Enum):
    """
    Predefined cache profiles for different content types.
    All cacheable content uses 1-hour CDN cache with stale-while-revalidate.
    Use purge_cdn_cache() when content is updated.
    """
    # Static content - rarely changes
    STATIC = {"s_maxage": 86400, "max_age": 3600, "stale": 86400}  # CDN: 1 day

    # Podcast/Episode metadata - 1 hour CDN cache
    PODCAST = {"s_maxage": 3600, "max_age": 3600, "stale": 7200}  # CDN: 1 hour

    # News content - 1 hour CDN cache
    NEWS = {"s_maxage": 3600, "max_age": 3600, "stale": 7200}  # CDN: 1 hour

    # Trending/Recommendations - 1 hour CDN cache, SHORT browser cache.
    # The browser cache can't be purged remotely (only s-maxage at the CDN is),
    # so a long max_age pinned users to stale buzz/rail data for up to an hour
    # after a deploy + CDN purge — the browser never revalidated. Keep the CDN at
    # 1h (purged on deploy) but let browsers refresh within ~2min (matches the
    # documented episode-freshness browser TTL in CLAUDE.md).
    TRENDING = {"s_maxage": 3600, "max_age": 120, "stale": 7200}  # CDN: 1h, browser: 2min

    # Search results - 1 hour CDN cache
    SEARCH = {"s_maxage": 3600, "max_age": 3600, "stale": 7200}  # CDN: 1 hour

    # Stock data - 1 hour CDN cache
    STOCK = {"s_maxage": 3600, "max_age": 3600, "stale": 7200}  # CDN: 1 hour

    # Real-time - no CDN cache (WebSocket, live prices)
    REALTIME = {"s_maxage": 0, "max_age": 0, "stale": 0}  # No cache

    # Personalized/Auth - private, no CDN
    PRIVATE = None


def build_cache_header(
    s_maxage: int,
    max_age: int = 0,
    stale_while_revalidate: int = 0,
    private: bool = False
) -> str:
    """
    Build Cache-Control header value.

    Args:
        s_maxage: CDN cache duration in seconds
        max_age: Browser cache duration in seconds
        stale_while_revalidate: Allow serving stale content while revalidating
        private: If True, response is user-specific (no CDN caching)

    Returns:
        Cache-Control header string
    """
    if private:
        return "private, no-store, no-cache"

    if s_maxage == 0 and max_age == 0:
        return "no-cache, no-store, must-revalidate"

    parts = ["public"]
    if s_maxage > 0:
        parts.append(f"s-maxage={s_maxage}")
    if max_age > 0:
        parts.append(f"max-age={max_age}")
    if stale_while_revalidate > 0:
        parts.append(f"stale-while-revalidate={stale_while_revalidate}")

    return ", ".join(parts)


def set_cache_headers(
    response: Response,
    profile: Optional[CacheProfile] = None,
    s_maxage: Optional[int] = None,
    max_age: Optional[int] = None,
    stale: Optional[int] = None,
    private: bool = False
) -> Response:
    """
    Set CDN cache headers on a response.

    Args:
        response: FastAPI Response object
        profile: Predefined cache profile (CacheProfile enum)
        s_maxage: Override CDN cache duration
        max_age: Override browser cache duration
        stale: Override stale-while-revalidate duration
        private: Mark as private (no CDN caching)

    Returns:
        Response with cache headers set
    """
    if private or profile == CacheProfile.PRIVATE:
        response.headers["Cache-Control"] = build_cache_header(0, 0, 0, private=True)
        return response

    # Use profile defaults if provided
    if profile and profile.value:
        cfg = profile.value
        s_maxage = s_maxage if s_maxage is not None else cfg["s_maxage"]
        max_age = max_age if max_age is not None else cfg["max_age"]
        stale = stale if stale is not None else cfg["stale"]

    # Default values
    s_maxage = s_maxage or 0
    max_age = max_age or 0
    stale = stale or 0

    if "Cache-Control" not in response.headers:
        response.headers["Cache-Control"] = build_cache_header(s_maxage, max_age, stale)

    # Add Vary header to ensure proper cache key differentiation
    response.headers["Vary"] = "Accept-Encoding"

    return response


def cdn_cached(
    profile: Optional[CacheProfile] = None,
    s_maxage: Optional[int] = None,
    max_age: Optional[int] = None,
    stale: Optional[int] = None,
    private: bool = False
):
    """
    Decorator to add CDN cache headers to a route.

    Usage:
        @router.get("/news")
        @cdn_cached(profile=CacheProfile.NEWS)
        async def get_news():
            return {"news": [...]}

        @router.get("/custom")
        @cdn_cached(s_maxage=600, max_age=120)
        async def get_custom():
            return {"data": [...]}

    Args:
        profile: Predefined cache profile
        s_maxage: CDN cache duration in seconds
        max_age: Browser cache duration in seconds
        stale: Stale-while-revalidate duration
        private: Mark as private (no CDN caching)
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            injected_response = kwargs.get("response")
            if not isinstance(injected_response, Response):
                injected_response = next((arg for arg in args if isinstance(arg, Response)), None)

            # If result is already a Response, add headers
            if isinstance(result, Response):
                return set_cache_headers(
                    result,
                    profile=profile,
                    s_maxage=s_maxage,
                    max_age=max_age,
                    stale=stale,
                    private=private
                )

            # Serialize Pydantic models to dict for JSON encoding
            from pydantic import BaseModel
            if isinstance(result, BaseModel):
                content = result.model_dump(mode='json')
            elif isinstance(result, list) and result and isinstance(result[0], BaseModel):
                content = [item.model_dump(mode='json') for item in result]
            elif isinstance(result, dict):
                # Handle dict with potential Pydantic model values
                content = {}
                for key, value in result.items():
                    if isinstance(value, BaseModel):
                        content[key] = value.model_dump(mode='json')
                    elif isinstance(value, list) and value and isinstance(value[0], BaseModel):
                        content[key] = [item.model_dump(mode='json') for item in value]
                    else:
                        content[key] = value
            else:
                content = result

            # Ensure Decimals/datetimes are JSON-serializable (e.g. from DB)
            content = _make_json_serializable(content)

            # Create JSONResponse with serialized content
            response = JSONResponse(content=content)
            if isinstance(injected_response, Response):
                for name, value in injected_response.headers.items():
                    response.headers.setdefault(name, value)
            return set_cache_headers(
                response,
                profile=profile,
                s_maxage=s_maxage,
                max_age=max_age,
                stale=stale,
                private=private
            )

        return wrapper
    return decorator


# Convenience decorators for common profiles
def cdn_cache_podcast(func: Callable):
    """Cache for podcast content (1 hour CDN)"""
    return cdn_cached(profile=CacheProfile.PODCAST)(func)


def cdn_cache_news(func: Callable):
    """Cache for news content (1 hour CDN)"""
    return cdn_cached(profile=CacheProfile.NEWS)(func)


def cdn_cache_trending(func: Callable):
    """Cache for trending/recommendations (1 hour CDN)"""
    return cdn_cached(profile=CacheProfile.TRENDING)(func)


def cdn_cache_stock(func: Callable):
    """Cache for stock data (1 hour CDN)"""
    return cdn_cached(profile=CacheProfile.STOCK)(func)


def cdn_no_cache(func: Callable):
    """No CDN caching (real-time or personalized)"""
    return cdn_cached(profile=CacheProfile.REALTIME)(func)


# =============================================================================
# CDN Cache Invalidation (Cloudflare Purge)
# =============================================================================

logger = logging.getLogger(__name__)


async def purge_cdn_cache(
    urls: Optional[List[str]] = None,
    prefixes: Optional[List[str]] = None,
    hosts: Optional[List[str]] = None,
    purge_everything: bool = False
) -> bool:
    """
    Purge Cloudflare CDN cache for specific URLs, prefixes, or hosts.

    Credentials come from settings (loaded from GCP Secret Manager) — the zone id is
    stored as CLOUDFLARE_ZONE_TAG and the token as CLOUDFLARE_API_TOKEN. Env vars of the
    same names (plus legacy CLOUDFLARE_ZONE_ID) are accepted as a fallback for CI/tests.

    Args:
        urls: List of specific URLs to purge (e.g., ["https://api.tinboker.com/api/news"])
        prefixes: List of URL prefixes to purge — host+path, no scheme (Enterprise only)
        hosts: List of hostnames to purge — e.g. ["dev-api.tinboker.com"] (Enterprise only)
        purge_everything: If True, purge entire cache (use sparingly!)

    Returns:
        True if purge was successful, False otherwise

    Usage:
        # Purge specific URLs
        await purge_cdn_cache(urls=["https://api.tinboker.com/api/news/123"])

        # Purge by host (all cached responses for one env's API)
        await purge_cdn_cache(hosts=["dev-api.tinboker.com"])

        # Purge everything (use carefully!)
        await purge_cdn_cache(purge_everything=True)
    """
    # Creds live in settings (GCP Secret Manager); fall back to env vars for the CI /
    # test contexts that set them directly. settings.cloudflare_zone_tag is the zone id.
    try:
        from src.config import settings
        zone_id = settings.cloudflare_zone_tag or os.getenv("CLOUDFLARE_ZONE_TAG") or os.getenv("CLOUDFLARE_ZONE_ID")
        api_token = settings.cloudflare_api_token or os.getenv("CLOUDFLARE_API_TOKEN")
    except Exception:
        zone_id = os.getenv("CLOUDFLARE_ZONE_TAG") or os.getenv("CLOUDFLARE_ZONE_ID")
        api_token = os.getenv("CLOUDFLARE_API_TOKEN")

    if not zone_id or not api_token:
        logger.warning("Cloudflare credentials not configured. CDN cache purge skipped.")
        return False

    api_url = f"https://api.cloudflare.com/client/v4/zones/{zone_id}/purge_cache"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    # Build request body
    if purge_everything:
        body = {"purge_everything": True}
        logger.info("Purging entire CDN cache")
    elif hosts:
        body = {"hosts": hosts}
        logger.info(f"Purging CDN cache hosts: {hosts}")
    elif prefixes:
        body = {"prefixes": prefixes}
        logger.info(f"Purging CDN cache prefixes: {prefixes}")
    elif urls:
        body = {"files": urls}
        logger.info(f"Purging CDN cache URLs: {urls}")
    else:
        logger.warning("No urls/prefixes/hosts specified for CDN purge")
        return False
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(api_url, headers=headers, json=body, timeout=30.0)
            result = response.json()
            
            if result.get("success"):
                logger.info("CDN cache purge successful")
                return True
            else:
                errors = result.get("errors", [])
                logger.error(f"CDN cache purge failed: {errors}")
                return False
    except Exception as e:
        logger.error(f"CDN cache purge error: {e}")
        return False


# Convenience functions for common purge patterns
async def purge_podcast_cache(podcast_name: Optional[str] = None):
    """Purge podcast-related CDN cache"""
    base = os.getenv("API_BASE_URL", "https://api.tinboker.com")
    if podcast_name:
        return await purge_cdn_cache(prefixes=[f"{base}/api/podcast/{podcast_name}"])
    return await purge_cdn_cache(prefixes=[f"{base}/api/podcast/", f"{base}/api/episodes/"])


async def purge_news_cache(news_id: Optional[str] = None):
    """Purge news-related CDN cache"""
    base = os.getenv("API_BASE_URL", "https://api.tinboker.com")
    if news_id:
        return await purge_cdn_cache(urls=[f"{base}/api/news/{news_id}", f"{base}/api/news"])
    return await purge_cdn_cache(prefixes=[f"{base}/api/news"])


async def purge_recommendations_cache():
    """Purge recommendations CDN cache"""
    base = os.getenv("API_BASE_URL", "https://api.tinboker.com")
    return await purge_cdn_cache(prefixes=[f"{base}/api/recommendations/"])
