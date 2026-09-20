# Stock Router Data Flow Documentation

This document explains how data is prepared for each endpoint in `src/routers/stock.py`.

## Overview

All stock data comes from **Massive API** (with mock data fallback). The database is only used for graph/news relationships, not stock data.

## Data Flow Architecture

```
Router Endpoint
    ↓
StockService (src/services/stock.py)
    ↓
DataCollectionService (src/services/data_collection_service.py)
    ↓
MassiveAPIService (src/services/massive_service.py)
    ↓
Massive API / Mock Data
```

## Endpoint-by-Endpoint Data Preparation

### 1. `GET /api/stocks/{ticker}` - Get Stock by Ticker

**Router Handler**: `get_stock_by_ticker(ticker, timeframe)`
- **Service Method**: `stock_service.get_stock_info_async(ticker, timeframe)`
- **Query Params**: 
  - `timeframe`: Optional (1H, 1D, 1W, 1M, 3M, 6M, 1Y, YTD, ALL)

**Data Preparation Flow**:

1. **Cache Check** (Redis):
   - Cache key: `stock:{ticker}:info:{timeframe}:{granularity}`
   - Granularity: `'minute'` for 1H/1D, `'daily'` for others
   - If cached, deserialize and return `CompanyDetail` object

2. **Fetch from API**:
   - Calls `data_collection_service.collect_stock_data(ticker, timeframe=timeframe)`
   - This triggers:
     - `massive_service.get_ticker_details(ticker)` - Basic info
     - `massive_service.get_ticker_snapshot(ticker)` - Current price
     - **Historical data** (granularity based on timeframe):
       - `1H` or `1D`: Fetches **minute-level aggregates** via `_fetch_minute_aggregates()`
       - Others: Fetches **daily aggregates** via `_fetch_daily_aggregates()`
     - `massive_service.list_financials_income_statements(ticker)` - Revenue
     - `massive_service.list_financials_ratios(ticker)` - P/E, dividend yield

3. **Data Transformation**:
   - Converts `Stock` object to `CompanyDetail` via `_convert_stock_to_company_detail()`
   - Creates `ChartDataPoint` objects from `stock_price_history.day`:
     ```python
     ChartDataPoint(
         timestamp=record.timestamp or calculated_from_date,
         price=record.close,
         date=record.date,
         open=record.open,
         high=record.max,
         low=record.min,
         close=record.close,
         volume=record.Trading_Volume
     )
     ```

4. **Timeframe Filtering** (if provided and not 1H/1D):
   - Uses `filter_chart_data_by_timeframe()` from `src/utils/timeframe.py`
   - Filters `chartData` by timestamp based on timeframe:
     - `1W`: Last 7 days
     - `1M`: Last 30 days
     - `3M`: Last 90 days
     - `6M`: Last 180 days
     - `1Y`: Last 365 days
     - `YTD`: From January 1st
     - `ALL`: No filtering

5. **Cache Storage**:
   - Stores `CompanyDetail` object in Redis as JSON
   - TTL: `CACHE_TTL["stock_info"]`

**Response**: `CompanyDetail` - Full stock information with chart data

---

### 2. `GET /api/stocks/{ticker}/basic` - Get Basic Stock Info

**Router Handler**: `get_stock_basic_info(ticker)`
- **Service Method**: `stock_service.get_stock_basic_info_async(ticker)`

**Data Preparation Flow**:

1. **Cache Check** (Redis):
   - Cache key: `stock:{ticker}:basic`
   - If cached, return dict immediately

2. **Fetch from API**:
   - Calls `data_collection_service.collect_stock_data(ticker)`
   - Same data collection as full stock info, but...

3. **Data Transformation**:
   - Extracts only basic fields (NO chart data):
   ```python
   {
       "ticker": stock_data.stock_id,
       "name": stock_data.metadata.stock_name,
       "price": stock_data.price or 0.0,
       "change": stock_data.change or 0.0,
       "changePercent": stock_data.changePercent or 0.0,
       "marketCap": stock_data.marketCap or 0,
       "revenue": stock_data.revenue or 0,
       "pe": stock_data.pe or 0.0,
       "dividendYield": stock_data.dividendYield or 0.0,
       "about": stock_data.about or "",
       "stats": {
           "volume": stock_data.stats.volume,
           "beta": stock_data.stats.beta,
           "volatility": stock_data.stats.volatility
       }
   }
   ```

