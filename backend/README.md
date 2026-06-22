# TinBoker Backend

The FastAPI platform API for [TinBoker](../README.md) — it serves the web UI with TW/US stock
data, relationship graphs, full-text search, podcast/episode content, auth, and an
admin/config control plane. It reads the content the pipelines derive (Postgres + Firestore)
and exposes it over a single HTTP API.

## Features

- 📊 **Stock data**: TW + US prices, charts, key stats, ticker insights (Massive + FinMind)
- 🕸️ **Graph visualization**: company/sector/concept relationship graphs
- 🔍 **Search & discovery**: full-text search, autocomplete, trending tickers/tags
- 🎙️ **Podcast & content**: episodes, podcasts, comments, news, articles
- 🔄 **Real-time prices**: WebSocket price streaming
- 🔐 **Auth & admin**: Google OAuth → JWT, watchlists, admin/config control plane
- 💾 **Storage**: SQLite (dev) / PostgreSQL (staging + prod), Redis cache
- 🧪 **Tested**: 200+ unit and integration tests (`pytest`)

## Tech Stack

- **Framework**: FastAPI 0.104.1
- **Python**: 3.12+
- **Database**: SQLite (dev) / PostgreSQL (staging + prod) via SQLAlchemy 2
- **Caching**: Redis 7
- **Data Sources**: Massive API (US), FinMind API (TW), Firestore (podcasts) — mock-data fallback
- **Testing**: pytest, httpx
- **Deployment**: Docker on Netcup VPS, via GitHub Actions (see [deploy flow](../docs/workflows/deploy-flow.md))

## Installation

You can use either **pip** (standard) or **uv** (faster, recommended) to manage dependencies.

### Prerequisites

- Python 3.12 or higher
- pip package manager (or uv)
- (Optional) PostgreSQL and Redis for production

### Setup

1. **Clone the repository**

```bash
git clone <repository-url>
cd TinBoker-Backend
```

2. **Create a virtual environment & Install Dependencies**

**Option A: Using pip (Standard)**

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Option B: Using uv (Fast)**

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync dependencies (uses requirements.txt)
uv pip install -r requirements.txt

# OR using pyproject.toml
uv sync
```

4. **Set up environment variables**

Create a `.env` file in the project root:

```env
# API Keys (optional - falls back to mock data if not provided)
MASSIVE_API_KEY=your_massive_api_key_here
FINMIND_API_KEY=your_finmind_api_key_here

# Database (SQLite by default)
DATABASE_PATH=data/tinboker.db
USE_POSTGRES=false

# For production with PostgreSQL
# USE_POSTGRES=true
# DATABASE_URL=postgresql://user:password@host:port/dbname

# Redis (optional)
# REDIS_URL=redis://localhost:6379/0

# Google Cloud Firestore (for Podcast API)
# GCP_CREDENTIALS_PATH=/path/to/credentials.json
# OR
# GCP_CREDENTIALS_JSON={"type": "service_account", ...}
# FIRESTORE_DATABASE_ID=your-database-id  # Optional, defaults to "(default)"

# Server Configuration
HOST=0.0.0.0
PORT=5174
ENVIRONMENT=development

# CORS
CORS_ORIGINS=http://localhost:5173,https://your-frontend-domain.com
```

5. **Initialize the database**

```bash
python -m src.database.migrate
```

## Running the Application

### Prerequisites

Before starting the application, ensure Redis is running for caching functionality:

**Start Redis (Required for caching):**

```bash
# Option 1: Using Docker Compose (Recommended)
docker compose up -d redis

# Option 2: Using helper script
./scripts/start-redis.sh

# Verify Redis is running
docker exec tinboker-redis redis-cli ping
# Should return: PONG
```

**Note:** The application will work without Redis, but caching will be disabled and API responses will be slower.

### Development Mode

The server port is configured in `.env` file (default: `PORT=5174`).

**Option 1: Using Python (Recommended - uses port from .env automatically)**

```bash
# Start Redis first
docker compose up -d redis

# Start the application
python -m src.main
```

**Kill the running process (from another terminal):**

When using `uv run` or if `pkill -f "src.main"` doesn't work, kill by the port the app listens on (see `PORT` in `.env`, default 5174):

```bash
# By port (most reliable – use your PORT from .env, default 5174)
lsof -ti :5174 | xargs kill -9
# Or: fuser -k 5174/tcp

