# FinMind API Usage for Stock Price Tracking

This document tracks all FinMind API endpoints and datasets used in the TinBoker Backend for stock price tracking and related financial data.

## Overview

FinMind provides comprehensive Taiwan stock market data through their API. This document catalogs the specific APIs we use for:
- Real-time stock prices
- Historical price data
- Market indicators
- Company fundamentals
- Trading statistics

## API Base Configuration

**Base URL**: `https://api.finmindtrade.com/api/v4/data`

**Authentication**: Requires API token (set via environment variable `FINMIND_API_TOKEN`)

**Rate Limits**: Check FinMind platform for account-specific limits

### Python Setup

```python
import requests
import pandas as pd
import os
from datetime import datetime, timedelta

# API Configuration
API_BASE_URL = "https://api.finmindtrade.com/api/v4/data"
API_TOKEN = os.getenv("FINMIND_API_TOKEN")
HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}
```

---

## Stock Price Tracking APIs (TW)

### 1. Real-Time Stock Data

#### `taiwan_stock_tick_snapshot`
**Purpose**: Get real-time stock tick data for current prices

**Use Case**: 
- Live price updates for company detail pages
- Top movers calculation
- Real-time price monitoring

**Parameters**:
- `dataset`: `"taiwan_stock_tick_snapshot"`
- `data_id`: Stock ticker (e.g., "2330" for TSMC)
- `date`: Current date (YYYY-MM-DD format)

**Response Fields**:
- `stock_id`: Stock ticker
- `deal_price`: Current trading price
- `volume`: Trading volume
- `time`: Timestamp

**Update Frequency**: Real-time (every few seconds)

**Python Example**:
```python
def get_realtime_stock_price(stock_id: str, date: str = None):
    """
    Get real-time stock tick data
    
    Args:
        stock_id: Stock ticker (e.g., "2330" for TSMC)
        date: Date in YYYY-MM-DD format (defaults to today)
    """
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    
    parameters = {
        "dataset": "taiwan_stock_tick_snapshot",
        "data_id": stock_id,
        "date": date,
    }
    
    response = requests.get(API_BASE_URL, headers=HEADERS, params=parameters)
    data = response.json()
    
    if data.get("status") == 200:
        return pd.DataFrame(data["data"])
    else:
        raise Exception(f"API Error: {data.get('msg')}")

# Usage
df = get_realtime_stock_price("2330")  # TSMC
print(df[['stock_id', 'deal_price', 'volume', 'time']])
```

---

### 2. Historical Price Data

#### `TaiwanStockPrice`
**Purpose**: Daily stock price data (OHLCV)

**Use Case**:
- Chart data for company detail pages (30-day, 1-year views)
- Historical price analysis
- Price change calculations

**Parameters**:
- `dataset`: `"TaiwanStockPrice"`
- `data_id`: Stock ticker
- `start_date`: Start date (YYYY-MM-DD)
- `end_date`: End date (YYYY-MM-DD)

**Response Fields**:
- `date`: Trading date
- `stock_id`: Stock ticker
- `Trading_Volume`: Trading volume
- `Trading_money`: Trading value
- `open`: Opening price
- `max`: Highest price
- `min`: Lowest price
- `close`: Closing price
- `spread`: Price spread
- `Trading_turnover`: Number of transactions

**Update Frequency**: Daily (after market close)

**Python Example**:
```python
def get_stock_price_history(stock_id: str, start_date: str, end_date: str = None):
    """
    Get daily stock price data (OHLCV)
    
    Args:
        stock_id: Stock ticker (e.g., "2330")
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format (defaults to today)
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    parameters = {
        "dataset": "TaiwanStockPrice",
        "data_id": stock_id,
        "start_date": start_date,
        "end_date": end_date,
    }
    
    response = requests.get(API_BASE_URL, headers=HEADERS, params=parameters)
    data = response.json()
    
    if data.get("status") == 200:
        df = pd.DataFrame(data["data"])
        # Convert date column to datetime
        df['date'] = pd.to_datetime(df['date'])
        return df
    else:
        raise Exception(f"API Error: {data.get('msg')}")

# Usage - Get last 30 days of data
end_date = datetime.now().strftime("%Y-%m-%d")
start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
df = get_stock_price_history("2330", start_date, end_date)
print(df[['date', 'close', 'open', 'max', 'min', 'Trading_Volume']])
```

