"""
Redis client setup for FastAPI
"""
from redis import asyncio as aioredis
from typing import Optional
from src.config import settings
import json
import logging

logger = logging.getLogger(__name__)

class RedisClient:
    """Async Redis client wrapper with pub/sub support"""
    
    _client: Optional[aioredis.Redis] = None
    _pubsub_client: Optional[aioredis.Redis] = None
    _disabled: bool = False  # Circuit breaker flag
    
    @classmethod
    async def initialize(cls, retries: int = 1, delay: float = 0.5) -> None:
        """
        Initialize Redis connection with retry logic.
        
        Args:
            retries: Number of retry attempts (default: 1 for fast fail)
            delay: Initial delay between retries in seconds
        """
        import os
        import asyncio
        
        if cls._disabled:
            return

        redis_url = settings.redis_connection_string
        
        # Log what we're trying to connect to (without exposing password)
        if redis_url:
            # Mask password in URL for logging
            safe_url = redis_url
            if "@" in redis_url and ":" in redis_url.split("@")[0]:
                parts = redis_url.split("@")
                safe_url = f"redis://:***@{parts[1]}" if len(parts) > 1 else redis_url
            logger.info(f"Attempting to connect to Redis: {safe_url}")
        else:
            # Check if REDIS_URL env var exists but wasn't picked up
            if "REDIS_URL" in os.environ:
                logger.warning(f"REDIS_URL env var exists but connection string is None. Value: {os.environ['REDIS_URL'][:20]}...")
            else:
                logger.info("Redis connection string not configured, caching disabled")
            
            cls._disabled = True
            cls._client = None
            return
        
        # Retry logic for connection
        for attempt in range(retries):
            try:
                # BlockingConnectionPool (not the default pool): under a homepage burst
                # dozens of tickers each do concurrent cache ops. The default pool *raises*
                # "Too many connections" the instant max_connections is exceeded, which makes
                # cache_get fail and the caller fall through to a live upstream API call —
                # turning a cache hit into a Massive/FinMind request and pinning their rate
                # limits. The blocking pool instead waits up to `timeout` for a free
                # connection, so bursts queue briefly rather than bypassing the cache.
                pool = aioredis.BlockingConnectionPool.from_url(
                    redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "100")),
                    timeout=float(os.getenv("REDIS_POOL_TIMEOUT", "0.5")),  # wait for a free conn, don't throw
                    socket_connect_timeout=float(os.getenv("REDIS_CONNECT_TIMEOUT", "1")),
                    socket_timeout=float(os.getenv("REDIS_SOCKET_TIMEOUT", "1")),
                )
                cls._client = aioredis.Redis(connection_pool=pool)
                # Test connection
                await cls._client.ping()
                logger.info("Redis connection established successfully")
                cls._disabled = False
                return
            except Exception as e:
                # Close client if it was created but failed ping
                if cls._client:
                    await cls._client.close()
                    cls._client = None
                    
                if attempt < retries - 1:
                    wait_time = delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(f"Failed to connect to Redis (attempt {attempt + 1}/{retries}): {e}. Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.warning(f"Failed to connect to Redis after {retries} attempts: {e}. Caching will be disabled.")
                    cls._disabled = True
                    cls._client = None
    
    @classmethod
    async def get_client(cls) -> Optional[aioredis.Redis]:
        """Get Redis client instance"""
        if cls._disabled:
            return None
            
        if cls._client is None:
            await cls.initialize()
            
        return cls._client
    
    @classmethod
    async def close(cls) -> None:
        """Close Redis connection"""
        if cls._client:
            await cls._client.close()
            cls._client = None
            logger.info("Redis connection closed")
    
    @classmethod
    async def is_available(cls) -> bool:
        """Check if Redis is available"""
        if cls._client is None:
            return False
        try:
            await cls._client.ping()
            return True
        except Exception:
            return False
    
    @classmethod
    async def get_pubsub_client(cls) -> Optional[aioredis.Redis]:
        """Get separate Redis client for pub/sub (recommended)"""
        if cls._pubsub_client is None:
            redis_url = settings.redis_connection_string
            if not redis_url:
                logger.debug("Redis connection string not available for pub/sub client")
                return None
            try:
                cls._pubsub_client = aioredis.from_url(
                    redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    max_connections=10,
                    socket_connect_timeout=5,
                    socket_timeout=5
                )
                await cls._pubsub_client.ping()
                logger.info("Redis pub/sub client initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Redis pub/sub client: {e}")
                cls._pubsub_client = None
        return cls._pubsub_client
    
    @classmethod
    async def publish_message(cls, channel: str, data: dict) -> int:
        """
        Publish a message to a Redis channel.
        
        Args:
            channel: Redis channel name
            data: Dictionary to publish (will be JSON serialized)
            
        Returns:
            Number of subscribers that received the message
        """
        redis = await cls.get_client()
        if not redis:
            return 0
        
        try:
            message = json.dumps(data, default=str)
            subscribers = await redis.publish(channel, message)
            return subscribers
        except Exception as e:
            logger.error(f"Error publishing to channel {channel}: {e}")
            return 0
    
    @classmethod
    async def create_subscriber(cls) -> Optional[aioredis.client.PubSub]:
        """
        Create a Redis pub/sub subscriber.
        
        Returns:
            PubSub object or None if Redis unavailable
        """
        redis = await cls.get_pubsub_client()
        if not redis:
            return None
        
        return redis.pubsub()
    
    @classmethod
    async def subscribe_channel(cls, pubsub: aioredis.client.PubSub, channel: str) -> None:
        """Subscribe to a Redis channel"""
        if pubsub:
            await pubsub.subscribe(channel)
            logger.debug(f"Subscribed to channel: {channel}")
    
    @classmethod
    async def unsubscribe_channel(cls, pubsub: aioredis.client.PubSub, channel: str) -> None:
        """Unsubscribe from a Redis channel"""
        if pubsub:
            await pubsub.unsubscribe(channel)
            logger.debug(f"Unsubscribed from channel: {channel}")
    
    @classmethod
    async def close_pubsub(cls, pubsub: aioredis.client.PubSub) -> None:
        """Close pub/sub connection"""
        if pubsub:
            await pubsub.close()
    
    @classmethod
    async def close_all(cls) -> None:
        """Close all Redis connections"""
        await cls.close()
        if cls._pubsub_client:
            await cls._pubsub_client.close()
            cls._pubsub_client = None
            logger.info("Redis pub/sub client closed")


# Convenience functions
async def get_redis() -> Optional[aioredis.Redis]:
    """Get Redis client"""
    return await RedisClient.get_client()

async def cache_get(key: str) -> Optional[str]:
    """Get value from cache"""
    redis = await get_redis()
    if redis:
        try:
            return await redis.get(key)
        except Exception as e:
            logger.warning(f"Cache get error for key {key}: {e}")
            return None
    return None

async def cache_set(key: str, value: str, ttl: int = 300) -> bool:
    """Set value in cache with TTL"""
    redis = await get_redis()
    if redis:
        try:
            await redis.setex(key, ttl, value)
            return True
        except Exception as e:
            logger.warning(f"Cache set error for key {key}: {e}")
            return False
    return False

async def cache_delete(key: str) -> bool:
    """Delete key from cache"""
    redis = await get_redis()
    if redis:
        try:
            await redis.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Cache delete error for key {key}: {e}")
            return False
    return False

async def cache_delete_pattern(pattern: str) -> int:
    """Delete all keys matching pattern"""
    redis = await get_redis()
    if redis:
        try:
            keys = await redis.keys(pattern)
            if keys:
                return await redis.delete(*keys)
        except Exception as e:
            logger.warning(f"Cache delete pattern error for {pattern}: {e}")
    return 0


# ── Cross-env (logical-DB) purge ─────────────────────────────────────────────
# Every env's backend writes to the SAME shared Postgres but caches into its OWN
# Redis logical DB (docker-compose.multi.yml: prod=/0, staging=/1, dev=/2). The admin
# UI is dev-only, so an edit there only clears /2 unless we fan the purge out —
# otherwise prod/staging serve stale until TTL.
# ponytail: DB list mirrors the fixed 0/1/2 split in compose; widen if envs are added.
_ENV_REDIS_DBS = (0, 1, 2)


def _env_redis_urls(base: str) -> list:
    """Rewrite `base` to point at each env's Redis logical DB (0/1/2)."""
    from urllib.parse import urlparse, urlunparse
    parsed = urlparse(base)
    return [urlunparse(parsed._replace(path=f"/{db}")) for db in _ENV_REDIS_DBS]


async def cache_delete_pattern_all_envs(pattern: str) -> int:
    """Delete keys matching `pattern` in EVERY env's Redis logical DB.

    All envs share one DB but cache into per-env logical DBs, so an admin edit from
    one env must invalidate the others. Best-effort per DB; never raises.
    """
    base = settings.redis_connection_string
    if not base:
        return 0
    deleted = 0
    for db, url in zip(_ENV_REDIS_DBS, _env_redis_urls(base)):
        try:
            client = aioredis.from_url(
                url, encoding="utf-8", decode_responses=True,
                socket_connect_timeout=1, socket_timeout=1,
            )
            try:
                keys = await client.keys(pattern)
                if keys:
                    deleted += await client.delete(*keys)
            finally:
                await client.close()
        except Exception as e:  # never leak the url (it may carry a password)
            logger.warning("cross-env cache purge failed for %s (db %s): %s", pattern, db, e)
    return deleted

