# Redis Service Setup & Caching Strategy Guide

This comprehensive guide covers Redis setup, caching strategies, and best practices for the TinBoker Backend API.

---

## 1. Install Redis

### Local Installation

**macOS:**
```bash
brew install redis
brew services start redis
```

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

**Windows (WSL):**
```bash
# In WSL Ubuntu
sudo apt-get install redis-server
```

### Docker (Recommended for Development)

```bash
# Basic Redis container
docker run -d --name redis-local -p 6379:6379 redis:7-alpine

# With persistence and custom config
docker run -d --name redis-local \
  -p 6379:6379 \
  -v $(pwd)/redis-data:/data \
  -v $(pwd)/redis.conf:/usr/local/etc/redis/redis.conf \
  redis:7-alpine redis-server /usr/local/etc/redis/redis.conf

# Check if running
docker ps | grep redis
redis-cli ping  # Should return PONG
```

### Verify Installation

```bash
redis-cli ping
# Expected: PONG

redis-cli info server
# Should show Redis version and server info
```

---

## 2. Configure Redis

### Basic Configuration (`redis.conf`)

For **cache-only** usage (recommended for TinBoker):

```conf
# Network
bind 0.0.0.0
port 6379
protected-mode no  # Only for local/dev

# Memory Management
maxmemory 2gb
maxmemory-policy allkeys-lru  # Evict least recently used when full

# Persistence (optional for cache-only)
# For cache, you typically don't need persistence
save ""  # Disable RDB snapshots
appendonly no  # Disable AOF

# Performance
tcp-backlog 511
timeout 0
tcp-keepalive 300

# Logging
loglevel notice
```

### Production Configuration

For production, enable persistence and security:

```conf
# Security
requirepass your_strong_password_here
protected-mode yes

# Persistence (if you need data to survive restarts)
save 900 1      # Save if at least 1 key changed in 900 seconds
save 300 10     # Save if at least 10 keys changed in 300 seconds
save 60 10000   # Save if at least 10000 keys changed in 60 seconds

appendonly yes
appendfsync everysec
```

### Docker with Custom Config

```bash
# Create redis.conf file
cat > redis.conf << EOF
maxmemory 2gb
maxmemory-policy allkeys-lru
save ""
appendonly no
EOF

# Run with config
docker run -d --name redis-local \
  -p 6379:6379 \
  -v $(pwd)/redis.conf:/usr/local/etc/redis/redis.conf \
  redis:7-alpine redis-server /usr/local/etc/redis/redis.conf
```

---

## 3. Add Redis Client in Backend (FastAPI)

### Install Python Redis Client

```bash
# For async operations (recommended for FastAPI)
pip install aioredis

# Or for sync operations
pip install redis[hiredis]  # hiredis provides better performance
```

### Async Redis Client Setup (Recommended)

Create `src/cache/redis_client.py`:

```python
"""
Redis client setup for FastAPI
"""
import aioredis
from typing import Optional
from src.config import settings
import json
import logging

logger = logging.getLogger(__name__)

class RedisClient:
    """Async Redis client wrapper"""
    
    _client: Optional[aioredis.Redis] = None
    
    @classmethod
    async def initialize(cls) -> None:
        """Initialize Redis connection"""
        try:
            redis_url = settings.redis_connection_string
            cls._client = await aioredis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=50
            )
            # Test connection
            await cls._client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            cls._client = None
    
    @classmethod
    async def get_client(cls) -> Optional[aioredis.Redis]:
        """Get Redis client instance"""
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

# Convenience functions
async def get_redis() -> Optional[aioredis.Redis]:
    """Get Redis client"""
    return await RedisClient.get_client()

async def cache_get(key: str) -> Optional[str]:
    """Get value from cache"""
    redis = await get_redis()
    if redis:
        return await redis.get(key)
    return None

async def cache_set(key: str, value: str, ttl: int = 300) -> bool:
    """Set value in cache with TTL"""
    redis = await get_redis()
    if redis:
        await redis.setex(key, ttl, value)
        return True
    return False

async def cache_delete(key: str) -> bool:
    """Delete key from cache"""
    redis = await get_redis()
    if redis:
        await redis.delete(key)
        return True
    return False

async def cache_delete_pattern(pattern: str) -> int:
    """Delete all keys matching pattern"""
    redis = await get_redis()
    if redis:
        keys = await redis.keys(pattern)
        if keys:
            return await redis.delete(*keys)
    return 0
```