---

#### `TaiwanStockPriceAdj`
**Purpose**: Adjusted stock prices (accounting for dividends, splits)

**Use Case**:
- Accurate historical price charts
- Long-term trend analysis
- Performance calculations

**Parameters**:
- `dataset`: `"TaiwanStockPriceAdj"`
- `data_id`: Stock ticker
- `start_date`: Start date
- `end_date`: End date

**Response Fields**: Same as `TaiwanStockPrice` but with adjusted prices

**Update Frequency**: Daily

**Python Example**:
```python
def get_adjusted_stock_price(stock_id: str, start_date: str, end_date: str = None):
    """
    Get adjusted stock prices (accounting for dividends, splits)
    
    Args:
        stock_id: Stock ticker
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format (defaults to today)
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    parameters = {
        "dataset": "TaiwanStockPriceAdj",
        "data_id": stock_id,
        "start_date": start_date,
        "end_date": end_date,
    }
    
    response = requests.get(API_BASE_URL, headers=HEADERS, params=parameters)
    data = response.json()
    
    if data.get("status") == 200:
        return pd.DataFrame(data["data"])
    else:
        raise Exception(f"API Error: {data.get('msg')}")

# Usage
df = get_adjusted_stock_price("2330", "2024-01-01", "2024-11-07")
```

---

#### `TaiwanStockKBar`
**Purpose**: K-line (candlestick) data for various timeframes

**Use Case**:
- Technical analysis charts
- Multiple timeframe views (1min, 5min, 15min, 30min, 60min, daily)

**Parameters**:
- `dataset`: `"TaiwanStockKBar"`
- `data_id`: Stock ticker
- `start_date`: Start date
- `end_date`: End date
- `freq`: Timeframe ("1min", "5min", "15min", "30min", "60min", "D")

**Response Fields**:
- `date`: Timestamp
- `stock_id`: Stock ticker
- `open`: Opening price
- `high`: Highest price
- `low`: Lowest price
- `close`: Closing price
- `volume`: Trading volume

**Update Frequency**: Real-time for intraday, daily for daily bars

**Python Example**:
```python
def get_kbar_data(stock_id: str, start_date: str, end_date: str, freq: str = "D"):
    """
    Get K-line (candlestick) data
    
    Args:
        stock_id: Stock ticker
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        freq: Timeframe - "1min", "5min", "15min", "30min", "60min", "D"
    """
    parameters = {
        "dataset": "TaiwanStockKBar",
        "data_id": stock_id,
        "start_date": start_date,
        "end_date": end_date,
        "freq": freq,
    }
    
    response = requests.get(API_BASE_URL, headers=HEADERS, params=parameters)
    data = response.json()
    
    if data.get("status") == 200:
        df = pd.DataFrame(data["data"])
        df['date'] = pd.to_datetime(df['date'])
        return df
    else:
        raise Exception(f"API Error: {data.get('msg')}")

# Usage - Daily K-line
df = get_kbar_data("2330", "2024-01-01", "2024-11-07", freq="D")

# Usage - 5-minute K-line (for intraday analysis)
df = get_kbar_data("2330", "2024-11-07", "2024-11-07", freq="5min")
```

---

### 3. Market Indicators & Statistics

#### `TaiwanVariousIndicators5Seconds`
**Purpose**: Market-wide indicators updated every 5 seconds

**Use Case**:
- Market index tracking (TAIEX)
- Market sentiment indicators
- Overall market performance

**Parameters**:
- `dataset`: `"TaiwanVariousIndicators5Seconds"`
- `data_id`: Indicator ID (e.g., "TAIEX" for Taiwan Stock Exchange Index)
- `start_date`: Start date
- `end_date`: End date

**Response Fields**:
- `date`: Timestamp
- `index_id`: Indicator identifier
- `value`: Indicator value

**Update Frequency**: Every 5 seconds

**Python Example**:
```python
def get_market_indicators(indicator_id: str = "TAIEX", start_date: str = None, end_date: str = None):
    """
    Get market-wide indicators (e.g., TAIEX index)
    
    Args:
        indicator_id: Indicator ID (default: "TAIEX")
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
    """
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    parameters = {
        "dataset": "TaiwanVariousIndicators5Seconds",
        "data_id": indicator_id,
        "start_date": start_date,
        "end_date": end_date,
    }
    
    response = requests.get(API_BASE_URL, headers=HEADERS, params=parameters)
    data = response.json()
    
    if data.get("status") == 200:
        return pd.DataFrame(data["data"])
    else:
        raise Exception(f"API Error: {data.get('msg')}")

# Usage
df = get_market_indicators("TAIEX")
print(df.tail())  # Show latest values
```