# By process name (force kill with SIGKILL)
pkill -9 -f "src.main"
pkill -9 -f "uv run python"
```

**Option 2: Using uvicorn directly**

```bash
# Start Redis first
docker compose up -d redis

# Start the application
uvicorn src.main:app --reload --host 0.0.0.0 --port 5174
```

Note: When using uvicorn directly, the `--port` flag overrides the `.env` setting. To use the port from `.env`, use Option 1 instead.

### Clearing Redis Cache

**Clear all cache (use with caution):**

```bash
# Using docker exec
docker exec tinboker-redis redis-cli flushall

# Or if Redis is running locally
redis-cli flushall
```

**Clear specific cache keys:**

```bash
# Connect to Redis CLI
docker exec -it tinboker-redis redis-cli

# Delete specific key
DEL podcast:Gooaye 股癌:episode:Gooaye_988e8c33a6e3934f

# Delete keys matching a pattern
KEYS podcast:*
# Then delete them individually or use:
# (Note: KEYS can be slow on large databases)
```

**Using Python scripts:**

```bash
# Clear cache for a specific episode
python3 scripts/clear_episode_cache.py

# Or use the test script to check Firestore data
python3 scripts/test_episode_firestore.py
```

**Redis**

Locally, Redis runs via `docker compose up -d redis` (see [Running](#running-the-application)).
In staging/prod, `REDIS_URL` points at the VPS Redis 7 instance and is loaded from GCP Secret
Manager. Note: the local `.env`'s `REDIS_URL` may point at a *shared remote* Redis — override it
to `redis://localhost:6379/0` before any local cache operation.

### Starting WebSocket Services

**Quick Verification:**

```bash
# Test WebSocket connection (server must be running)
python3 -c "
import asyncio
import json
from websockets import connect

async def test():
    async with connect('ws://localhost:5174/ws/prices') as ws:
        msg = await ws.recv()
        print('✅ WebSocket connected!')
        print('Response:', json.loads(msg))

asyncio.run(test())
"
```

The API will be available at:
- **API**: http://localhost:5174 (or the port specified in `.env`)
- **WebSocket**: ws://localhost:5174/ws/prices
- **Interactive Docs (Swagger)**: http://localhost:5174/docs
- **Alternative Docs (ReDoc)**: http://localhost:5174/redoc
- **Health Check**: http://localhost:5174/health (shows Redis status and cache statistics)

### Production Mode

```bash
# Start Redis
docker compose up -d redis

# Start the application
uvicorn src.main:app --host 0.0.0.0 --port $PORT --workers 4
```

### Redis Management

**Start Redis:**
```bash
docker compose up -d redis
# or
./scripts/start-redis.sh
```

**Stop Redis:**
```bash
docker compose down redis
# or
docker stop tinboker-redis
```

**View Redis logs:**
```bash
docker logs tinboker-redis
```

**Connect to Redis CLI:**
```bash
docker exec -it tinboker-redis redis-cli
```

**Test Redis connection:**
```bash
python scripts/test-redis-connection.py
```

## API Documentation