### Initialize in FastAPI Startup

Update `src/main.py`:

```python
from src.cache.redis_client import RedisClient

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    # ... existing database init ...
    
    # Initialize Redis
    await RedisClient.initialize()

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    await RedisClient.close()
```

### Sync Redis Client (Alternative)

If you prefer sync operations:

```python
import redis
from src.config import settings

redis_pool = redis.ConnectionPool(
    host=settings.redis_host,
    port=settings.redis_port,
    db=settings.redis_db,
    password=settings.redis_password,
    max_connections=50,
    decode_responses=True
)

redis_client = redis.Redis(connection_pool=redis_pool)
```

---

## 4. Cache Key Naming Convention

Design a clear, hierarchical key structure for TinBoker:

### Stock Data Keys

```
stock:{ticker}:info              # Full stock information (CompanyDetail)
stock:{ticker}:basic             # Basic stock info only
stock:{ticker}:ohlcv:{start}:{end}  # Historical OHLCV data
stock:list:{sort_by}:{limit}    # Sorted stock list
stock:price:{ticker}             # Current price only
```

**Examples:**
- `stock:AAPL:info`
- `stock:NVDA:basic`
- `stock:MSFT:ohlcv:2024-01-01:2024-01-31`
- `stock:list:price:50`

### Graph Data Keys

```
graph:{graph_id}                 # Full graph data
graph:list:{sort_by}             # Graph list
graph:{graph_id}:nodes           # Graph nodes only
graph:{graph_id}:edges           # Graph edges only
```

### Visual Graph Keys

```
visual:supply-chain              # Supply chain visualization
visual:ownership                 # Ownership tree
visual:cluster                   # Cluster visualization
visual:interactive-models        # Interactive models list
```

### News Data Keys

```
news:{news_id}                   # Individual news item
news:list:{sort_by}              # News list
news:ticker:{ticker}:{limit}      # News by ticker
```

### Session & WebSocket Keys

```
session:{user_id}                # User session data
ws:channel:{user_id}             # WebSocket channel
ws:subscription:{ticker}         # WebSocket subscription
```

### Rate Limiting Keys

```
ratelimit:{endpoint}:{user_id}   # Rate limit counter
ratelimit:ip:{ip_address}        # IP-based rate limit
```

---

## 5. TTL (Time To Live) Strategy

### What TTL Does

TTL automatically expires and deletes keys after a specified time:
- **Automatic deletion**: Redis removes expired keys in the background
- **No manual cleanup**: Expired keys are handled automatically
- **Memory efficiency**: Prevents unbounded cache growth
- **Fresh data**: Ensures cached data doesn't become stale

### TTL Configuration for TinBoker

Define TTL values based on data freshness requirements:

```python
# src/cache/cache_config.py

CACHE_TTL = {
    # Stock prices change frequently - short TTL
    "stock_info": 300,        # 5 minutes
    "stock_basic": 300,        # 5 minutes
    "stock_price": 60,         # 1 minute (most volatile)
    
    # Stock lists change often - very short TTL
    "stock_list": 60,          # 1 minute
    
    # Historical data rarely changes - long TTL
    "stock_ohlcv": 3600,       # 1 hour
    "stock_history": 86400,    # 24 hours
    
    # Graph structure changes rarely - medium TTL
    "graph_data": 1800,        # 30 minutes
    "graph_list": 600,         # 10 minutes
    
    # Visual graphs include prices - short TTL
    "visual_graph": 300,       # 5 minutes
    
    # News articles don't change - long TTL
    "news_item": 3600,         # 1 hour
    "news_list": 300,          # 5 minutes
    "news_ticker": 1800,       # 30 minutes
    
    # Session data
    "session": 3600,           # 1 hour
    "ws_subscription": 300,    # 5 minutes
}
```