---

#### `TaiwanStockStatisticsOfOrderBookAndTrade`
**Purpose**: Order book and trade statistics every 5 seconds

**Use Case**:
- Market depth analysis
- Trading activity monitoring
- Order flow analysis

**Parameters**:
- `dataset`: `"TaiwanStockStatisticsOfOrderBookAndTrade"`
- `data_id`: Stock ticker
- `start_date`: Start date
- `end_date`: End date

**Response Fields**:
- `date`: Timestamp
- `stock_id`: Stock ticker
- `best_bid_price`: Best bid price
- `best_ask_price`: Best ask price
- `total_volume`: Total volume
- `total_amount`: Total amount

**Update Frequency**: Every 5 seconds

**Python Example**:
```python
def get_orderbook_statistics(stock_id: str, start_date: str, end_date: str = None):
    """
    Get order book and trade statistics every 5 seconds
    
    Args:
        stock_id: Stock ticker
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    parameters = {
        "dataset": "TaiwanStockStatisticsOfOrderBookAndTrade",
        "data_id": stock_id,
        "start_date": start_date,
        "end_date": end_date,
    }
    
    response = requests.get(API_BASE_URL, headers=HEADERS, params=parameters)
    data = response.json()
    
    if data.get("status") == 200:
        return pd.DataFrame(data["data"])
    else:
        raise Exception(f"API Error: {data.get('msg')}")

# Usage
df = get_orderbook_statistics("2330", "2024-11-07")
```

---

### 4. Company Information

## Stock Price Tracking APIs (US) 


#### `TaiwanStockInfo`
**Purpose**: Basic stock information and metadata

**Use Case**:
- Company list generation
- Stock metadata (name, industry, listing date)
- Stock classification

**Parameters**:
- `dataset`: `"TaiwanStockInfo"`

**Response Fields**:
- `stock_id`: Stock ticker
- `stock_name`: Company name
- `industry_category`: Industry classification
- `date`: Listing date
- `type`: Stock type

**Update Frequency**: As needed (relatively static)

**Python Example**:
```python
def get_stock_info():
    """
    Get basic stock information for all Taiwan stocks
    """
    parameters = {
        "dataset": "TaiwanStockInfo",
    }
    
    response = requests.get(API_BASE_URL, headers=HEADERS, params=parameters)
    data = response.json()
    
    if data.get("status") == 200:
        return pd.DataFrame(data["data"])
    else:
        raise Exception(f"API Error: {data.get('msg')}")

# Usage
df = get_stock_info()
print(df[['stock_id', 'stock_name', 'industry_category']].head())

# Filter by industry
tech_stocks = df[df['industry_category'].str.contains('半導體', na=False)]
```

---

#### `TaiwanStockPER`
**Purpose**: Price-to-Earnings (P/E) and Price-to-Book (P/B) ratios

**Use Case**:
- Company valuation metrics
- Fundamental analysis
- Company detail pages

**Parameters**:
- `dataset`: `"TaiwanStockPER"`
- `data_id`: Stock ticker
- `start_date`: Start date
- `end_date`: End date

**Response Fields**:
- `date`: Date
- `stock_id`: Stock ticker
- `PER`: Price-to-Earnings ratio
- `PBR`: Price-to-Book ratio

**Update Frequency**: Daily

**Python Example**:
```python
def get_stock_per_pbr(stock_id: str, start_date: str, end_date: str = None):
    """
    Get P/E and P/B ratios for a stock
    
    Args:
        stock_id: Stock ticker
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    parameters = {
        "dataset": "TaiwanStockPER",
        "data_id": stock_id,
        "start_date": start_date,
        "end_date": end_date,
    }
    
    response = requests.get(API_BASE_URL, headers=HEADERS, params=parameters)
    data = response.json()
    
    if data.get("status") == 200:
        df = pd.DataFrame(data["data"])
        df['date'] = pd.to_datetime(df['date'])
        return df
    else:
        raise Exception(f"API Error: {data.get('msg')}")

# Usage - Get latest P/E and P/B
df = get_stock_per_pbr("2330", "2024-01-01")
latest = df.iloc[-1]  # Get most recent values
print(f"P/E Ratio: {latest['PER']}, P/B Ratio: {latest['PBR']}")
```

