# WebSocket Testing Guide

## Overview

This guide explains how to test the WebSocket implementation for real-time stock price updates.

## Prerequisites

1. **Server Running**: FastAPI server must be running
2. **Redis Running**: Redis must be available for pub/sub
3. **Background Worker**: Publisher worker should be running (optional for basic tests)
4. **Massive API Key**: Configured in environment (optional for basic tests)

## Starting the Server

```bash
# Start FastAPI server
cd /home/lewis/tinboker/backend
uvicorn src.main:app --host 0.0.0.0 --port 3000 --reload
```

## Starting the Publisher Worker

The publisher worker connects to Massive WebSocket and publishes updates to Redis:

```bash
# Set monitored tickers (optional, defaults to AAPL,GOOGL,MSFT,NVDA,TSLA)
export MONITORED_TICKERS=AAPL,TSLA,NVDA

# Start the worker
python3 -m src.workers.stock_price_publisher
```

## Testing WebSocket Endpoint

### Test Scripts

Two test scripts are available:

1. **Simple Test** (`scripts/test_websocket_simple.py`):
   - Basic connectivity test
   - Subscribe to a ticker
   - Quick validation

2. **Comprehensive Test** (`scripts/test_websocket_prices.py`):
   - Full test suite
   - Tests all features: subscribe, unsubscribe, ping/pong, error handling
   - Tests price update reception

### Running Tests

```bash
# Simple test
python3 scripts/test_websocket_simple.py --port 3000

# Comprehensive test suite
python3 scripts/test_websocket_prices.py --port 3000

# Test specific feature
python3 scripts/test_websocket_prices.py --port 3000 --test subscribe
python3 scripts/test_websocket_prices.py --port 3000 --test updates
```

### Manual Testing with Python

```python
import asyncio
import json
from websockets import connect

async def test():
    async with connect("ws://localhost:3000/ws/prices") as websocket:
        # Receive connection confirmation
        msg = await websocket.recv()
        print("Connected:", json.loads(msg))
        
        # Subscribe to tickers
        await websocket.send(json.dumps({
            "type": "subscribe",
            "tickers": ["AAPL", "TSLA"]
        }))
        
        # Receive subscription confirmation
        msg = await websocket.recv()
        print("Subscribed:", json.loads(msg))
        
        # Wait for price updates
        for i in range(5):
            msg = await websocket.recv()
            data = json.loads(msg)
            print(f"Update {i+1}:", data)

asyncio.run(test())
```

### Manual Testing with JavaScript (Browser Console)

```javascript
const ws = new WebSocket('ws://localhost:3000/ws/prices');

ws.onopen = () => {
    console.log('Connected');
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Received:', data);
    
    if (data.type === 'connected') {
        // Subscribe to tickers
        ws.send(JSON.stringify({
            type: 'subscribe',
            tickers: ['AAPL', 'TSLA']
        }));
    }
};

ws.onerror = (error) => {
    console.error('WebSocket error:', error);
};

ws.onclose = () => {
    console.log('Disconnected');
};
```

### Manual Testing with curl (for HTTP endpoints)

```bash
# Test health endpoint
curl http://localhost:3000/health

# Test stock endpoint
curl http://localhost:3000/api/stocks/AAPL
```

## Testing Redis Pub/Sub Directly

You can test Redis pub/sub independently:

```bash
# Terminal 1: Subscribe to channel
redis-cli
> SUBSCRIBE stock:AAPL:ohlcv

# Terminal 2: Publish a test message
redis-cli
> PUBLISH stock:AAPL:ohlcv '{"type":"price_update","data":{"ticker":"AAPL","price":150.25,"change":1.5,"changePercent":1.01,"timestamp":1234567890,"marketStatus":"open"}}'
```

## Expected Behavior

### Connection Flow

1. Client connects to `ws://localhost:3000/ws/prices`
2. Server sends: `{"type": "connected", "message": "WebSocket connection established"}`
3. Client sends subscribe: `{"type": "subscribe", "tickers": ["AAPL"]}`
4. Server sends: `{"type": "subscribed", "tickers": ["AAPL"]}`
5. Server streams price updates: `{"type": "price_update", "data": {...}}`

### Price Update Format

```json
{
  "type": "price_update",
  "data": {
    "ticker": "AAPL",
    "price": 150.25,
    "change": 1.5,
    "changePercent": 1.01,
    "volume": 1000000,
    "timestamp": 1234567890,
    "marketStatus": "open",
    "open": 149.0,
    "high": 151.0,
    "low": 148.5,
    "close": 150.25,
    "previousClose": 148.75
  }
}
```

## Troubleshooting

### Connection Refused

- **Check server is running**: `ps aux | grep uvicorn`
- **Check port**: Default is 3000, verify with `lsof -i :3000`
- **Check firewall**: Ensure port is accessible

### HTTP 403 Forbidden

- **Server needs restart**: Restart the FastAPI server to load new code
- **CORS issue**: Check CORS configuration in `src/main.py`
- **WebSocket not enabled**: Verify WebSocket routes are registered

### No Price Updates Received

- **Publisher worker not running**: Start the publisher worker
- **Redis not available**: Check Redis connection: `redis-cli ping`
- **Tickers not monitored**: Check `MONITORED_TICKERS` environment variable
- **Massive API not configured**: Verify `MASSIVE_API_KEY` is set
- **Market closed**: Updates may be delayed or unavailable outside market hours

### Redis Connection Issues

```bash
# Test Redis connection
redis-cli ping
# Should return: PONG

# Check Redis URL in config
python3 -c "from src.config import settings; print(settings.redis_connection_string)"
```

## Architecture

```
┌─────────────────┐
│  Massive        │
│  WebSocket      │───┐
│  (Publisher)    │   │
└─────────────────┘   │
                      │ PUBLISH
                      ▼
              ┌───────────────┐
              │  Redis        │
              │  Pub/Sub      │
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

## Next Steps

1. **Start server**: `uvicorn src.main:app --reload`
2. **Start publisher worker**: `python3 -m src.workers.stock_price_publisher`
3. **Run tests**: `python3 scripts/test_websocket_prices.py`
4. **Verify updates**: Check Redis channels and WebSocket messages

## Notes

- WebSocket endpoint: `/ws/prices`
- Redis channels: `stock:{TICKER}:ohlcv` and `stock:{TICKER}:price`
- Publisher uses Massive API delayed WebSocket (15-minute delay for Starter plan)
- Multiple clients can subscribe to the same ticker
- Updates are distributed via Redis pub/sub for scalability