4. **Cache Storage**:
   - Stores dict in Redis
   - TTL: `CACHE_TTL["stock_basic"]`

**Response**: `Dict[str, Any]` - Basic stock info without chart data

---

### 3. `GET /api/stocks/{ticker}/history` - Get Stock Price History

**Router Handler**: `get_stock_history(ticker, timeframe)`
- **Service Method**: `stock_service.get_stock_info_async(ticker, timeframe)`
- **Query Params**: Same timeframe options as `/api/stocks/{ticker}`

**Data Preparation Flow**:

1. **Fetch Full Stock Info**:
   - Calls `stock_service.get_stock_info_async(ticker, timeframe)`
   - Same flow as endpoint #2 above

2. **Extract History**:
   - Extracts `chartData` from `CompanyDetail` object
   - Converts to lightweight format:
   ```python
   {
       "symbol": ticker.upper(),
       "data": [
           {
               "time": point.date,      # YYYY-MM-DD
               "price": point.close     # Closing price
           }
           for point in chart_data
       ]
   }
   ```

**Response**: `Dict` with `symbol` and `data` array (lightweight format for sparklines)

---

### 4. `WebSocket /api/stocks/{ticker}/ohlcv` - Real-time OHLCV Streaming

**Router Handler**: `websocket_ohlcv(websocket, ticker)`
- **Service**: Uses `WebSocketSubscriber` for Redis pub/sub

**Data Preparation Flow**:

1. **WebSocket Connection**:
   - Accepts WebSocket connection
   - Creates `WebSocketSubscriber` instance

2. **Subscribe to Updates**:
   - Subscribes to Redis channel for ticker updates
   - Channel: Based on ticker symbol

3. **Message Streaming**:
   - Listens for messages from Redis pub/sub
   - Forwards OHLCV updates to WebSocket client
   - Sends ping messages every 30 seconds to keep connection alive

**Note**: Real-time updates come from Redis pub/sub system (not directly from Massive API in this endpoint)

---

## Key Data Structures

### Stock Object (from DataCollectionService)
```python
Stock(
    stock_id: str,
    metadata: StockMetadata,
    stock_price_history: StockPriceHistory,  # Contains .day list
    price: float,
    change: float,
    changePercent: float,
    marketCap: int,
    revenue: int,
    pe: float,
    dividendYield: float,
    about: str,
    stats: CompanyStats
)
```

### CompanyDetail (API Response Model)
```python
CompanyDetail(
    ticker: str,
    name: str,
    price: float,
    change: float,
    changePercent: float,
    marketCap: int,
    revenue: int,
    pe: float,
    dividendYield: float,
    about: str,
    stats: StockStats,
    chartData: List[ChartDataPoint]  # Historical OHLCV data
)
```

### ChartDataPoint
```python
ChartDataPoint(
    timestamp: int,      # Unix timestamp in milliseconds
    price: float,        # Closing price (for backward compatibility)
    date: str,           # ISO date string (YYYY-MM-DD)
    open: float,
    high: float,
    low: float,
    close: float,
    volume: int
)
```

## Caching Strategy

All endpoints use Redis caching with different TTLs:

- **Stock List**: `CACHE_TTL["stock_list"]` - Cached by sort_by and limit
- **Stock Info**: `CACHE_TTL["stock_info"]` - Cached by ticker, timeframe, and granularity
- **Stock Basic**: `CACHE_TTL["stock_basic"]` - Cached by ticker

Cache keys include relevant parameters to ensure correct data is returned.

## Timeframe Handling

### Data Granularity
- **1H / 1D**: Fetches **minute-level aggregates** from Massive API
- **Others**: Fetches **daily aggregates** from Massive API

### Filtering
- For **1H/1D**: Data is fetched with appropriate granularity, no post-filtering needed
- For **others**: Data is fetched as daily aggregates, then filtered by timestamp using `filter_chart_data_by_timeframe()`

## Error Handling

1. **API Failures**: Falls back to mock data via `MockCompanyDataService`
2. **Cache Failures**: Silently continues (doesn't break request)
3. **Missing Data**: Returns `None` or empty lists
4. **Invalid Timeframe**: Returns unfiltered data with warning log

## Performance Optimizations

1. **Ultra-fast mode** for stock list: Uses `list_tickers()` which doesn't make per-ticker API calls
2. **Caching**: All endpoints cache results to reduce API calls
3. **Async operations**: All service methods are async for better concurrency
4. **Selective data fetching**: Basic info endpoint doesn't fetch chart data