---

### 5. Trading Statistics

#### `TaiwanStockDayTrading`
**Purpose**: Day trading statistics and volume

**Use Case**:
- Day trading activity tracking
- Trading volume analysis
- Market activity indicators

**Parameters**:
- `dataset`: `"TaiwanStockDayTrading"`
- `data_id`: Stock ticker (optional, omit for all stocks)
- `start_date`: Start date
- `end_date`: End date

**Response Fields**:
- `date`: Trading date
- `stock_id`: Stock ticker
- `BuyAfterSale`: Day trading buy volume
- `VolumeAfterSale`: Day trading sell volume
- `DayTradeVolume`: Total day trading volume
- `DayTradeMoney`: Total day trading value

**Update Frequency**: Daily

**Python Example**:
```python
def get_day_trading_data(stock_id: str = None, start_date: str = None, end_date: str = None):
    """
    Get day trading statistics
    
    Args:
        stock_id: Stock ticker (optional, omit for all stocks)
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
    """
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")
    
    parameters = {
        "dataset": "TaiwanStockDayTrading",
        "start_date": start_date,
        "end_date": end_date,
    }
    
    if stock_id:
        parameters["data_id"] = stock_id
    
    response = requests.get(API_BASE_URL, headers=HEADERS, params=parameters)
    data = response.json()
    
    if data.get("status") == 200:
        return pd.DataFrame(data["data"])
    else:
        raise Exception(f"API Error: {data.get('msg')}")

# Usage - Get day trading data for specific stock
df = get_day_trading_data("2330", "2024-11-01", "2024-11-07")

# Usage - Get all stocks' day trading data
all_df = get_day_trading_data(start_date="2024-11-07", end_date="2024-11-07")
```

---

## Complete Python Example - Company Detail Data

Here's a complete example that combines multiple APIs to get comprehensive company data:

```python
def get_company_detail_data(stock_id: str):
    """
    Get comprehensive company data including:
    - Current price (real-time)
    - Historical prices (30 days)
    - P/E and P/B ratios
    - Basic company info
    """
    today = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    
    results = {}
    
    # 1. Get real-time price
    try:
        realtime_params = {
            "dataset": "taiwan_stock_tick_snapshot",
            "data_id": stock_id,
            "date": today,
        }
        resp = requests.get(API_BASE_URL, headers=HEADERS, params=realtime_params)
        realtime_data = resp.json()
        if realtime_data.get("status") == 200 and realtime_data.get("data"):
            latest = realtime_data["data"][-1]
            results["current_price"] = latest.get("deal_price")
            results["current_volume"] = latest.get("volume")
    except Exception as e:
        print(f"Error fetching real-time data: {e}")
    
    # 2. Get historical prices for chart
    try:
        price_params = {
            "dataset": "TaiwanStockPrice",
            "data_id": stock_id,
            "start_date": start_date,
            "end_date": today,
        }
        resp = requests.get(API_BASE_URL, headers=HEADERS, params=price_params)
        price_data = resp.json()
        if price_data.get("status") == 200:
            df = pd.DataFrame(price_data["data"])
            df['date'] = pd.to_datetime(df['date'])
            results["chart_data"] = df[['date', 'close', 'open', 'max', 'min', 'Trading_Volume']].to_dict('records')
            
            # Calculate price change
            if len(df) > 1:
                prev_close = df.iloc[-2]['close']
                current_close = df.iloc[-1]['close']
                results["change"] = current_close - prev_close
                results["change_percent"] = (results["change"] / prev_close) * 100
    except Exception as e:
        print(f"Error fetching price history: {e}")
    
    # 3. Get P/E and P/B ratios
    try:
        per_params = {
            "dataset": "TaiwanStockPER",
            "data_id": stock_id,
            "start_date": start_date,
            "end_date": today,
        }
        resp = requests.get(API_BASE_URL, headers=HEADERS, params=per_params)
        per_data = resp.json()
        if per_data.get("status") == 200 and per_data.get("data"):
            latest_per = per_data["data"][-1]
            results["pe_ratio"] = latest_per.get("PER")
            results["pb_ratio"] = latest_per.get("PBR")
    except Exception as e:
        print(f"Error fetching P/E data: {e}")
    
    # 4. Get company info
    try:
        info_params = {"dataset": "TaiwanStockInfo"}
        resp = requests.get(API_BASE_URL, headers=HEADERS, params=info_params)
        info_data = resp.json()
        if info_data.get("status") == 200:
            df = pd.DataFrame(info_data["data"])
            company_info = df[df['stock_id'] == stock_id].iloc[0]
            results["company_name"] = company_info.get("stock_name")
            results["industry"] = company_info.get("industry_category")
    except Exception as e:
        print(f"Error fetching company info: {e}")
    
    return results

# Usage
company_data = get_company_detail_data("2330")  # TSMC
print(company_data)
```