### Using TTL in Code

```python
import json
from src.cache.redis_client import cache_set, cache_get
from src.cache.cache_config import CACHE_TTL

# Set with TTL
async def cache_stock_info(ticker: str, data: dict):
    cache_key = f"stock:{ticker.upper()}:info"
    ttl = CACHE_TTL["stock_info"]
    await cache_set(cache_key, json.dumps(data, default=str), ttl)

# Get with automatic expiration
async def get_cached_stock_info(ticker: str) -> Optional[dict]:
    cache_key = f"stock:{ticker.upper()}:info"
    cached = await cache_get(cache_key)
    if cached:
        return json.loads(cached)
    return None

# Check remaining TTL
async def get_cache_ttl(key: str) -> int:
    """Returns: -2 (doesn't exist), -1 (no expiration), or seconds remaining"""
    redis = await get_redis()
    if redis:
        return await redis.ttl(key)
    return -2
```

---

## 6. Caching Implementation Patterns

### Pattern 1: Cache-Aside (Lazy Loading)

Most common pattern - check cache first, fetch on miss:

```python
async def get_stock_info(ticker: str) -> Optional[CompanyDetail]:
    """Get stock info with caching"""
    cache_key = f"stock:{ticker.upper()}:info"
    
    # 1. Check cache first
    cached = await cache_get(cache_key)
    if cached:
        return CompanyDetail(**json.loads(cached))
    
    # 2. Cache miss - fetch from API
    stock_data = data_collection_service.collect_stock_data(ticker)
    if not stock_data:
        return None
    
    result = _convert_stock_to_company_detail(stock_data)
    
    # 3. Store in cache
    await cache_set(
        cache_key,
        json.dumps(result.dict(), default=str),
        CACHE_TTL["stock_info"]
    )
    
    return result
```

### Pattern 2: Cache Decorator

Reusable decorator for automatic caching:

```python
from functools import wraps
import hashlib

def cached(ttl: int = 300, key_prefix: str = ""):
    """Decorator to cache function results"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            key_parts = [key_prefix, func.__name__]
            key_parts.extend([str(arg) for arg in args])
            key_parts.extend([f"{k}:{v}" for k, v in sorted(kwargs.items())])
            cache_key = ":".join(key_parts)
            
            # Try cache
            cached = await cache_get(cache_key)
            if cached:
                return json.loads(cached)
            
            # Execute and cache
            result = await func(*args, **kwargs)
            if result:
                await cache_set(cache_key, json.dumps(result, default=str), ttl)
            
            return result
        return wrapper
    return decorator

# Usage
@cached(ttl=CACHE_TTL["stock_info"], key_prefix="stock")
async def get_stock_info(ticker: str):
    # ... fetch logic ...
    return stock_data
```

### Pattern 3: Cache Stampede Prevention

Prevent multiple simultaneous requests for the same data:

```python
import asyncio

async def get_with_lock(cache_key: str, fetch_func, ttl: int):
    """Get data with lock to prevent cache stampede"""
    # Try cache first
    cached = await cache_get(cache_key)
    if cached:
        return json.loads(cached)
    
    # Try to acquire lock
    lock_key = f"{cache_key}:lock"
    redis = await get_redis()
    
    lock_acquired = await redis.set(lock_key, "1", nx=True, ex=10)
    
    if lock_acquired:
        # We got the lock, fetch data
        try:
            data = await fetch_func()
            await cache_set(cache_key, json.dumps(data, default=str), ttl)
            return data
        finally:
            await cache_delete(lock_key)
    else:
        # Wait for other request to finish
        await asyncio.sleep(0.1)
        # Retry getting from cache
        cached = await cache_get(cache_key)
        if cached:
            return json.loads(cached)
        # If still not cached, retry with lock
        return await get_with_lock(cache_key, fetch_func, ttl)
```

### Pattern 4: Stale-While-Revalidate

Return stale data immediately while refreshing in background:

```python
async def get_with_stale_revalidate(
    cache_key: str,
    fetch_func,
    ttl: int,
    stale_threshold: int = 60
):
    """Get data with stale-while-revalidate pattern"""
    cached = await cache_get(cache_key)
    if cached:
        redis = await get_redis()
        ttl_remaining = await redis.ttl(cache_key)
        
        # If almost expired, return stale but refresh in background
        if ttl_remaining < stale_threshold:
            # Return stale data immediately
            asyncio.create_task(refresh_cache(cache_key, fetch_func, ttl))
            return json.loads(cached)
        
        return json.loads(cached)
    
    # Cache miss - fetch fresh
    data = await fetch_func()
    await cache_set(cache_key, json.dumps(data, default=str), ttl)
    return data

async def refresh_cache(cache_key: str, fetch_func, ttl: int):
    """Background task to refresh cache"""
    try:
        data = await fetch_func()
        await cache_set(cache_key, json.dumps(data, default=str), ttl)
    except Exception as e:
        logger.error(f"Failed to refresh cache {cache_key}: {e}")
```

---

## 7. Cache Invalidation Strategies

### Strategy 1: Time-Based (TTL)

Let cache expire naturally - simplest approach:

```python
# TTL handles expiration automatically
await cache_set(key, value, ttl=300)  # Expires in 5 minutes
```

### Strategy 2: Event-Based Invalidation

Invalidate cache when data is updated:

```python
async def update_stock_price(ticker: str, new_price: float):
    """Update stock price and invalidate related cache"""
    # Update in database/API
    await update_price_in_db(ticker, new_price)
    
    # Invalidate related cache keys
    await cache_delete(f"stock:{ticker}:info")
    await cache_delete(f"stock:{ticker}:basic")
    await cache_delete(f"stock:{ticker}:price")
    
    # Invalidate stock lists (pattern delete)
    await cache_delete_pattern("stock:list:*")
    
    return new_price
```

### Strategy 3: Version-Based Keys

Add version to cache key for easy invalidation:

```python
async def get_stock_info_versioned(ticker: str):
    """Get stock info with version-based caching"""
    # Get current version
    version_key = f"stock:{ticker}:version"
    redis = await get_redis()
    version = await redis.get(version_key) or "0"
    
    cache_key = f"stock:{ticker}:info:v{version}"
    
    cached = await cache_get(cache_key)
    if cached:
        return json.loads(cached)
    
    # Fetch and cache
    data = await fetch_stock_info(ticker)
    await cache_set(cache_key, json.dumps(data), CACHE_TTL["stock_info"])
    
    return data

async def invalidate_stock_cache(ticker: str):
    """Invalidate by incrementing version"""
    version_key = f"stock:{ticker}:version"
    redis = await get_redis()
    await redis.incr(version_key)
    # Old cache keys become orphaned (can be cleaned up later)
```

---

## 8. Implementation Examples for TinBoker

### Example 1: Stock Service with Caching

```python
# src/services/stock.py (enhanced with caching)

from src.cache.redis_client import cache_get, cache_set, cache_delete
from src.cache.cache_config import CACHE_TTL
import json

class StockService:
    async def get_stock_info(self, ticker: str) -> Optional[CompanyDetail]:
        """Get stock info with caching"""
        cache_key = f"stock:{ticker.upper()}:info"
        
        # Check cache
        cached = await cache_get(cache_key)
        if cached:
            return CompanyDetail(**json.loads(cached))
        
        # Fetch from API
        stock_data = self.data_collection_service.collect_stock_data(ticker)
        if not stock_data:
            return None
        
        result = self._convert_stock_to_company_detail(stock_data)
        
        # Cache result
        await cache_set(
            cache_key,
            json.dumps(result.dict(), default=str),
            CACHE_TTL["stock_info"]
        )
        
        return result
    
    async def get_sorted_stocks(self, sort_by: str = "ticker", limit: int = 50):
        """Get sorted stocks with caching"""
        cache_key = f"stock:list:{sort_by}:{limit}"
        
        # Check cache
        cached = await cache_get(cache_key)
        if cached:
            return json.loads(cached)
        
        # Fetch from API
        stocks_data = self.data_collection_service.get_all_stocks(limit=limit)
        stocks_list = [self._format_stock_dict(s) for s in stocks_data]
        stocks_list.sort(key=lambda x: x.get(sort_by, ""))
        
        # Cache result
        await cache_set(
            cache_key,
            json.dumps(stocks_list, default=str),
            CACHE_TTL["stock_list"]
        )
        
        return stocks_list
```

