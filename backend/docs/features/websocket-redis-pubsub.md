# WebSocket Implementation with Redis Pub/Sub

This document provides a comprehensive guide for implementing WebSocket functionality using Redis Pub/Sub pattern in the TinBoker Backend project.

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Redis Pub/Sub Concepts](#redis-pubsub-concepts)
4. [Implementation Strategy](#implementation-strategy)
5. [Code Implementation](#code-implementation)
6. [Integration with Existing Code](#integration-with-existing-code)
7. [Best Practices](#best-practices)
8. [Testing](#testing)
9. [Deployment Considerations](#deployment-considerations)

---

## Overview

### Current State

- ✅ Redis is already configured for caching static API responses
- ✅ Basic WebSocket endpoint exists at `/api/stocks/{ticker}/ohlcv`
- ✅ WebSocket currently uses mock data generation
- ⚠️ No Redis pub/sub implementation yet

### Goal

Implement a scalable WebSocket system using Redis Pub/Sub that:
- Allows multiple WebSocket clients to subscribe to the same stock ticker
- Enables background workers to publish updates once and distribute to all subscribers
- Scales horizontally across multiple server instances
- Provides real-time stock price updates efficiently

---

## Architecture

### High-Level Architecture

```
┌─────────────────┐
│  Background      │
│  Worker/Service  │───┐
└─────────────────┘   │
                      │ PUBLISH
                      ▼
              ┌───────────────┐
              │  Redis Server │
              │  (Pub/Sub)    │
              └───────────────┘
                      │
                      │ SUBSCRIBE
        ┌─────────────┼─────────────┐
        │             │             │
        ▼             ▼             ▼
┌───────────┐  ┌───────────┐  ┌───────────┐
│ WebSocket │  │ WebSocket │  │ WebSocket │
│ Client 1  │  │ Client 2  │  │ Client 3  │
└───────────┘  └───────────┘  └───────────┘
```

### Component Roles

1. **Publisher (Background Worker)**
   - Fetches stock data from external APIs (Massive API, FinMind)
   - Publishes updates to Redis channels
   - Runs independently of WebSocket connections

2. **Redis Pub/Sub**
   - Acts as message broker
   - Channels: `stock:{ticker}:ohlcv`, `stock:{ticker}:price`, etc.
   - Decouples publishers from subscribers

3. **Subscriber (WebSocket Endpoint)**
   - Accepts WebSocket connections
   - Subscribes to Redis channels based on client requests
   - Forwards messages from Redis to WebSocket clients

4. **WebSocket Clients**
   - Frontend applications connecting via WebSocket
   - Receive real-time updates pushed from server

---

## Redis Pub/Sub Concepts

### Channels

Redis channels are like topics in a message queue. Messages published to a channel are delivered to all subscribers of that channel.

**Channel Naming Convention:**
```
stock:{ticker}:ohlcv      # OHLCV data updates
stock:{ticker}:price       # Price-only updates
stock:{ticker}:news        # News updates
stock:all:updates          # All stocks updates (if needed)
```

### Commands

**Publisher Side:**
```python
# Publish a message to a channel
await redis.publish("stock:AAPL:ohlcv", json.dumps(data))
```

**Subscriber Side:**
```python
# Create a pubsub object
pubsub = redis.pubsub()

# Subscribe to a channel
await pubsub.subscribe("stock:AAPL:ohlcv")

# Listen for messages
async for message in pubsub.listen():
    if message['type'] == 'message':
        data = message['data']
        # Forward to WebSocket client
```

### Key Benefits

1. **Decoupling**: Publishers don't need to know about subscribers
2. **Scalability**: Multiple servers can subscribe to the same channels
3. **Efficiency**: One publish operation reaches all subscribers
4. **Flexibility**: Easy to add/remove subscribers dynamically

---

## Implementation Strategy

### Phase 1: Redis Pub/Sub Infrastructure

1. **Extend Redis Client**
   - Add pub/sub helper methods
   - Create channel name generators
   - Add connection pooling for pub/sub

2. **Create Publisher Service**
   - Background service that publishes stock updates
   - Can be integrated with existing worker service
   - Handles rate limiting and error recovery

3. **Create Subscriber Manager**
   - Manages WebSocket subscriptions
   - Handles subscription/unsubscription lifecycle
   - Manages connection cleanup

### Phase 2: WebSocket Integration

1. **Update WebSocket Endpoint**
   - Replace mock data generation with Redis subscription
   - Handle multiple clients per ticker
   - Implement graceful disconnection

2. **Connection Management**
   - Track active subscriptions per WebSocket
   - Clean up subscriptions on disconnect
   - Handle reconnection scenarios

### Phase 3: Background Publisher

1. **Stock Update Worker**
   - Poll external APIs for updates
   - Publish to Redis channels
   - Handle API rate limits
   - Support multiple tickers

---

## Code Implementation

### 1. Extend Redis Client for Pub/Sub

**File: `src/cache/redis_client.py`**

Add pub/sub functionality:

```python
from typing import AsyncIterator, Optional
import json
from redis import asyncio as aioredis

class RedisClient:
    """Async Redis client wrapper with pub/sub support"""
    
    _client: Optional[aioredis.Redis] = None
    _pubsub_client: Optional[aioredis.Redis] = None
    
    @classmethod
    async def get_pubsub_client(cls) -> Optional[aioredis.Redis]:
        """Get separate Redis client for pub/sub (recommended)"""
        if cls._pubsub_client is None:
            redis_url = settings.redis_connection_string
            if not redis_url:
                return None
            cls._pubsub_client = aioredis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=10
            )
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
```

### 2. Channel Name Utilities

**File: `src/cache/channels.py`**

```python
"""
Redis channel name utilities for pub/sub
"""

def stock_ohlcv_channel(ticker: str) -> str:
    """Get Redis channel name for stock OHLCV updates"""
    return f"stock:{ticker.upper()}:ohlcv"

def stock_price_channel(ticker: str) -> str:
    """Get Redis channel name for stock price updates"""
    return f"stock:{ticker.upper()}:price"

def stock_news_channel(ticker: str) -> str:
    """Get Redis channel name for stock news updates"""
    return f"stock:{ticker.upper()}:news"

def all_stocks_channel() -> str:
    """Get Redis channel name for all stocks updates"""
    return "stock:all:updates"
```

### 3. Stock Update Publisher Service

**File: `src/services/stock_publisher.py`**

```python
"""
Service for publishing stock updates to Redis channels
"""
import asyncio
import json
import logging
from typing import List, Optional
from datetime import datetime
from src.cache.redis_client import RedisClient
from src.cache.channels import stock_ohlcv_channel, stock_price_channel
from src.services.data_collection_service import DataCollectionService

logger = logging.getLogger(__name__)

class StockPublisher:
    """Publishes stock updates to Redis channels"""
    
    def __init__(self, data_collection_service: Optional[DataCollectionService] = None):
        self.data_collection_service = data_collection_service or DataCollectionService()
        self._running = False
        self._update_interval = 5  # seconds
    
    async def publish_stock_update(self, ticker: str) -> bool:
        """
        Fetch latest stock data and publish to Redis channel.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            True if published successfully, False otherwise
        """
        try:
            # Fetch latest stock data
            stock_data = self.data_collection_service.collect_stock_data(ticker)
            if not stock_data:
                logger.warning(f"No data available for {ticker}")
                return False
            
            # Prepare OHLCV update
            ohlcv_data = {
                "ticker": ticker.upper(),
                "timestamp": int(datetime.now().timestamp() * 1000),
                "date": datetime.now().strftime("%Y-%m-%d"),
                "open": stock_data.open or stock_data.price,
                "high": stock_data.high or stock_data.price,
                "low": stock_data.low or stock_data.price,
                "close": stock_data.price,
                "price": stock_data.price,
                "volume": stock_data.volume or 0,
            }
            
            # Publish to OHLCV channel
            channel = stock_ohlcv_channel(ticker)
            subscribers = await RedisClient.publish_message(channel, ohlcv_data)
            
            if subscribers > 0:
                logger.debug(f"Published {ticker} update to {subscribers} subscribers")
            
            # Also publish price-only update
            price_data = {
                "ticker": ticker.upper(),
                "price": stock_data.price,
                "timestamp": int(datetime.now().timestamp() * 1000),
            }
            price_channel = stock_price_channel(ticker)
            await RedisClient.publish_message(price_channel, price_data)
            
            return True
            
        except Exception as e:
            logger.error(f"Error publishing update for {ticker}: {e}")
            return False
    
    async def start_publishing_loop(self, tickers: List[str], interval: int = 5):
        """
        Start continuous publishing loop for multiple tickers.
        
        Args:
            tickers: List of ticker symbols to monitor
            interval: Update interval in seconds
        """
        self._running = True
        self._update_interval = interval
        
        logger.info(f"Starting stock publisher for {len(tickers)} tickers")
        
        while self._running:
            try:
                # Publish updates for all tickers
                tasks = [self.publish_stock_update(ticker) for ticker in tickers]
                await asyncio.gather(*tasks, return_exceptions=True)
                
                # Wait before next update cycle
                await asyncio.sleep(self._update_interval)
                
            except asyncio.CancelledError:
                logger.info("Stock publisher loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in publisher loop: {e}")
                await asyncio.sleep(self._update_interval)
    
    def stop(self):
        """Stop the publishing loop"""
        self._running = False
```

### 4. WebSocket Subscriber Manager

**File: `src/services/websocket_subscriber.py`**

```python
"""
WebSocket subscriber manager for Redis pub/sub
"""
import asyncio
import json
import logging
from typing import Set, Optional
from fastapi import WebSocket
from redis import asyncio as aioredis
from src.cache.redis_client import RedisClient
from src.cache.channels import stock_ohlcv_channel

logger = logging.getLogger(__name__)

class WebSocketSubscriber:
    """Manages WebSocket subscription to Redis channels"""
    
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.pubsub: Optional[aioredis.client.PubSub] = None
        self.subscribed_channels: Set[str] = set()
        self._listening = False
        self._listen_task: Optional[asyncio.Task] = None
    
    async def subscribe(self, ticker: str) -> bool:
        """
        Subscribe to stock updates for a ticker.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            True if subscribed successfully
        """
        try:
            if not self.pubsub:
                self.pubsub = await RedisClient.create_subscriber()
                if not self.pubsub:
                    logger.error("Failed to create Redis subscriber")
                    return False
            
            channel = stock_ohlcv_channel(ticker)
            await RedisClient.subscribe_channel(self.pubsub, channel)
            self.subscribed_channels.add(channel)
            logger.debug(f"Subscribed to {channel} for WebSocket")
            return True
            
        except Exception as e:
            logger.error(f"Error subscribing to {ticker}: {e}")
            return False
    
    async def unsubscribe(self, ticker: str) -> bool:
        """
        Unsubscribe from stock updates for a ticker.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            True if unsubscribed successfully
        """
        try:
            if not self.pubsub:
                return False
            
            channel = stock_ohlcv_channel(ticker)
            if channel in self.subscribed_channels:
                await RedisClient.unsubscribe_channel(self.pubsub, channel)
                self.subscribed_channels.discard(channel)
                logger.debug(f"Unsubscribed from {channel}")
            return True
            
        except Exception as e:
            logger.error(f"Error unsubscribing from {ticker}: {e}")
            return False
    
    async def start_listening(self):
        """Start listening for messages and forwarding to WebSocket"""
        if self._listening:
            return
        
        if not self.pubsub:
            logger.error("Cannot start listening: no pubsub connection")
            return
        
        self._listening = True
        self._listen_task = asyncio.create_task(self._listen_loop())
    
    async def _listen_loop(self):
        """Internal loop that listens to Redis and forwards to WebSocket"""
        try:
            while self._listening and self.pubsub:
                try:
                    # Get message from Redis (with timeout to allow checking _listening flag)
                    message = await asyncio.wait_for(
                        self.pubsub.get_message(ignore_subscribe_messages=True),
                        timeout=1.0
                    )
                    
                    if message and message['type'] == 'message':
                        # Parse and forward to WebSocket
                        try:
                            data = json.loads(message['data'])
                            await self.websocket.send_json(data)
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON in message: {message['data']}")
                        except Exception as e:
                            logger.error(f"Error sending WebSocket message: {e}")
                            break  # Exit loop on WebSocket error
                            
                except asyncio.TimeoutError:
                    # Timeout is expected - continue loop
                    continue
                except Exception as e:
                    logger.error(f"Error in listen loop: {e}")
                    await asyncio.sleep(1)
                    
        except asyncio.CancelledError:
            logger.debug("Listen loop cancelled")
        finally:
            self._listening = False
    
    async def stop(self):
        """Stop listening and cleanup"""
        self._listening = False
        
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        
        # Unsubscribe from all channels
        for channel in list(self.subscribed_channels):
            ticker = channel.split(':')[1]  # Extract ticker from channel name
            await self.unsubscribe(ticker)
        
        # Close pubsub connection
        if self.pubsub:
            await RedisClient.close_pubsub(self.pubsub)
            self.pubsub = None
```

### 5. Updated WebSocket Endpoint

**File: `src/routers/stock.py`**

Update the existing WebSocket endpoint:

```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from src.services.websocket_subscriber import WebSocketSubscriber
import logging

logger = logging.getLogger(__name__)

@router.websocket("/{ticker}/ohlcv")
async def websocket_ohlcv(websocket: WebSocket, ticker: str):
    """
    WebSocket endpoint for OHLCV data streaming using Redis pub/sub.
    
    Streams real-time OHLCV updates for the specified ticker.
    """
    await websocket.accept()
    ticker_upper = ticker.upper()
    
    subscriber = None
    try:
        # Create subscriber manager
        subscriber = WebSocketSubscriber(websocket)
        
        # Subscribe to ticker updates
        if not await subscriber.subscribe(ticker_upper):
            await websocket.close(code=1011, reason="Failed to subscribe to updates")
            return
        
        # Start listening for messages
        await subscriber.start_listening()
        
        # Keep connection alive and handle client messages (optional)
        while True:
            try:
                # Wait for client message or timeout
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # Handle client messages if needed (e.g., unsubscribe, change ticker)
                logger.debug(f"Received message from client: {data}")
            except asyncio.TimeoutError:
                # Send ping to keep connection alive
                await websocket.send_json({"type": "ping"})
            except WebSocketDisconnect:
                break
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for {ticker_upper}")
    except Exception as e:
        logger.error(f"Error in WebSocket for {ticker_upper}: {e}")
        await websocket.close(code=1011, reason=str(e))
    finally:
        # Cleanup subscription
        if subscriber:
            await subscriber.stop()
```

### 6. Background Worker for Publishing

**File: `src/workers/stock_price_publisher.py`**

```python
"""
Background worker that publishes stock price updates to Redis
"""
import asyncio
import logging
import signal
from typing import List
from src.services.stock_publisher import StockPublisher
from src.config import settings

logger = logging.getLogger(__name__)

class StockPricePublisherWorker:
    """Worker that continuously publishes stock updates"""
    
    def __init__(self):
        self.publisher = StockPublisher()
        self.running = False
        self.tickers: List[str] = []
    
    async def start(self, tickers: List[str], interval: int = 5):
        """
        Start the publisher worker.
        
        Args:
            tickers: List of ticker symbols to monitor
            interval: Update interval in seconds
        """
        self.tickers = tickers
        self.running = True
        
        logger.info(f"Starting stock price publisher worker for {len(tickers)} tickers")
        
        # Start publishing loop
        await self.publisher.start_publishing_loop(tickers, interval)
    
    def stop(self):
        """Stop the worker"""
        self.running = False
        self.publisher.stop()
        logger.info("Stock price publisher worker stopped")

async def main():
    """Main entry point for worker"""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Default tickers to monitor (can be configured via env vars)
    default_tickers = ["AAPL", "GOOGL", "MSFT", "NVDA", "TSLA"]
    
    # Get tickers from environment or use defaults
    import os
    tickers_env = os.getenv("MONITORED_TICKERS", "")
    tickers = [t.strip().upper() for t in tickers_env.split(",") if t.strip()] if tickers_env else default_tickers
    
    # Update interval (seconds)
    interval = int(os.getenv("STOCK_UPDATE_INTERVAL", "5"))
    
    worker = StockPricePublisherWorker()
    
    # Handle shutdown signals
    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        worker.stop()
        asyncio.get_event_loop().stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await worker.start(tickers, interval)
    except KeyboardInterrupt:
        logger.info("Worker interrupted")
    finally:
        worker.stop()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Integration with Existing Code

### 1. Update `src/main.py`

Ensure Redis is initialized before WebSocket connections:

```python
@app.on_event("startup")
async def startup_event():
    """Initialize database and Redis on startup"""
    # ... existing database initialization ...
    
    # Initialize Redis (required for pub/sub)
    await RedisClient.initialize()
    
    # Verify Redis is available
    if await RedisClient.is_available():
        logger.info("Redis initialized - WebSocket pub/sub available")
    else:
        logger.warning("Redis not available - WebSocket pub/sub will be disabled")
```

### 2. Update `render.yaml`

Add worker service for stock publisher:

```yaml
services:
  # ... existing services ...
  
  # Stock price publisher worker
  - type: worker
    name: tinboker-stock-publisher
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: python -m src.workers.stock_price_publisher
    envVars:
      - key: PYTHON_VERSION
        value: 3.11.9
      - key: REDIS_URL
        fromService:
          type: redis
          name: tinboker-redis
          property: connectionString
      - key: MONITORED_TICKERS
        value: AAPL,GOOGL,MSFT,NVDA,TSLA
        sync: false
      - key: STOCK_UPDATE_INTERVAL
        value: 5
        sync: false
```

### 3. Update `requirements.txt`

Ensure Redis dependency is present (already included):
```
redis[hiredis]>=5.0.0
```

---

## Best Practices

### 1. Channel Naming

- Use consistent naming convention: `{resource}:{identifier}:{event_type}`
- Keep channel names short but descriptive
- Use uppercase for tickers to ensure consistency

### 2. Message Format

- Always use JSON for message payloads
- Include timestamp in every message
- Include ticker/identifier in message data (not just channel name)

### 3. Error Handling

- Handle Redis connection failures gracefully
- Implement reconnection logic for pub/sub connections
- Log errors but don't crash the service

### 4. Resource Management

- Always clean up subscriptions on disconnect
- Use separate Redis connections for pub/sub (recommended)
- Set appropriate connection pool sizes

### 5. Performance

- Batch updates when possible
- Use connection pooling
- Monitor Redis memory usage
- Set appropriate TTLs for cached data

### 6. Security

- Validate ticker symbols before subscribing
- Rate limit WebSocket connections per client
- Sanitize all inputs
- Use Redis authentication in production

---

## Testing

### 1. Unit Tests

**File: `tests/test_websocket_subscriber.py`**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.services.websocket_subscriber import WebSocketSubscriber

@pytest.mark.asyncio
async def test_subscribe():
    websocket = AsyncMock()
    subscriber = WebSocketSubscriber(websocket)
    
    # Mock Redis client
    with patch('src.services.websocket_subscriber.RedisClient') as mock_redis:
        mock_pubsub = AsyncMock()
        mock_redis.create_subscriber.return_value = mock_pubsub
        
        result = await subscriber.subscribe("AAPL")
        assert result is True
        assert "stock:AAPL:ohlcv" in subscriber.subscribed_channels
```

### 2. Integration Tests

Test the full flow:
1. Start publisher worker
2. Connect WebSocket client
3. Verify messages are received
4. Test multiple clients for same ticker
5. Test unsubscribe and cleanup

### 3. Manual Testing

**Using Redis CLI:**
```bash
# Subscribe to channel
redis-cli SUBSCRIBE stock:AAPL:ohlcv

# In another terminal, publish a message
redis-cli PUBLISH stock:AAPL:ohlcv '{"ticker":"AAPL","price":150.25}'
```

**Using WebSocket Client:**
```javascript
const ws = new WebSocket('ws://localhost:3000/api/stocks/AAPL/ohlcv');
ws.onmessage = (event) => {
    console.log('Received:', JSON.parse(event.data));
};
```

---

## Deployment Considerations

### 1. Redis Configuration

For production, ensure Redis is configured for pub/sub:
- Sufficient memory for message buffering
- Appropriate `maxmemory-policy` (e.g., `allkeys-lru`)
- Connection limits set appropriately

### 2. Scaling

- Multiple FastAPI instances can subscribe to the same channels
- Publisher worker can run on separate instance
- Redis handles message distribution automatically

### 3. Monitoring

Monitor:
- Number of active WebSocket connections
- Redis memory usage
- Message publish rate
- Subscription count per channel
- WebSocket connection errors

### 4. Fallback Strategy

If Redis is unavailable:
- WebSocket endpoints should return appropriate error
- Consider fallback to polling-based updates
- Log errors for monitoring

### 5. Environment Variables

```env
# Redis
REDIS_URL=redis://localhost:6379/0

# Stock Publisher Worker
MONITORED_TICKERS=AAPL,GOOGL,MSFT
STOCK_UPDATE_INTERVAL=5

# WebSocket
WEBSOCKET_MAX_CONNECTIONS=1000
WEBSOCKET_TIMEOUT=300
```

---

## Migration Path

### Step 1: Add Infrastructure
1. Extend `RedisClient` with pub/sub methods
2. Create channel utilities
3. Add tests

### Step 2: Create Publisher
1. Implement `StockPublisher` service
2. Create background worker
3. Test publishing to Redis

### Step 3: Update WebSocket
1. Implement `WebSocketSubscriber`
2. Update WebSocket endpoint
3. Test end-to-end flow

### Step 4: Deploy
1. Deploy updated code
2. Start publisher worker
3. Monitor and verify

### Step 5: Remove Old Code
1. Remove mock data generation
2. Clean up unused code
3. Update documentation

---

## Troubleshooting

### Issue: Messages not received

**Check:**
- Redis connection status
- Channel names match exactly
- Subscriber is actually listening
- Publisher is actually publishing

**Debug:**
```python
# Check active subscriptions
redis-cli PUBSUB NUMSUB stock:AAPL:ohlcv

# Monitor all pub/sub activity
redis-cli MONITOR
```

### Issue: High Memory Usage

**Solutions:**
- Reduce message frequency
- Compress message payloads
- Set appropriate Redis maxmemory
- Monitor slow subscribers

### Issue: Connection Drops

**Solutions:**
- Implement reconnection logic
- Add heartbeat/ping messages
- Monitor connection health
- Set appropriate timeouts

---

## Additional Resources

- [Redis Pub/Sub Documentation](https://redis.io/docs/manual/pubsub/)
- [FastAPI WebSocket Guide](https://fastapi.tiangolo.com/advanced/websockets/)
- [aioredis Documentation](https://aioredis.readthedocs.io/)

---

## Summary

This implementation provides:

✅ **Scalable Architecture**: Multiple servers can handle WebSocket connections
✅ **Efficient Updates**: One publish reaches all subscribers
✅ **Decoupled Design**: Publishers and subscribers are independent
✅ **Production Ready**: Error handling, logging, and monitoring included
✅ **Easy Integration**: Works with existing Redis setup

The system is ready for horizontal scaling and can handle thousands of concurrent WebSocket connections efficiently.

