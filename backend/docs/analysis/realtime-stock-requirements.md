# Real-Time Stock Price Updates & Timeframe Selection Requirements

## Overview

This document outlines the requirements for implementing dynamic, real-time stock price updates with timeframe selection (1D, 1W, 1M, 1Y, etc.) in the TinBoker WebUI Stock Dashboard, similar to platforms like Yahoo Finance and Google Finance.

## Table of Contents

1. [Features](#features)
2. [Data Structures](#data-structures)
3. [WebSocket Architecture](#websocket-architecture)
4. [Backend Requirements](#backend-requirements)
5. [Frontend Requirements](#frontend-requirements)
6. [Implementation Phases](#implementation-phases)

---

## Features

### 1. Real-Time Price Updates
- **Live price updates** during market hours (and optionally pre-market/after-hours)
- **Automatic price refresh** without page reload
- **Visual indicators** for price changes (color coding, animations)
- **Connection status** indicator (connected/disconnected/reconnecting)

### 2. Timeframe Selection
- **Multiple timeframes**: 1H (hourly), 1D (daily), 1W (weekly), 1M (monthly), 3M (3 months), 6M (6 months), 1Y (yearly), YTD (year-to-date), ALL
- **Dynamic chart filtering** based on selected timeframe
- **Persistent timeframe selection** (remember user preference)
- **Smooth chart transitions** when switching timeframes

### 3. Enhanced Chart Display
- **Larger, interactive chart** (replacing small sparkline)
- **Timeframe selector buttons** (similar to Landing page)
- **Chart controls**: zoom, pan, crosshair
- **Price tooltips** on hover
- **Volume overlay** (optional)

---

## Data Structures

### 1. Real-Time Price Update (WebSocket Message)

```typescript
interface RealTimePriceUpdate {
  type: 'price_update';
  ticker: string;
  price: number;              // Current price
  change: number;             // Absolute change from previous close
  changePercent: number;      // Percentage change (e.g., 2.5 for +2.5%)
  volume?: number;            // Trading volume
  timestamp: number;          // Unix timestamp (milliseconds)
  marketStatus: 'open' | 'closed' | 'pre-market' | 'after-hours';
  
  // Optional extended data
  bid?: number;              // Bid price
  ask?: number;              // Ask price
  high?: number;             // Day's high
  low?: number;              // Day's low
  open?: number;             // Opening price
  previousClose?: number;    // Previous day's close
}
```

### 2. Historical Chart Data (REST API Response)

The existing `CompanyDetail` interface should be extended to support timeframe-specific queries:

```typescript
interface CompanyDetail {
  ticker: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  marketCap: number;
  revenue?: number;
  pe?: number;
  dividendYield?: number;
  about: string;
  stats: {
    volume: number;
    beta: number;
    volatility: number;
  };
  chartData: ChartDataPoint[];  // Filtered by requested timeframe
}

interface ChartDataPoint {
  timestamp: number;         // Unix timestamp (milliseconds)
  price: number;             // For backward compatibility
  date?: string;            // ISO date string (YYYY-MM-DD)
  
  // OHLCV data (required for accurate charting)
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}
```

### 3. Timeframe Options

```typescript
type TimeframeOption = 
  | '1H'   // 1 Hour (intraday)
  | '1D'   // 1 Day
  | '1W'   // 1 Week
  | '1M'   // 1 Month
  | '3M'   // 3 Months
  | '6M'   // 6 Months
  | '1Y'   // 1 Year
  | 'YTD'  // Year to Date
  | 'ALL'; // All available data
```

### 4. WebSocket Message Types

```typescript
// Client → Server Messages
interface SubscribeMessage {
  type: 'subscribe';
  tickers: string[];  // Array of ticker symbols to subscribe to
}

interface UnsubscribeMessage {
  type: 'unsubscribe';
  tickers: string[];  // Array of ticker symbols to unsubscribe from
}

interface HeartbeatMessage {
  type: 'ping';
}

// Server → Client Messages
interface PriceUpdateMessage {
  type: 'price_update';
  data: RealTimePriceUpdate;
}

interface SubscriptionConfirmation {
  type: 'subscribed';
  tickers: string[];
}

interface ErrorMessage {
  type: 'error';
  code: string;
  message: string;
}

interface HeartbeatResponse {
  type: 'pong';
}
```

---

## WebSocket Architecture

### Connection Details

- **Endpoint**: `wss://api.example.com/ws/prices` (or `/ws/stocks` or similar)
- **Protocol**: WebSocket (WSS for production)
- **Reconnection**: Automatic with exponential backoff
- **Heartbeat**: Client sends ping every 30 seconds, expects pong within 5 seconds

### Connection Flow

```
1. Client establishes WebSocket connection
2. Server sends connection confirmation
3. Client subscribes to ticker(s): { type: 'subscribe', tickers: ['TSLA'] }
4. Server confirms subscription: { type: 'subscribed', tickers: ['TSLA'] }
5. Server streams price updates: { type: 'price_update', data: {...} }
6. Client updates UI with new prices
7. On disconnect, client attempts reconnection with exponential backoff
```

### Subscription Management

- **Multiple tickers**: Client can subscribe to multiple tickers in one message
- **Dynamic subscription**: Client can add/remove tickers without reconnecting
- **Unsubscribe on unmount**: Client should unsubscribe when component unmounts or user navigates away

### Error Handling

- **Connection errors**: Automatic reconnection with exponential backoff (1s, 2s, 4s, 8s, max 30s)
- **Invalid ticker**: Server responds with error message, client handles gracefully
- **Rate limiting**: Server may throttle updates, client should handle gracefully
- **Network issues**: Show connection status indicator to user

---

## Backend Requirements

### 1. WebSocket Endpoint

**Endpoint**: `wss://api.example.com/ws/prices`

**Required Capabilities**:
- Accept WebSocket connections
- Handle subscription/unsubscription messages
- Stream real-time price updates for subscribed tickers
- Support multiple concurrent clients
- Handle connection cleanup on disconnect
- Implement heartbeat/ping-pong mechanism

**Example Implementation (FastAPI)**:
```python
from fastapi import WebSocket, WebSocketDisconnect
from typing import Set

class PriceWebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, ticker: str):
        await websocket.accept()
        if ticker not in self.active_connections:
            self.active_connections[ticker] = set()
        self.active_connections[ticker].add(websocket)
    
    async def disconnect(self, websocket: WebSocket, ticker: str):
        if ticker in self.active_connections:
            self.active_connections[ticker].discard(websocket)
    
    async def broadcast_price_update(self, ticker: str, update: dict):
        if ticker in self.active_connections:
            for connection in self.active_connections[ticker]:
                try:
                    await connection.send_json(update)
                except:
                    # Handle disconnected clients
                    pass

@app.websocket("/ws/prices")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    subscribed_tickers = set()
    
    try:
        while True:
            data = await websocket.receive_json()
            
            if data["type"] == "subscribe":
                tickers = data["tickers"]
                subscribed_tickers.update(tickers)
                await websocket.send_json({
                    "type": "subscribed",
                    "tickers": list(subscribed_tickers)
                })
            
            elif data["type"] == "unsubscribe":
                tickers = data["tickers"]
                subscribed_tickers.difference_update(tickers)
            
            elif data["type"] == "ping":
                await websocket.send_json({"type": "pong"})
    
    except WebSocketDisconnect:
        # Cleanup subscriptions
        pass
```

### 2. REST API Enhancement

**Existing Endpoint**: `GET /api/stocks/{ticker}`

**New Query Parameter**: `timeframe`

**Examples**:
- `GET /api/stocks/TSLA?timeframe=1D` - Returns last 24 hours of data
- `GET /api/stocks/TSLA?timeframe=1M` - Returns last 30 days of data
- `GET /api/stocks/TSLA?timeframe=1Y` - Returns last 365 days of data
- `GET /api/stocks/TSLA?timeframe=1H` - Returns last hour of intraday data

**Response**: Same `CompanyDetail` structure, but `chartData` array filtered/aggregated by timeframe

**Data Aggregation Rules**:
- **1H**: Return intraday minute-by-minute or 5-minute candles
- **1D**: Return hourly candles or daily single point
- **1W**: Return daily candles (7 points)
- **1M**: Return daily candles (~30 points)
- **3M**: Return daily candles (~90 points)
- **6M**: Return daily candles (~180 points)
- **1Y**: Return daily or weekly candles (~252 trading days or ~52 weeks)
- **YTD**: Return all data points from January 1st to today
- **ALL**: Return all available historical data

### 3. Price Data Source Integration

**Requirements**:
- Integrate with market data provider (e.g., Alpha Vantage, IEX Cloud, Polygon.io, Yahoo Finance API)
- Real-time price feed for WebSocket updates
- Historical data API for timeframe queries
- Handle market hours (9:30 AM - 4:00 PM ET for US markets)
- Support pre-market (4:00 AM - 9:30 AM ET) and after-hours (4:00 PM - 8:00 PM ET)

**Data Provider Considerations**:
- **Free tier limitations**: May have rate limits, delayed data (15-20 minutes)
- **Paid tiers**: Real-time data, higher rate limits
- **WebSocket support**: Some providers offer WebSocket feeds directly
- **Fallback strategy**: Use REST polling if WebSocket unavailable

### 4. Data Caching Strategy

**Recommendations**:
- Cache historical chart data by ticker + timeframe
- Cache duration: 1-5 minutes for active stocks
- Invalidate cache on new price updates
- Use Redis or similar for distributed caching

---

## Frontend Requirements

### 1. WebSocket Client Service

**File**: `src/services/websocket/priceWebSocket.ts`

**Responsibilities**:
- Manage WebSocket connection lifecycle
- Handle subscription/unsubscription
- Implement reconnection logic with exponential backoff
- Parse and validate incoming messages
- Emit events for price updates

**Interface**:
```typescript
class PriceWebSocketClient {
  connect(): void;
  disconnect(): void;
  subscribe(tickers: string[]): void;
  unsubscribe(tickers: string[]): void;
  onPriceUpdate(callback: (update: RealTimePriceUpdate) => void): void;
  onConnectionChange(callback: (connected: boolean) => void): void;
  isConnected(): boolean;
}
```

### 2. StockDashboard Component Updates

**File**: `src/pages/StockDashboard.tsx`

**Required Changes**:

1. **Add Timeframe State**:
```typescript
const [selectedTimeframe, setSelectedTimeframe] = useState<TimeframeOption>('1D');
```

2. **Add WebSocket Integration**:
```typescript
useEffect(() => {
  const wsClient = priceWebSocketClient;
  
  wsClient.subscribe([symbol]);
  wsClient.onPriceUpdate((update) => {
    if (update.ticker === symbol) {
      setStockData(prev => prev ? {
        ...prev,
        price: update.price,
        change: update.change,
        changePercent: update.changePercent,
        stats: {
          ...prev.stats,
          volume: update.volume ?? prev.stats.volume
        }
      } : null);
    }
  });
  
  return () => {
    wsClient.unsubscribe([symbol]);
  };
}, [symbol]);
```

3. **Add Timeframe Selector UI**:
```typescript
const timeframes: TimeframeOption[] = ['1H', '1D', '1W', '1M', '3M', '6M', '1Y', 'YTD', 'ALL'];

<div className="flex gap-2">
  {timeframes.map((tf) => (
    <button
      key={tf}
      onClick={() => setSelectedTimeframe(tf)}
      className={`px-3 py-1 rounded-full text-xs font-bold ${
        selectedTimeframe === tf
          ? 'bg-indigo-600 text-white'
          : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
      }`}
    >
      {tf}
    </button>
  ))}
</div>
```

4. **Filter Chart Data by Timeframe**:
```typescript
const filteredChartData = useMemo(() => {
  if (!stockData?.chartData) return [];
  return filterDataByTimeframe(stockData.chartData, selectedTimeframe);
}, [stockData, selectedTimeframe]);

const series = useMemo(() => {
  return convertChartDataToPricePoints(filteredChartData);
}, [filteredChartData]);
```

5. **Fetch Data with Timeframe Parameter**:
```typescript
useEffect(() => {
  const fetchStockData = async () => {
    setIsLoading(true);
    try {
      const data = await fetchWithFallback(
        () => getStockByTicker(symbol, selectedTimeframe), // Add timeframe param
        mockCompanyDetails[symbol] || mockCompanyDetails['TSLA'],
        `GET /api/stocks/${symbol}?timeframe=${selectedTimeframe}`
      );
      setStockData(data);
    } catch (error) {
      console.error('Failed to fetch stock data:', error);
      setStockData(mockCompanyDetails[symbol] || mockCompanyDetails['TSLA']);
    } finally {
      setIsLoading(false);
    }
  };
  
  if (symbol) {
    fetchStockData();
  }
}, [symbol, selectedTimeframe]); // Add selectedTimeframe dependency
```

6. **Enhance Chart Display**:
- Increase chart height from 80px to 300-400px
- Add chart controls (zoom, pan)
- Add price tooltip on hover
- Show volume bars (optional)

### 3. Update API Service

**File**: `src/services/api/index.ts`

**Add Timeframe Parameter**:
```typescript
export async function getStockByTicker(
  ticker: string, 
  timeframe?: TimeframeOption
): Promise<CompanyDetail> {
  const params = timeframe ? { timeframe } : {};
  const response = await apiClient.get(`/api/stocks/${ticker}`, { params });
  const validated = parseResponse(CompanyDetailSchema, response.data);
  return validated;
}
```

### 4. Update Chart Data Utils

**File**: `src/utils/chartDataUtils.ts`

**Add Hourly Support**:
```typescript
export function filterDataByTimeframe(data: ChartDataPoint[], timeframe: TimeframeOption): ChartDataPoint[] {
  const now = Date.now();
  const dayMs = 24 * 60 * 60 * 1000;
  const hourMs = 60 * 60 * 1000;

  let startDate: number;

  switch (timeframe) {
    case '1H':
      startDate = now - hourMs;
      break;
    case '1D':
      startDate = now - dayMs;
      break;
    // ... existing cases
  }

  return data.filter(d => d.timestamp >= startDate);
}
```

### 5. Connection Status Indicator

**Add to StockHeader**:
```typescript
const [isConnected, setIsConnected] = useState(false);

useEffect(() => {
  const wsClient = priceWebSocketClient;
  wsClient.onConnectionChange(setIsConnected);
}, []);

// In JSX:
<div className="flex items-center gap-2">
  <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
  <span className="text-xs text-slate-400">
    {isConnected ? 'Live' : 'Disconnected'}
  </span>
</div>
```

---

## Implementation Phases

### Phase 1: Timeframe Selection (No WebSocket)
**Priority**: High
**Estimated Time**: 2-3 days

1. ✅ Add timeframe selector UI to StockDashboard
2. ✅ Update `getStockByTicker` to accept timeframe parameter
3. ✅ Backend: Add timeframe query parameter to `/api/stocks/{ticker}`
4. ✅ Filter chart data by timeframe on frontend
5. ✅ Test with different timeframes

### Phase 2: WebSocket Infrastructure
**Priority**: High
**Estimated Time**: 3-5 days

1. ✅ Create WebSocket client service
2. ✅ Backend: Implement WebSocket endpoint
3. ✅ Backend: Integrate with price data provider
4. ✅ Add connection status indicator
5. ✅ Implement reconnection logic
6. ✅ Test connection stability

### Phase 3: Real-Time Price Updates
**Priority**: Medium
**Estimated Time**: 2-3 days

1. ✅ Integrate WebSocket into StockDashboard
2. ✅ Update price display with real-time data
3. ✅ Add visual indicators for price changes
4. ✅ Update chart with latest price point
5. ✅ Handle edge cases (market closed, no data, etc.)

### Phase 4: Enhanced Chart Features
**Priority**: Low
**Estimated Time**: 2-3 days

1. ✅ Increase chart size and interactivity
2. ✅ Add zoom/pan controls
3. ✅ Add price tooltips
4. ✅ Add volume overlay
5. ✅ Improve chart performance

---

## Testing Requirements

### Unit Tests
- WebSocket client connection logic
- Timeframe filtering function
- Price update message parsing
- Reconnection logic

### Integration Tests
- WebSocket subscription/unsubscription flow
- REST API with timeframe parameter
- Chart data filtering accuracy
- Real-time price update flow

### E2E Tests
- User selects timeframe, chart updates
- WebSocket connects, price updates in real-time
- Connection drops, automatic reconnection
- Multiple tickers, multiple subscriptions

---

## Performance Considerations

### WebSocket
- **Connection pooling**: Reuse single connection for multiple tickers
- **Message batching**: Batch multiple price updates if needed
- **Throttling**: Limit update frequency to prevent UI lag (e.g., max 1 update per second per ticker)

### Chart Rendering
- **Data point limits**: Limit chart data points (e.g., max 1000 points)
- **Virtualization**: Only render visible chart range
- **Debouncing**: Debounce timeframe changes to prevent excessive API calls

### API Caching
- Cache historical data by ticker + timeframe
- Cache duration: 1-5 minutes
- Invalidate on new price updates

---

## Security Considerations

1. **WebSocket Authentication**: Implement authentication (JWT token in query string or header)
2. **Rate Limiting**: Limit subscription requests per user/IP
3. **Input Validation**: Validate ticker symbols to prevent injection attacks
4. **CORS**: Configure CORS properly for WebSocket connections
5. **Data Sanitization**: Sanitize all incoming WebSocket messages

---

## Future Enhancements

1. **Multiple Stocks**: Support viewing multiple stocks on one dashboard
2. **Price Alerts**: Set price alerts, notify user when threshold reached
3. **Historical Comparison**: Compare current price to historical averages
4. **Technical Indicators**: Add moving averages, RSI, MACD overlays
5. **Candlestick Charts**: Switch between line and candlestick chart types
6. **Export Data**: Export chart data to CSV/JSON
7. **Mobile Optimization**: Optimize for mobile devices

---

## Dependencies

### Frontend
- `lightweight-charts` (already installed) - For chart rendering
- WebSocket API (native browser API)

### Backend
- WebSocket library (FastAPI: `websockets` or `python-socketio`)
- Market data provider SDK (e.g., `yfinance`, `alpha_vantage`, `polygon-api-client`)
- Redis (optional, for caching)

---

## References

- [WebSocket API - MDN](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)
- [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)
- [Lightweight Charts Documentation](https://tradingview.github.io/lightweight-charts/)
- Existing codebase:
  - `src/utils/chartDataUtils.ts` - Chart data filtering
  - `src/pages/Landing.tsx` - Timeframe selector UI pattern
  - `src/components/charts/MultiStockChart/` - Chart implementation examples

---

## Questions & Notes

- **Hourly data availability**: Confirm if backend can provide intraday/hourly data
- **Market data provider**: Decide on provider (free vs paid tier)
- **Update frequency**: Determine optimal update frequency (every second? every 5 seconds?)
- **Offline support**: Consider caching last known price for offline viewing
- **International markets**: Consider timezone handling for different markets