### Example 2: Visual Graph Service with Caching

```python
# src/services/visual_graph.py (enhanced with caching)

class VisualGraphService:
    async def get_supply_chain_data(self) -> Dict[str, Any]:
        """Get supply chain data with caching"""
        cache_key = "visual:supply-chain"
        
        # Check cache
        cached = await cache_get(cache_key)
        if cached:
            return json.loads(cached)
        
        # Generate graph structure
        graph_structure = get_supply_chain_structure()
        
        # Enrich nodes (this is expensive - multiple API calls)
        enriched_nodes = []
        for node in graph_structure["nodes"]:
            enriched_node = await self._enrich_node_with_financials(node)
            enriched_nodes.append(enriched_node)
        
        result = {
            "data": {
                "nodes": enriched_nodes,
                "edges": graph_structure["edges"],
            },
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        
        # Cache result (5 minutes - includes real-time prices)
        await cache_set(
            cache_key,
            json.dumps(result, default=str),
            CACHE_TTL["visual_graph"]
        )
        
        return result
```

---

## 9. WebSocket Pub/Sub Implementation

### Publisher (when stock price updates)

```python
async def publish_stock_update(ticker: str, data: dict):
    """Publish stock update to Redis channel"""
    redis = await get_redis()
    if redis:
        channel = f"stock:{ticker.upper()}:updates"
        await redis.publish(channel, json.dumps(data))
```

### Subscriber (WebSocket handler)

```python
async def websocket_stock_updates(websocket: WebSocket, ticker: str):
    """WebSocket endpoint with Redis pub/sub"""
    await websocket.accept()
    redis = await get_redis()
    
    if not redis:
        await websocket.close(code=1011, reason="Redis not available")
        return
    
    channel = f"stock:{ticker.upper()}:updates"
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = json.loads(message["data"])
                await websocket.send_json(data)
    except WebSocketDisconnect:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
```

---

## 10. Rate Limiting with Redis

```python
async def check_rate_limit(endpoint: str, user_id: str, limit: int = 100, window: int = 60):
    """Check if request is within rate limit"""
    redis = await get_redis()
    if not redis:
        return True  # Allow if Redis unavailable
    
    key = f"ratelimit:{endpoint}:{user_id}"
    
    # Increment counter
    current = await redis.incr(key)
    
    # Set expiration on first request
    if current == 1:
        await redis.expire(key, window)
    
    # Check if over limit
    if current > limit:
        return False
    
    return True
```

---

## 11. Monitor Redis

### Redis CLI Commands

```bash
# Connect to Redis
redis-cli

# Monitor all commands in real-time
redis-cli monitor

# Check memory usage
redis-cli info memory

# Check connected clients
redis-cli info clients

# List all keys (use with caution in production)
redis-cli keys "*"

# Count keys
redis-cli dbsize

# Get key info
redis-cli object idletime stock:AAPL:info
redis-cli ttl stock:AAPL:info

# Check server info
redis-cli info server
redis-cli info stats

# Flush all data (DANGER - only for dev)
redis-cli flushall

# Flush current database
redis-cli flushdb
```

### Python Monitoring

