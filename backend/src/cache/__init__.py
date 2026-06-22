"""
Cache module for Redis caching and CDN cache headers
"""
from src.cache.redis_client import (
    RedisClient,
    get_redis,
    cache_get,
    cache_set,
    cache_delete,
    cache_delete_pattern,
    cache_delete_pattern_all_envs,
)
from src.cache.cache_config import CACHE_TTL
from src.cache.cdn_cache import (
    CacheProfile,
    cdn_cached,
    cdn_cache_podcast,
    cdn_cache_news,
    cdn_cache_trending,
    cdn_cache_stock,
    cdn_no_cache,
    set_cache_headers,
    purge_cdn_cache,
    purge_podcast_cache,
    purge_news_cache,
    purge_recommendations_cache,
)

__all__ = [
    # Redis caching
    "RedisClient",
    "get_redis",
    "cache_get",
    "cache_set",
    "cache_delete",
    "cache_delete_pattern",
    "cache_delete_pattern_all_envs",
    "CACHE_TTL",
    # CDN cache headers
    "CacheProfile",
    "cdn_cached",
    "cdn_cache_podcast",
    "cdn_cache_news",
    "cdn_cache_trending",
    "cdn_cache_stock",
    "cdn_no_cache",
    "set_cache_headers",
    # CDN cache invalidation
    "purge_cdn_cache",
    "purge_podcast_cache",
    "purge_news_cache",
    "purge_recommendations_cache",
]