> **The authoritative, always-current API reference is the auto-generated OpenAPI docs at
> [`/docs`](https://api.tinboker.com/docs)** (Swagger UI) and `/redoc`. The sections below cover
> the core stock/graph/news/podcast endpoints by hand; for everything else (auth, search, tags,
> comments, articles, social, SEO, notifications, ticker-insights, admin/config), use `/docs`.

### Router map

The API is organised into 32 routers under `src/routers/`:

| Group | Routers |
|-------|---------|
| Stocks & markets | `stock`, `company`, `ticker_insights`, `translations`, `websocket_prices`, `websocket` |
| Content | `episodes`, `podcast`, `comments`, `news`, `articles`, `content`, `recommendations` |
| Discovery | `search`, `tags`, `graph`, `visual_graph` |
| Platform | `auth`, `user`, `notifications`, `analytics`, `seo`, `social`, `sources` |
| Admin / config | `admin_system`, `admin_analytics`, `admin_articles`, `admin_pipeline`, `admin_pipeline_trial`, `admin_sources`, `admin_tags`, `admin_translations` |

### Base URL

- **Local**: `http://localhost:5174`
- **Production**: `https://api.tinboker.com`

---

### Stock APIs

#### 1. Get All Stocks

Get a sorted list of all stocks in the database.

```bash
curl -X GET "http://localhost:5174/api/stocks?sort_by=ticker"
```

**Query Parameters:**
- `sort_by` (optional): Sort field - `ticker`, `name`, `price`, `change_percent`, `market_cap` (default: `ticker`)

**Example Response:**

```json
[
  {
    "ticker": "AAPL",
    "name": "Apple Inc.",
    "price": 178.50,
    "change": 2.30,
    "change_percent": 1.31,
    "market_cap": 2800000000000,
    "revenue": 394328000000,
    "pe": 29.5,
    "dividend_yield": 0.52,
    "about": "Apple Inc. designs, manufactures, and markets smartphones...",
    "volume": 52000000,
    "beta": 1.25,
    "volatility": 0.28,
    "updated_at": "2024-01-15T10:30:00"
  }
]
```

---

#### 2. Get Stock by Ticker

Get detailed information about a specific stock including chart data.

```bash
curl -X GET "http://localhost:5174/api/stocks/NVDA"
```

**Query Parameters:**
- `timeframe` (optional): Filter chart data by timeframe. Valid options:
  - `1H` - Last 1 hour (minute-level granularity, ~60-120 data points)
  - `1D` - Last 24 hours (minute-level granularity, ~390-1440 data points)
  - `1W` - Last 7 days (daily granularity)
  - `1M` - Last 30 days (daily granularity)
  - `3M` - Last 90 days (daily granularity)
  - `6M` - Last 180 days (daily granularity)
  - `1Y` - Last 365 days (daily granularity)
  - `YTD` - Year to date (from January 1st, daily granularity)
  - `ALL` - All available data (default if not specified, daily granularity)

**Note:** 
- The `1H` and `1D` timeframes fetch minute-level aggregates for intraday charting, providing high-resolution data similar to professional trading platforms.
- Due to the 15-minute delay on the Starter plan, these timeframes use yesterday's data (last trading day) to ensure availability.
- Other timeframes use daily aggregates.

**Examples:**

```bash
# Get all available data (default)
curl -X GET "http://localhost:5174/api/stocks/NVDA"

# Get last 1 hour with minute-level data
curl -X GET "http://localhost:5174/api/stocks/NVDA?timeframe=1H"

# Get last 24 hours with minute-level data
curl -X GET "http://localhost:5174/api/stocks/NVDA?timeframe=1D"

# Get last week of data (daily granularity)
curl -X GET "http://localhost:5174/api/stocks/NVDA?timeframe=1W"

# Get last 30 days of data
curl -X GET "http://localhost:5174/api/stocks/NVDA?timeframe=1M"

# Get last year of data
curl -X GET "http://localhost:5174/api/stocks/NVDA?timeframe=1Y"

# Get year-to-date data
curl -X GET "http://localhost:5174/api/stocks/NVDA?timeframe=YTD"
```

**Example Response:**

```json
{
  "ticker": "NVDA",
  "name": "NVIDIA Corporation",
  "price": 495.22,
  "change": 12.45,
  "changePercent": 2.58,
  "marketCap": 1220000000000,
  "revenue": 60922000000,
  "pe": 95.3,
  "dividendYield": 0.03,
  "about": "NVIDIA is a leading designer of graphics processing units...",
  "stats": {
    "volume": 52000000,
    "beta": 1.68,
    "volatility": 0.52
  },
  "chartData": [
    {
      "timestamp": 1704067200000,
      "price": 490.50,
      "date": "2024-01-01",
      "open": 488.00,
      "high": 492.00,
      "low": 487.50,
      "close": 490.50,
      "volume": 45000000
    }
  ]
}
```

---

#### 3. Get Stock Basic Info

Get basic stock information without chart data (faster response).

```bash
curl -X GET "http://localhost:5174/api/stocks/MSFT/basic"
```

**Example Response:**

```json
{
  "ticker": "MSFT",
  "name": "Microsoft Corporation",
  "price": 378.91,
  "change": 3.21,
  "changePercent": 0.85,
  "marketCap": 2820000000000,
  "revenue": 211915000000,
  "pe": 35.7,
  "dividendYield": 0.79,
  "about": "Microsoft develops, licenses, and supports software...",
  "stats": {
    "volume": 24000000,
    "beta": 0.92,
    "volatility": 0.28
  }
}
```

---

#### 4. WebSocket - Real-time Price Updates

Connect via WebSocket to receive real-time stock price updates using the `/ws/prices` endpoint.

**Endpoint:** `ws://localhost:5174/ws/prices`

**JavaScript Example:**

```javascript
const ws = new WebSocket('ws://localhost:5174/ws/prices');

ws.onopen = () => {
  // Subscribe to tickers
  ws.send(JSON.stringify({
    type: 'subscribe',
    tickers: ['AAPL', 'TSLA']
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'price_update') {
    console.log('Price update:', data.data);
    // data.data contains: ticker, price, change, changePercent, volume, timestamp, etc.
  }
};
```

**Example Price Update Message:**

```json
{
  "type": "price_update",
  "data": {
    "ticker": "AAPL",
    "price": 175.50,
    "change": 1.25,
    "changePercent": 0.72,
    "volume": 50000000,
    "timestamp": 1701504000000,
    "marketStatus": "open",
    "open": 174.25,
    "high": 176.00,
    "low": 174.00,
    "close": 175.50,
    "previousClose": 174.25
  }
}
```

**Note:** The WebSocket endpoint starts automatically with the server. For real-time updates, start the publisher worker (see "Starting WebSocket Services" section above).

---

### Graph APIs

#### 1. Get All Graphs

Get a sorted list of all graphs.

```bash
curl -X GET "http://localhost:5174/api/graphs?sort_by=concept_id"
```

**Query Parameters:**
- `sort_by` (optional): Sort field - `concept_id`, `created_at`, `updated_at` (default: `concept_id`)

**Example Response:**

```json
[
  {
    "id": "abc123-def456",
    "concept_id": "ai",
    "created_at": "2024-01-15T10:00:00",
    "updated_at": "2024-01-15T10:00:00"
  }
]
```

---

#### 2. Get Graph by ID

Get complete graph data including nodes and edges.

```bash
curl -X GET "http://localhost:5174/api/graphs/abc123-def456"
```

**Example Response:**

```json
{
  "nodes": [
    {
      "id": "NVDA",
      "type": "stock",
      "data": {
        "label": "NVIDIA",
        "ticker": "NVDA",
        "marketCapTier": "large"
      },
      "position": {
        "x": 100.0,
        "y": 200.0
      }
    },
    {
      "id": "MSFT",
      "type": "stock",
      "data": {
        "label": "Microsoft",
        "ticker": "MSFT",
        "marketCapTier": "large"
      },
      "position": {
        "x": 300.0,
        "y": 400.0
      }
    }
  ],
  "edges": [
    {
      "id": "e1",
      "source": "NVDA",
      "target": "MSFT",
      "label": "Partnership",
      "data": {
        "category": "automation"
      }
    }
  ]
}
```

---

#### 3. Create New Graph

Create a new graph with nodes and edges.

```bash
curl -X POST "http://localhost:5174/api/graphs" \
  -H "Content-Type: application/json" \
  -d '{
    "conceptId": "ai",
    "nodes": [
      {
        "id": "NVDA",
        "type": "stock",
        "label": "NVIDIA",
        "ticker": "NVDA",
        "marketCapTier": "large",
        "positionX": 100.0,
        "positionY": 200.0
      },
      {
        "id": "MSFT",
        "type": "stock",
        "label": "Microsoft",
        "ticker": "MSFT",
        "marketCapTier": "large",
        "positionX": 300.0,
        "positionY": 400.0
      }
    ],
    "edges": [
      {
        "id": "e1",
        "source": "NVDA",
        "target": "MSFT",
        "label": "Partnership",
        "category": "automation"
      }
    ]
  }'
```

**Example Response:**

```json
{
  "id": "abc123-def456",
  "message": "Graph created successfully"
}
```

---

#### 4. Update Node Position/Data

Update a node in an existing graph.

```bash
curl -X PUT "http://localhost:5174/api/graphs/abc123-def456/nodes/NVDA" \
  -H "Content-Type: application/json" \
  -d '{
    "positionX": 150.0,
    "positionY": 250.0
  }'
```

**Example Response:**

```json
{
  "message": "Node updated successfully"
}
```

---

#### 5. Update Edge

Update an edge in an existing graph.

```bash
curl -X PUT "http://localhost:5174/api/graphs/abc123-def456/edges/e1" \
  -H "Content-Type: application/json" \
  -d '{
    "label": "Strategic Partnership",
    "category": "collaboration"
  }'
```

**Example Response:**

```json
{
  "message": "Edge updated successfully"
}
```

---

#### 6. Delete Graph

Delete a graph and all its nodes and edges.

```bash
curl -X DELETE "http://localhost:5174/api/graphs/abc123-def456"
```

**Example Response:**

```json
{
  "message": "Graph deleted successfully"
}
```

---

#### 7. Delete Node

Delete a node from a graph (also deletes connected edges).

```bash
curl -X DELETE "http://localhost:5174/api/graphs/abc123-def456/nodes/NVDA"
```

**Example Response:**

```json
{
  "message": "Node deleted successfully"
}
```

---

#### 8. Delete Edge

Delete an edge from a graph.

```bash
curl -X DELETE "http://localhost:5174/api/graphs/abc123-def456/edges/e1"
```

**Example Response:**

```json
{
  "message": "Edge deleted successfully"
}
```

---

### News APIs

#### 1. Get All News

Get a sorted list of all news/events.

```bash
curl -X GET "http://localhost:5174/api/news?sort_by=date"
```

**Query Parameters:**
- `sort_by` (optional): Sort field - `date`, `created_at`, `updated_at`, `title` (default: `date`)

**Example Response:**

```json
[
  {
    "id": "news-123",
    "type": "earnings",
    "date": 1704067200000,
    "title": "NVIDIA Q4 Earnings Beat Expectations",
    "description": "NVIDIA reports record quarterly revenue driven by AI chip demand",
    "content": "Full earnings report content here...",
    "relatedTickers": ["NVDA", "AMD"]
  }
]
```

---

#### 2. Fetch News from Massive API

Fetch news articles from Massive API for a specific ticker and save them to the database.

```bash
curl -X POST "http://localhost:5174/api/news/fetch/NVDA?limit=10"
```

**Path Parameters:**
- `ticker`: Stock ticker symbol (e.g., "NVDA", "AAPL", "MSFT")

**Query Parameters:**
- `limit` (optional): Maximum number of articles to fetch (default: 10)

**Example Response:**

```json
{
  "ticker": "NVDA",
  "count": 5,
  "news_ids": [
    "e18deab177b3585e850f6bd47ccc50d0cbe7852933f28afdb0f421670a7229de",
    "e90f06cbae784c401193dda88fd71749e8c7185c79f4ed51d4677d2784d85542"
  ],
  "message": "Successfully fetched and saved 5 news articles"
}
```

**Notes:**
- News articles are automatically saved to the database
- Duplicate articles (same ID) are skipped
- Articles are tagged with the ticker as a related ticker
- Date is automatically converted from ISO format to Unix timestamp

---

#### 3. Get News by ID

Get detailed information about a specific news item.

```bash
curl -X GET "http://localhost:5174/api/news/news-123"
```

**Example Response:**

```json
{
  "id": "news-123",
  "type": "earnings",
  "date": 1704067200000,
  "title": "NVIDIA Q4 Earnings Beat Expectations",
  "description": "NVIDIA reports record quarterly revenue driven by AI chip demand",
  "content": "NVIDIA Corporation announced today that it has achieved record quarterly revenue of $22.1 billion...",
  "relatedTickers": ["NVDA", "AMD"]
}
```

---

### Podcast APIs

#### 1. Get All Podcasts

Get a sorted list of all podcasts.

```bash
curl -X GET "http://localhost:5174/api/podcast?sort_by=name&order=asc&limit=50&offset=0"
```

**Query Parameters:**
- `sort_by` (optional): Sort field - `name`, `episode_count`, `created_at`, `updated_at` (default: `name`)
- `order` (optional): Sort order - `asc`, `desc` (default: `asc`)
- `limit` (optional): Maximum number of podcasts to return, 1-200 (default: 50)
- `offset` (optional): Pagination offset (default: 0)

**Example Response:**
```json
[
  {
    "id": "股癌",
    "name": "股癌",
    "episode_count": 150,
    "created_at": 1609459200000,
    "updated_at": 1704067200000
  }
]
```

---

#### 2. Get Podcast by Name

Get detailed information about a specific podcast.

**Note:** When using podcast names with Chinese characters or spaces, you must URL-encode the path parameter.

```bash
# Using URL-encoded podcast name (required for Chinese characters)
curl -X GET "http://localhost:5174/api/podcast/%E8%82%A1%E7%99%8C"

# Or use curl with --data-urlencode (for simple cases)
# For podcast names with spaces: "Gooaye 股癌" -> "Gooaye%20%E8%82%A1%E7%99%8C"
curl -X GET "http://localhost:5174/api/podcast/Gooaye%20%E8%82%A1%E7%99%8C"
```

**Path Parameters:**
- `podcast_name`: Podcast name (must be URL-encoded if containing special characters)

**Example Response:**
```json
{
  "id": "股癌",
  "name": "股癌",
  "episode_count": 150,
  "created_at": 1609459200000,
  "updated_at": 1704067200000
}
```

---

#### 3. Get Podcast Episodes

Get all episodes for a specific podcast.

**Note:** The `podcast_name` path parameter must be URL-encoded if it contains Chinese characters or spaces.

```bash
# Using URL-encoded podcast name
curl -X GET "http://localhost:5174/api/podcast/%E8%82%A1%E7%99%8C/episodes?sort_by=created_time&order=desc&limit=50&offset=0"

# Example with podcast name containing space
curl -X GET "http://localhost:5174/api/podcast/Gooaye%20%E8%82%A1%E7%99%8C/episodes?sort_by=created_time&order=desc&limit=50&offset=0"
```

**Path Parameters:**
- `podcast_name`: Podcast name (must be URL-encoded if containing special characters, e.g., "股癌" -> "%E8%82%A1%E7%99%8C")

**Query Parameters:**
- `sort_by` (optional): Sort field - `created_time`, `episode_number`, `episode_title` (default: `created_time`)
- `order` (optional): Sort order - `asc`, `desc` (default: `desc`)
- `limit` (optional): Maximum number of episodes to return, 1-200 (default: 50)
- `offset` (optional): Pagination offset (default: 0)

**Example Response:**
```json
[
  {
    "id": "podcast_episode_123",
    "podcast_name": "股癌",
    "episode_title": "Episode 150: Market Analysis",
    "episode_number": 150,
    "transcript": "Full transcript text...",
    "summary_content": "# Summary\n\nMarket analysis summary...",
    "summary_image": "<svg>...</svg>",
    "related_tickers": ["NVDA", "AAPL", "TSLA"],
    "created_time": 1704067200000,
    "number_click": 1250,
    "num_likes": 89,
    "raw_mp3": "/path/to/episode.mp3"
  }
]
```

---

#### 4. Get Episode by ID

Get detailed information about a specific episode.

**Note:** Both `podcast_name` and `episode_id` path parameters must be URL-encoded if they contain special characters.

```bash
# Using URL-encoded podcast name and episode ID
curl -X GET "http://localhost:5174/api/podcast/%E8%82%A1%E7%99%8C/episodes/podcast_episode_123"

# Example with podcast name containing space
curl -X GET "http://localhost:5174/api/podcast/Gooaye%20%E8%82%A1%E7%99%8C/episodes/Gooaye_b92f18e46367339e"
```

**Path Parameters:**
- `podcast_name`: Podcast name (must be URL-encoded if containing special characters)
- `episode_id`: Episode ID (must be URL-encoded if containing special characters)

**Example Response:**
```json
{
  "id": "podcast_episode_123",
  "podcast_name": "股癌",
  "episode_title": "Episode 150: Market Analysis",
  "episode_number": 150,
  "transcript": "Full transcript text...",
  "summary_content": "# Summary\n\nMarket analysis summary...",
  "summary_image": "<svg>...</svg>",
  "related_tickers": ["NVDA", "AAPL", "TSLA"],
  "created_time": 1704067200000,
  "number_click": 1250,
  "num_likes": 89,
  "raw_mp3": "/path/to/episode.mp3"
}
```

**Notes:**
- Podcast data is stored in Google Cloud Firestore
- Episodes are cached in Redis for improved performance
- Requires `GCP_CREDENTIALS_PATH` or `GCP_CREDENTIALS_JSON` environment variable
- Optional `FIRESTORE_DATABASE_ID` environment variable for custom database
- **Important:** All path parameters containing Chinese characters, spaces, or special characters must be URL-encoded
  - Use Python's `urllib.parse.quote()` or JavaScript's `encodeURIComponent()` to encode podcast names
  - Example: `"Gooaye 股癌"` → `"Gooaye%20%E8%82%A1%E7%99%8C"`

---

### Health Check

Check if the API is running and healthy.

```bash
curl -X GET "http://localhost:5174/health"
```

**Example Response:**

```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00.000Z"
}
```

---

### Root Endpoint

Get API information.

```bash
curl -X GET "http://localhost:5174/"
```

**Example Response:**

```json
{
  "message": "TinBoker Backend API",
  "version": "1.0.0",
  "environment": "development",
  "docs": "/docs"
}
```

---

## Database Schema

### Tables

#### stocks
- `ticker` (PK): Stock ticker symbol
- `name`: Company name
- `price`, `change`, `change_percent`: Current price data
- `market_cap`, `revenue`, `pe`, `dividend_yield`: Financial metrics
- `about`: Company description
- `volume`, `beta`, `volatility`: Trading statistics
- `updated_at`: Last update timestamp

#### stock_history
- `id` (PK): Auto-increment ID
- `ticker` (FK): References stocks
- `timestamp`, `date`: Time information
- `open`, `high`, `low`, `close`, `volume`: OHLCV data

#### graphs
- `id` (PK): Graph UUID
- `concept_id`: Concept/theme identifier
- `created_at`, `updated_at`: Timestamps

#### graph_nodes
- `id` (PK): Auto-increment ID
- `graph_id` (FK): References graphs
- `node_id`: Node identifier within graph
- `node_type`, `label`, `ticker`, `market_cap_tier`: Node data
- `position_x`, `position_y`: Position in visualization

#### graph_edges
- `id` (PK): Auto-increment ID
- `graph_id` (FK): References graphs
- `edge_id`: Edge identifier within graph
- `source_node_id`, `target_node_id`: Connected nodes
- `label`, `category`: Edge data

#### news
- `id` (PK): News UUID
- `type`: Event type (earnings, conference, news, dividend)
- `date`: Event date (Unix timestamp)
- `title`, `description`, `content`: News content
- `created_at`, `updated_at`: Timestamps

#### news_tickers
- `news_id` (FK): References news
- `ticker`: Related stock ticker
- Composite PK: (news_id, ticker)

---

## Testing

### Run All Tests

```bash
pytest tests/ -v
```

### Run Specific Test Categories

```bash
# Unit tests only
pytest tests/unit/ -v

# Integration tests only
pytest tests/integration/ -v

# Specific test file
pytest tests/unit/test_stock_db.py -v

# With coverage
pytest tests/ --cov=src --cov-report=html
```

### Test Results

The project includes:
- **65 passing tests** covering:
  - Database CRUD operations (30 tests)
  - Service layer logic (19 tests)
  - API endpoints (16 tests)
- **Test coverage**: Database, services, and API endpoints
- **Test isolation**: Each test uses a temporary SQLite database

---

## Project Structure

```
TinBoker-Backend/
├── src/
│   ├── database/          # Database layer
│   │   ├── db.py          # Database initialization
│   │   ├── stock_db.py    # Stock CRUD operations
│   │   ├── graph_db.py    # Graph CRUD operations
│   │   ├── news_db.py     # News CRUD operations
│   │   └── migrate.py     # Migration script
│   ├── models/            # Pydantic models
│   │   ├── stock.py       # Stock models
│   │   ├── graph.py       # Graph models
│   │   ├── news.py        # News models
│   │   └── schemas.py     # Additional schemas
│   ├── routers/           # API endpoints
│   │   ├── stock.py       # Stock APIs
│   │   ├── graph.py       # Graph APIs
│   │   ├── news.py        # News APIs
│   │   ├── company.py     # Legacy compatibility
│   │   └── websocket.py   # WebSocket endpoints
│   ├── services/          # Business logic
│   │   ├── stock.py       # Stock service
│   │   ├── graph.py       # Graph service
│   │   ├── news.py        # News service
│   │   ├── company_service.py    # Company data service
│   │   ├── data_collection_service.py  # Data orchestration
│   │   ├── massive_service.py    # Massive API client
│   │   └── mock_data.py   # Mock data generators
│   ├── config.py          # Configuration
│   └── main.py            # FastAPI application
├── tests/
│   ├── unit/              # Unit tests
│   ├── integration/       # Integration tests
│   └── conftest.py        # Test fixtures
├── data/                  # SQLite database (gitignored)
├── .env                   # Environment variables (gitignored)
├── requirements.txt       # Python dependencies (uv sync preferred)
├── pyproject.toml         # Project metadata + deps
├── pytest.ini            # Pytest configuration
├── Dockerfile             # Production image
├── docker-compose.yml     # Local: backend + Redis + Netdata
└── README.md             # This file
```

---

## Deployment

Deploys go **only** through Git → PR → GitHub Actions → Docker on the Netcup VPS — never SSH/rsync
by hand. CI builds `ghcr.io/haoweichan/tinboker-backend` and deploys per branch/tag:

| Branch / ref | Environment | URL · port |
|--------------|-------------|------------|
| merge to `develop` | Dev | dev-api.tinboker.com `:8001` |
| merge to `main` | Staging | staging-api.tinboker.com `:8002` |
| `v*` tag on `main` | Production | api.tinboker.com `:8000` |

The full procedure (pre-merge checks, health verification, rollback) is in
[`../docs/workflows/deploy-flow.md`](../docs/workflows/deploy-flow.md). Infra/ops reference:
[`../docs/infra-runbook.md`](../docs/infra-runbook.md).

### Environment Variables for Production

```env
ENVIRONMENT=production
USE_POSTGRES=true
POSTGRES_HOST=...            # Cloud SQL PostgreSQL
REDIS_URL=redis://...
MASSIVE_API_KEY=...
FINMIND_API_KEY=...
JWT_SECRET_KEY=...
CORS_ORIGINS=https://tinboker.com,https://staging.tinboker.com
```

Production secrets are loaded from GCP Secret Manager at startup by `config_loader.py` — see
the root [`CLAUDE.md`](../CLAUDE.md) "Environment Variables".

---

## Development

### Adding New Features

1. **Database**: Add CRUD operations in `src/database/`
2. **Models**: Define Pydantic models in `src/models/`
3. **Service**: Implement business logic in `src/services/`
4. **API**: Create endpoints in `src/routers/`
5. **Tests**: Add tests in `tests/unit/` and `tests/integration/`

### Code Style

- Follow PEP 8 style guide
- Use type hints for all functions
- Document functions with docstrings
- Run linter: `pylint src/`

---

## Troubleshooting

### Database Issues

**Problem**: Database not initialized
```bash
# Solution: Run migration script
python -m src.database.migrate
```

### Port Already in Use

**Problem**: Port 5174 is already in use
```bash
# Solution: Use a different port
uvicorn src.main:app --port 8000
```

### Import Errors

**Problem**: Module import errors
```bash
# Solution: Ensure virtual environment is activated
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Reinstall dependencies
pip install -r requirements.txt
```

---

## Contributing

1. Branch from `develop`: `git checkout -b feat/<name> develop` (or `fix/<name>`)
2. Make your change; run `ruff check src/` and `pytest tests/ -v`
3. Open a PR targeting `develop` — CI (`backend-ci.yml`) must pass its `ci-gate`
4. Merge to `develop` auto-deploys to dev; promote via `develop` → `main` (staging) → `v*` tag (prod)

See the root [`CLAUDE.md`](../CLAUDE.md) and [`AGENTS.md`](AGENTS.md) for conventions.

---

## License

No `LICENSE` file is present in the repository yet; usage terms are TBD. Add a root `LICENSE`
file before treating this as openly licensed.

---

## Support

For issues, questions, or contributions, please open an issue on GitHub.

---

## Acknowledgments

- **FastAPI**: Modern, fast web framework
- **Massive API**: US financial data provider
- **FinMind**: Taiwan/US stock data
- **Netcup VPS + Docker + Caddy**: hosting & reverse proxy
- **Cloudflare**: CDN + DNS