```python
async def get_cache_stats():
    """Get cache statistics"""
    redis = await get_redis()
    if not redis:
        return None
    
    info = await redis.info()
    stats = {
        "connected_clients": info.get("connected_clients", 0),
        "used_memory_human": info.get("used_memory_human", "0B"),
        "used_memory_peak_human": info.get("used_memory_peak_human", "0B"),
        "keyspace_hits": info.get("keyspace_hits", 0),
        "keyspace_misses": info.get("keyspace_misses", 0),
        "total_keys": await redis.dbsize(),
    }
    
    # Calculate hit rate
    total_requests = stats["keyspace_hits"] + stats["keyspace_misses"]
    if total_requests > 0:
        stats["hit_rate"] = stats["keyspace_hits"] / total_requests
    else:
        stats["hit_rate"] = 0
    
    return stats
```

### RedisInsight (GUI Tool)

Download from: https://redis.com/redis-enterprise/redis-insight/

Features:
- Visual key browser
- Real-time monitoring
- Command execution
- Memory analysis

---

## 12. Production Deployment

### Render.com (Already Configured)

Your `render.yaml` already includes Redis:

```yaml
services:
  - type: redis
    name: tinboker-redis
    plan: starter
```

The `REDIS_URL` environment variable is automatically provided.

### Other Cloud Providers

**AWS ElastiCache:**
- Use Redis 7.x
- Enable encryption in transit
- Configure security groups
- Use cluster mode for high availability

**GCP Memorystore:**
- Managed Redis service
- Automatic backups
- High availability options

**Azure Cache for Redis:**
- Standard or Premium tier
- Geo-replication available
- Built-in monitoring

### Production Best Practices

1. **Enable Authentication:**
   ```python
   redis_url = "redis://:password@host:port/db"
   ```

2. **Use TLS/SSL:**
   ```python
   redis_url = "rediss://:password@host:port/db"  # Note: rediss://
   ```

3. **Connection Pooling:**
   ```python
   # Already handled by aioredis with max_connections
   ```

4. **Monitor Memory:**
   - Set `maxmemory` limit
   - Use `allkeys-lru` eviction policy
   - Monitor memory usage

5. **High Availability:**
   - Use Redis Sentinel or Cluster
   - Configure replicas
   - Test failover scenarios

---

## 13. Backup & Persistence Strategy

### For Cache-Only (Recommended for TinBoker)

Since cache can be regenerated, persistence is optional:

```conf
# Disable persistence for better performance
save ""
appendonly no
```

### For Critical Data

If you store important data in Redis:

```conf
# RDB snapshots
save 900 1
save 300 10
save 60 10000

# AOF (Append Only File)
appendonly yes
appendfsync everysec
```

### Backup Script

```bash
#!/bin/bash
# backup-redis.sh

DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/backups/redis"
mkdir -p $BACKUP_DIR

# Create RDB backup
redis-cli --rdb $BACKUP_DIR/dump_$DATE.rdb

# Upload to S3 (optional)
aws s3 cp $BACKUP_DIR/dump_$DATE.rdb s3://your-bucket/redis-backups/
```

---

## 14. Performance Optimization Tips

### 1. Use Pipeline for Multiple Operations

```python
async def cache_multiple_stocks(stocks: dict):
    """Cache multiple stocks efficiently"""
    redis = await get_redis()
    if not redis:
        return
    
    pipe = redis.pipeline()
    for ticker, data in stocks.items():
        key = f"stock:{ticker}:info"
        pipe.setex(key, CACHE_TTL["stock_info"], json.dumps(data))
    
    await pipe.execute()  # Execute all at once
```

### 2. Compress Large Values

```python
import gzip
import base64

async def cache_large_data(key: str, data: dict, ttl: int):
    """Cache large data with compression"""
    json_str = json.dumps(data, default=str)
    compressed = gzip.compress(json_str.encode())
    encoded = base64.b64encode(compressed).decode()
    
    await cache_set(key, encoded, ttl)

async def get_cached_large_data(key: str) -> Optional[dict]:
    """Retrieve and decompress large data"""
    cached = await cache_get(key)
    if not cached:
        return None
    
    compressed = base64.b64decode(cached)
    json_str = gzip.decompress(compressed).decode()
    return json.loads(json_str)
```

### 3. Batch Operations