## Implementation Notes

### Data Caching Strategy

1. **Real-time Data**: Cache for 5-10 seconds
   - `taiwan_stock_tick_snapshot`
   - `TaiwanVariousIndicators5Seconds`
   - `TaiwanStockStatisticsOfOrderBookAndTrade`

2. **Daily Data**: Cache until next trading day
   - `TaiwanStockPrice`
   - `TaiwanStockPriceAdj`
   - `TaiwanStockPER`
   - `TaiwanStockDayTrading`

3. **Static Data**: Cache for extended periods
   - `TaiwanStockInfo` (update weekly or on-demand)

### Error Handling

- **Rate Limiting**: Implement exponential backoff for 429 responses
- **Missing Data**: Handle cases where stock data is unavailable
- **Market Hours**: Consider market hours (9:00-13:30 Taiwan time) for real-time data
- **Holidays**: Account for Taiwan market holidays

### Data Transformation

When integrating with our API contract:

1. **Price Data** → `CompanyDetail.chartData`
   - Convert FinMind date format to timestamp
   - Map `close` to `price`
   - Format date as `M/D/YYYY`

2. **Real-time Data** → `CompanyDetail.price`
   - Use `deal_price` from `taiwan_stock_tick_snapshot`
   - Calculate `change` and `changePercent` from previous close

3. **Market Cap** → `CompanyDetail.marketCap`
   - Calculate from `close` price × shares outstanding
   - Or use `TaiwanStockMarketValue` dataset

4. **Top Movers** → `TopMoversResponse`
   - Query multiple stocks' real-time data
   - Sort by `changePercent`
   - Return top 5-10 movers

---

## API Usage Tracking

### Endpoints Used Per Feature

| Feature | Primary API | Secondary API | Update Frequency |
|---------|------------|---------------|------------------|
| Company Detail - Current Price | `taiwan_stock_tick_snapshot` | `TaiwanStockPrice` | Real-time / Daily |
| Company Detail - Chart Data | `TaiwanStockPrice` | `TaiwanStockPriceAdj` | Daily |
| Company Detail - P/E Ratio | `TaiwanStockPER` | - | Daily |
| Top Movers | `taiwan_stock_tick_snapshot` | `TaiwanStockPrice` | Real-time |
| Company List | `TaiwanStockInfo` | - | Weekly |
| Market Indicators | `TaiwanVariousIndicators5Seconds` | - | Every 5 seconds |

### Estimated API Calls

**Per User Request**:
- Company Detail: 2-3 API calls (price + chart + PER)
- Top Movers: 10-20 API calls (one per stock)
- Company List: 1 API call (cached)

**Daily Usage** (assuming 1000 users):
- Real-time price queries: ~10,000 calls/day
- Chart data: ~5,000 calls/day
- Top movers: ~1,000 calls/day
- **Total**: ~16,000 API calls/day

**Note**: Actual usage depends on caching strategy and user behavior.

---

## Environment Variables

```bash
# Required
FINMIND_API_TOKEN=your_api_token_here

# Optional
FINMIND_API_BASE_URL=https://api.finmindtrade.com/api/v4/data
FINMIND_CACHE_TTL=300  # Cache TTL in seconds
FINMIND_RATE_LIMIT_DELAY=1  # Delay between requests in seconds
```

---

## References

- [FinMind Documentation](https://finmind.github.io/tutor/TaiwanMarket/DataList/)
- [FinMind API Documentation](https://finmind.github.io/tutor/)
- [FinMind GitHub](https://github.com/FinMind/FinMind)

---

## Changelog

| Date | Change | Author |
|------|--------|--------|
| 2024-11-07 | Initial documentation | Backend Team |

