# Analysis: Why Cache Isn't Being Used in Running Server

## Problem Identified

The `/api/visuals/supply-chain` endpoint is slow (~15 seconds) even though:
- ✅ Cache code is implemented correctly
- ✅ Redis is running and accessible
- ✅ Cache can be set/retrieved when tested directly
- ✅ Cache key exists in Redis: `visual:supply-chain`

## Root Cause

**The running FastAPI server does NOT have Redis connected!**

### Evidence

1. **Health endpoint shows no Redis info:**
   ```json
   {
     "status": "healthy",
     "timestamp": "2025-12-01T06:32:38.287306Z"
   }
   ```
   - Missing `redis` key entirely
   - This means `RedisClient.is_available()` returns `False`

2. **Redis stats don't increase on API calls:**
   - Before request: `keyspace_hits:21, keyspace_misses:12`
   - After request: `keyspace_hits:21, keyspace_misses:12` (no change!)
   - **Cache is NOT being checked during API requests**

3. **Server was started before Redis:**
   - Server process started at 11:03
   - Redis container might not have been running then
   - Redis initialization failed silently during startup

## Why Cache Operations Return None

Looking at `src/cache/redis_client.py`:

```python
async def cache_get(key: str) -> Optional[str]:
    redis = await get_redis()  # Returns None if Redis not initialized
    if redis:  # This is False, so returns None
        return await redis.get(key)
    return None  # ❌ Always returns None
```

When `RedisClient._client` is `None`:
- `cache_get()` returns `None` immediately
- `cache_set()` returns `False` immediately
- No errors are raised (silent failure)
- Code continues as if cache miss

## Code Flow Analysis

### In `visual_graph.py`:

```python
# Line 129: Check cache
cached = await cache_get(cache_key)  # Returns None (Redis not connected)
if cached:  # False, skips this block
    return json.loads(cached)

# Line 136-151: Always executes (cache miss path)
# Generates data (slow - 15 seconds)
result = {...}

# Line 155: Try to cache
await cache_set(...)  # Returns False (Redis not connected)
# Exception is caught and ignored (line 160)
```

**Result:** Always takes the slow path, cache is never used.

## Why Redis Initialization Failed

Possible reasons:

1. **Redis wasn't running when server started**
   - Server started at 11:03
   - Redis might have been started later
   - `RedisClient.initialize()` failed silently

2. **Connection error during startup**
   - `redis://localhost:6379/0` might not have been reachable
   - Exception caught, `_client` set to `None`
   - Server continued without Redis

3. **Timing issue**
   - FastAPI startup might have raced with Redis container
   - Redis wasn't ready when server tried to connect

## Verification Steps

1. ✅ Redis is running: `docker ps | grep redis` → Container exists
2. ✅ Redis is accessible: `docker exec tinboker-redis redis-cli ping` → PONG
3. ✅ Cache can be set: Direct Python test works
4. ✅ Cache key exists: `visual:supply-chain` in Redis
5. ❌ Server has Redis: Health endpoint shows no Redis info
6. ❌ Cache is used: Stats don't increase on API calls

## Solution

**Restart the FastAPI server** so it can connect to Redis:

```bash
# Stop current server
pkill -f "python.*main"

# Start Redis (if not running)
docker compose up -d redis

# Start server (will initialize Redis)
python -m src.main
```

After restart, the health endpoint should show:
```json
{
  "status": "healthy",
  "redis": {
    "available": true,
    "status": "connected",
    "keyspace_hits": ...,
    "keyspace_misses": ...,
    "hit_rate": ...
  }
}
```

## Additional Issues Found

Even after fixing Redis connection, the endpoint will still be slow on **first request** (cache miss) because:

1. **Sequential node processing** (6 nodes × 2.5s = 15s)
2. **Blocking `get_ohlcv_data()` call** (synchronous, blocks event loop)
3. **No parallelization** of node enrichment

These need to be fixed separately for optimal performance.