```python
async def get_multiple_stocks(tickers: List[str]) -> Dict[str, dict]:
    """Get multiple stocks efficiently"""
    redis = await get_redis()
    if not redis:
        return {}
    
    # Get all at once
    keys = [f"stock:{t.upper()}:info" for t in tickers]
    values = await redis.mget(keys)
    
    result = {}
    for ticker, value in zip(tickers, values):
        if value:
            result[ticker] = json.loads(value)
        else:
            # Cache miss - fetch individually
            stock = await fetch_stock_info(ticker)
            if stock:
                result[ticker] = stock
    
    return result
```

---

## 15. Expected Performance Improvements

With proper caching implementation:

| Endpoint | Before | After | Improvement |
|----------|--------|-------|-------------|
| `GET /api/stocks/{ticker}` | 500-2000ms | 1-5ms | **99%+ faster** |
| `GET /api/stocks` | 1000-3000ms | 10-50ms | **95%+ faster** |
| `GET /api/visuals/supply-chain` | 2000-5000ms | 50-200ms | **90%+ faster** |
| External API calls | 100% | 5-20% | **80-95% reduction** |
| Database queries | 100% | 20-40% | **60-80% reduction** |

---

## 16. Troubleshooting

### Common Issues

**1. Redis Connection Failed**
```python
# Check if Redis is running
redis-cli ping

# Check connection string
print(settings.redis_connection_string)

# Test connection
redis = await aioredis.from_url(settings.redis_connection_string)
await redis.ping()
```

**2. Memory Issues**
```bash
# Check memory usage
redis-cli info memory

# Check max memory setting
redis-cli config get maxmemory

# Set max memory
redis-cli config set maxmemory 2gb
```

**3. Keys Not Expiring**
```python
# Check TTL
ttl = await redis.ttl("stock:AAPL:info")
# -2: doesn't exist, -1: no expiration, >0: seconds remaining

# Manually set expiration
await redis.expire("stock:AAPL:info", 300)
```

**4. Cache Not Working**
```python
# Verify key exists
exists = await redis.exists("stock:AAPL:info")

# Get raw value
value = await redis.get("stock:AAPL:info")
print(value)  # Check if it's valid JSON

# Check if Redis is actually being used
# Add logging to cache_get/cache_set functions
```

---

## 17. Testing Caching

### Unit Tests

```python
import pytest
from src.cache.redis_client import cache_set, cache_get, cache_delete

@pytest.mark.asyncio
async def test_cache_set_get():
    """Test basic cache operations"""
    key = "test:key"
    value = {"test": "data"}
    
    # Set
    await cache_set(key, json.dumps(value), ttl=60)
    
    # Get
    cached = await cache_get(key)
    assert cached is not None
    assert json.loads(cached) == value
    
    # Delete
    await cache_delete(key)
    cached = await cache_get(key)
    assert cached is None

@pytest.mark.asyncio
async def test_cache_expiration():
    """Test TTL expiration"""
    key = "test:expire"
    await cache_set(key, "value", ttl=1)
    
    # Should exist immediately
    assert await cache_get(key) == "value"
    
    # Wait for expiration
    await asyncio.sleep(2)
    
    # Should be expired
    assert await cache_get(key) is None
```

---

## Summary

This guide provides a complete Redis setup and caching strategy for TinBoker Backend:

✅ **Installation** - Local, Docker, and production options  
✅ **Configuration** - Optimized settings for caching  
✅ **Client Setup** - Async Redis client for FastAPI  
✅ **Key Naming** - Structured naming convention  
✅ **TTL Strategy** - Time-based expiration configuration  
✅ **Caching Patterns** - Multiple implementation patterns  
✅ **Cache Invalidation** - Strategies for keeping data fresh  
✅ **Performance** - Optimization techniques  
✅ **Monitoring** - Tools and commands for observability  
✅ **Production** - Deployment best practices  

**Next Steps:**
1. Install Redis locally or use Docker
2. Add `aioredis` to `requirements.txt`
3. Create `src/cache/redis_client.py` with the provided code
4. Implement caching in `StockService` and `VisualGraphService`
5. Test and monitor cache hit rates
6. Deploy to production with Render.com Redis service

