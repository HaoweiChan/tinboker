# Backend API & Frontend Implementation Comparison

This document compares the backend API (as defined in `openapi_20251215.yaml`) with the current frontend implementation to identify matches, gaps, and required modifications.

**Last Updated:** Based on OpenAPI spec dated 2025-12-15

---

## Executive Summary

### ✅ Fully Matched Endpoints
- Graph CRUD operations (`/api/graphs/*`)
- Stock endpoints (`/api/stocks/*`)
- News endpoints (`/api/news/*`)
- Content endpoints (`/api/content/*`)
- Visual endpoints (`/api/visuals/*`)
- Podcast endpoints (`/api/podcast/*`)

### ⚠️ Partially Matched / Schema Issues
- Some endpoints have empty schemas in OpenAPI but return data
- Frontend uses workarounds for missing query parameters

### ❌ Missing Endpoints (Frontend Needs)
- `GET /api/episodes/recent` - Critical for homepage
- `GET /api/episodes/by-ticker/{ticker}` - For stock detail pages
- `GET /api/stocks/{ticker}/history` - For sparklines
- Authentication endpoints (`/api/auth/*`)
- User preferences endpoints (`/api/user/*`)

### ✅ Available but Not Used Optimally
- `GET /api/stocks` supports `q` (search) and `limit` parameters - frontend should use this
- `GET /api/episodes/recent` exists in backend but frontend uses inefficient workaround
- `GET /api/episodes/by-ticker/{ticker}` exists in backend
- `GET /api/tags` exists (mock data)
- `GET /api/episodes/by-tag/{tag}` exists (mock data)
- `GET /api/market/indices` exists (mock data)
- `GET /api/concepts` exists (mock data)
- `GET /api/top-movers` exists (mock data)

---

## Detailed Endpoint Comparison

### 1. Graph Endpoints

#### ✅ `GET /api/graphs`
- **Backend:** ✅ Available
- **Frontend:** ✅ Implemented in `getSortedGraphs()`
- **Status:** ✅ Match
- **Query Params:**
  - `sort_by`: `concept_id` | `created_at` | `updated_at` (default: `concept_id`)
- **Notes:** Frontend uses default `concept_id` sorting

#### ✅ `POST /api/graphs`
- **Backend:** ✅ Available
- **Frontend:** ✅ Implemented in `createGraph()`
- **Status:** ✅ Match
- **Request Body:** `GraphCreate` schema matches frontend expectations

#### ✅ `GET /api/graphs/{graph_id}`
- **Backend:** ✅ Available
- **Frontend:** ✅ Implemented in `getGraphById()`
- **Status:** ✅ Match
- **Response:** Returns `GraphData` with nodes and edges

#### ✅ `DELETE /api/graphs/{graph_id}`
- **Backend:** ✅ Available
- **Frontend:** ✅ Implemented in `deleteGraph()`
- **Status:** ✅ Match

#### ✅ `PUT /api/graphs/{graph_id}/nodes/{node_id}`
- **Backend:** ✅ Available
- **Frontend:** ✅ Implemented in `modifyNode()`
- **Status:** ✅ Match
- **Request Body:** `NodeUpdate` - all fields optional

#### ✅ `DELETE /api/graphs/{graph_id}/nodes/{node_id}`
- **Backend:** ✅ Available
- **Frontend:** ✅ Implemented in `deleteNode()`
- **Status:** ✅ Match

#### ✅ `PUT /api/graphs/{graph_id}/edges/{edge_id}`
- **Backend:** ✅ Available
- **Frontend:** ✅ Implemented in `modifyEdge()`
- **Status:** ✅ Match
- **Request Body:** `EdgeUpdate` - all fields optional

#### ✅ `DELETE /api/graphs/{graph_id}/edges/{edge_id}`
- **Backend:** ✅ Available
- **Frontend:** ✅ Implemented in `deleteEdge()`
- **Status:** ✅ Match

---

### 2. Stock Endpoints

#### ✅ `GET /api/stocks`
- **Backend:** ✅ Available
- **Frontend:** ✅ Implemented in `getSortedStocks()`
- **Status:** ⚠️ **Partially Matched** - Frontend not using all query params
- **Query Params:**
  - `sort_by`: `ticker` | `name` | `price` | `change_percent` | `market_cap` (default: `ticker`)
  - `limit`: `1-200` (default: `50`) - **Frontend not using**
  - `q`: Search query (filters by ticker or name) - **Frontend not using**
- **Frontend Usage:** Only uses `sort_by` parameter
- **Recommendation:** 
  - Frontend should use `q` parameter for stock search functionality
  - Frontend should use `limit` parameter for pagination
  - Currently frontend filters mock data locally - should migrate to API

#### ✅ `GET /api/stocks/{ticker}`
- **Backend:** ✅ Available
- **Frontend:** ✅ Implemented in `getStockByTicker()`
- **Status:** ✅ Match
- **Query Params:**
  - `timeframe`: `1H` | `1D` | `1W` | `1M` | `3M` | `6M` | `1Y` | `YTD` | `ALL` (optional)
- **Response:** `CompanyDetail` schema matches frontend expectations

#### ⚠️ `GET /api/stocks/{ticker}/basic`
- **Backend:** ✅ Available
- **Frontend:** ✅ Implemented in `getStockBasicInfo()`
- **Status:** ⚠️ **Schema Issue**
- **Problem:** OpenAPI spec shows empty schema `{}`
- **Frontend:** Returns raw data without validation
- **Recommendation:** Backend should define proper schema for basic stock info

#### ❌ `GET /api/stocks/{ticker}/history`
- **Backend:** ✅ **Available** (line 434-475 in OpenAPI)
- **Frontend:** ❌ **Not Implemented**
- **Status:** ❌ **Missing Frontend Implementation**
- **Description:** Returns lightweight price history for sparklines
- **Query Params:**
  - `timeframe`: `1H` | `1D` | `1W` | `1M` | `3M` | `6M` | `1Y` | `YTD` | `ALL` (optional)
- **Response:** Empty schema `{}` - needs definition
- **Frontend Need:** Used for sparkline charts in Watchlist and Sidebar
- **Current Workaround:** Frontend generates random data
- **Action Required:** 
  1. Backend should define response schema
  2. Frontend should implement `getStockHistory(ticker, timeframe?)` function

---

### 3. News Endpoints

#### ✅ `GET /api/news`
- **Backend:** ✅ Available
- **Frontend:** ✅ Implemented in `getSortedNews()`
- **Status:** ✅ Match
- **Query Params:**
  - `sort_by`: `date` | `created_at` | `updated_at` | `title` (default: `date`)

#### ✅ `GET /api/news/{news_id}`
- **Backend:** ✅ Available
- **Frontend:** ✅ Implemented in `getNewsById()`
- **Status:** ✅ Match
- **Response:** `StockEvent` schema

#### ✅ `POST /api/news/fetch/{ticker}`
- **Backend:** ✅ Available
- **Frontend:** ✅ Implemented in `fetchNewsFromMassive()`
- **Status:** ✅ Match
- **Query Params:**
  - `limit`: Maximum articles to fetch (default: `10`)

---

### 4. Content Endpoints

#### ✅ `GET /api/content/index`
- **Backend:** ✅ Available
- **Frontend:** ✅ Implemented in `getContentIndex()`
- **Status:** ✅ Match
- **Response:** Empty schema - frontend handles array or object format

#### ✅ `GET /api/content/{ticker}`
- **Backend:** ✅ Available
- **Frontend:** ✅ Implemented in `getContentByTicker()`
- **Status:** ✅ Match
- **Response:** Returns `ContentAsset` with `svg_url` and `article_url`

---

### 5. Visual Endpoints

#### ⚠️ `GET /api/visuals/supply-chain`
- **Backend:** ✅ Available
- **Frontend:** ✅ Implemented in `getSupplyChainVisual()`
- **Status:** ⚠️ **Schema Issue**
- **Problem:** OpenAPI spec shows empty schema `{}`
- **Frontend:** Uses `processGraphDataResponse()` to handle wrapped/unwrapped formats
- **Recommendation:** Backend should define `GraphData` schema for response

#### ⚠️ `GET /api/visuals/ownership`
- **Backend:** ✅ Available
- **Frontend:** ✅ Implemented in `getOwnershipVisual()`
- **Status:** ⚠️ **Schema Issue**
- **Problem:** OpenAPI spec shows empty schema `{}`
- **Frontend:** Uses `processGraphDataResponse()` to handle wrapped/unwrapped formats
- **Recommendation:** Backend should define `GraphData` schema for response

#### ⚠️ `GET /api/visuals/cluster`
- **Backend:** ✅ Available
- **Frontend:** ✅ Implemented in `getClusterVisual()`
- **Status:** ⚠️ **Schema Issue**
- **Problem:** OpenAPI spec shows empty schema `{}`
- **Frontend:** Uses `processGraphDataResponse()` to handle wrapped/unwrapped formats
- **Recommendation:** Backend should define `GraphData` schema for response

#### ⚠️ `GET /api/visuals/interactive-models`
- **Backend:** ✅ Available
- **Frontend:** ✅ Implemented in `getInteractiveModels()`
- **Status:** ⚠️ **Schema Issue**
- **Problem:** OpenAPI spec shows empty schema `{}`
- **Frontend:** Handles array or wrapped format
- **Recommendation:** Backend should define `InteractiveModelData[]` schema

---

### 6. Podcast Endpoints

#### ✅ `GET /api/podcast`
- **Backend:** ✅ Available
- **Frontend:** ✅ Implemented in `getSortedPodcasts()`
- **Status:** ✅ Match
- **Query Params:**
  - `sort_by`: `name` | `episode_count` | `created_at` | `updated_at` (default: `name`)
  - `order`: `asc` | `desc` (default: `asc`)
  - `limit`: `1-200` (default: `50`)
  - `offset`: Pagination offset (default: `0`)

#### ✅ `GET /api/podcast/{podcast_name}`
- **Backend:** ✅ Available
- **Frontend:** ✅ Implemented in `getPodcastByName()`
- **Status:** ✅ Match
- **Response:** `Podcast` schema

#### ✅ `GET /api/podcast/{podcast_name}/episodes`
- **Backend:** ✅ Available
- **Frontend:** ✅ Implemented in `getPodcastEpisodes()`
- **Status:** ✅ Match
- **Query Params:**
  - `sort_by`: `created_time` | `episode_number` | `episode_title` (default: `created_time`)
  - `order`: `asc` | `desc` (default: `desc`)
  - `limit`: `1-200` (default: `50`)
  - `offset`: Pagination offset (default: `0`)

#### ✅ `GET /api/podcast/{podcast_name}/episodes/{episode_id}`
- **Backend:** ✅ Available
- **Frontend:** ✅ Implemented in `getEpisodeById()`
- **Status:** ✅ Match
- **Response:** `Episode` schema with `tags` field (array of strings)

#### ✅ `GET /api/episodes/recent`
- **Backend:** ✅ **Available** (line 920-980 in OpenAPI)
- **Frontend:** ⚠️ **Inefficient Implementation**
- **Status:** ⚠️ **Should Use Direct Endpoint**
- **Description:** Returns recent episodes across all podcasts
- **Query Params:**
  - `limit`: `1-200` (default: `20`)
  - `offset`: Pagination offset (default: `0`)
  - `podcast_name`: Optional filter by podcast name
- **Frontend Current:** Uses `getAllRecentEpisodes()` helper that:
  1. Fetches all podcasts
  2. Fetches episodes from each podcast
  3. Merges and sorts locally
- **Recommendation:** 
  - Frontend should use `GET /api/episodes/recent` directly
  - Much more efficient than current approach
  - **Action Required:** Implement `getRecentEpisodes(limit?, offset?, podcastName?)` function

#### ✅ `GET /api/episodes/by-ticker/{ticker}`
- **Backend:** ✅ **Available** (line 981-1041 in OpenAPI)
- **Frontend:** ❌ **Not Implemented**
- **Status:** ❌ **Missing Frontend Implementation**
- **Description:** Returns episodes that mention a specific ticker
- **Query Params:**
  - `limit`: `1-200` (default: `50`)
  - `offset`: Pagination offset (default: `0`)
- **Frontend Need:** Used on stock detail pages to show related podcast mentions
- **Current Workaround:** Frontend filters mock data by checking `related_tickers` field
- **Action Required:** 
  1. Implement `getEpisodesByTicker(ticker, limit?, offset?)` function
  2. Replace mock data filtering with API call

---

### 7. Tag Endpoints (Mock Data)

#### ✅ `GET /api/tags`
- **Backend:** ✅ **Available** (line 1042-1058 in OpenAPI) - **MOCK DATA**
- **Frontend:** ❌ **Not Implemented**
- **Status:** ⚠️ **Available but Mock**
- **Description:** Returns list of available tags with episode counts
- **Response:** `TagsResponse` schema
- **Frontend Need:** Tag pages, search suggestions
- **Current Workaround:** Frontend extracts tags from episode mock data
- **Action Required:** 
  1. Implement `getTags()` function
  2. Replace mock extraction with API call
  3. Backend should implement real data (currently mock)

#### ✅ `GET /api/episodes/by-tag/{tag}`
- **Backend:** ✅ **Available** (line 1059-1111 in OpenAPI) - **MOCK DATA**
- **Frontend:** ❌ **Not Implemented**
- **Status:** ⚠️ **Available but Mock**
- **Description:** Returns episodes with a specific tag
- **Query Params:**
  - `limit`: `1-200` (default: `50`)
  - `offset`: Pagination offset (default: `0`)
- **Response:** `EpisodesByTagResponse` schema
- **Frontend Need:** Tag detail pages
- **Current Workaround:** Frontend filters episodes by tag locally
- **Action Required:** 
  1. Implement `getEpisodesByTag(tag, limit?, offset?)` function
  2. Replace local filtering with API call
  3. Backend should implement real data (currently mock)

---

### 8. Market & Concept Endpoints (Mock Data)

#### ✅ `GET /api/market/indices`
- **Backend:** ✅ **Available** (line 1112-1131 in OpenAPI) - **MOCK DATA**
- **Frontend:** ❌ **Not Implemented**
- **Status:** ⚠️ **Available but Mock**
- **Description:** Returns current market index values
- **Response:** Array of `MarketIndex` objects
- **Frontend Need:** Header ticker bar showing market indices
- **Current Workaround:** Static mock data in `src/data/market.ts`
- **Action Required:** 
  1. Implement `getMarketIndices()` function
  2. Replace static data with API call
  3. Backend should implement real data (currently mock)

#### ✅ `GET /api/concepts`
- **Backend:** ✅ **Available** (line 1132-1151 in OpenAPI) - **MOCK DATA**
- **Frontend:** ❌ **Not Implemented**
- **Status:** ⚠️ **Available but Mock**
- **Description:** Returns list of available industry concepts/themes
- **Response:** Array of `ConceptMetadata` objects
- **Frontend Need:** Concept selection pages
- **Current Workaround:** Mock data in `src/services/mocks/concepts.ts`
- **Action Required:** 
  1. Implement `getConcepts()` function
  2. Replace mock data with API call
  3. Backend should implement real data (currently mock)

#### ✅ `GET /api/top-movers`
- **Backend:** ✅ **Available** (line 1152-1192 in OpenAPI) - **MOCK DATA**
- **Frontend:** ❌ **Not Implemented**
- **Status:** ⚠️ **Available but Mock**
- **Description:** Returns top moving stocks by price change percentage
- **Query Params:**
  - `limit`: `1-50` (default: `10`)
- **Response:** Array of `TopMover` objects
- **Note:** Can also be derived from `GET /api/stocks?sort_by=change_percent&order=desc&limit={limit}`
- **Frontend Need:** Top movers widget
- **Current Workaround:** Mock data in `src/services/mocks/topMovers.ts`
- **Action Required:** 
  1. Implement `getTopMovers(limit?)` function
  2. Replace mock data with API call
  3. Backend should implement real data (currently mock) OR use stocks endpoint

---

### 9. Authentication Endpoints

#### ❌ `POST /api/auth/google`
- **Backend:** ❌ **Not in OpenAPI spec**
- **Frontend:** ⚠️ **Partially Implemented** (see `src/services/api/auth.ts`)
- **Status:** ❌ **Missing Backend Endpoint**
- **Description:** Verifies Google ID Token and establishes user session
- **Frontend Expects:**
  ```typescript
  interface GoogleLoginRequest {
    idToken: string;
  }
  
  interface AuthResponse {
    user: {
      id: string;
      email: string;
      name: string;
      avatar?: string;
    };
    token: string; // JWT Session token
  }
  ```
- **Current Status:** Frontend has auth service but no backend endpoint
- **Action Required:** Backend should implement Google OAuth verification endpoint

---

### 10. User Preferences Endpoints

#### ❌ User Data Endpoints
- **Backend:** ❌ **Not in OpenAPI spec**
- **Frontend:** ⚠️ **Uses LocalStorage** (Zustand persist)
- **Status:** ❌ **Missing Backend Endpoints**

**Required Endpoints:**

1. **Watchlist:**
   - `GET /api/user/watchlist` - Get user's watchlist
   - `POST /api/user/watchlist` - Add stock to watchlist
   - `DELETE /api/user/watchlist/{symbol}` - Remove stock from watchlist

2. **Subscriptions:**
   - `GET /api/user/subscriptions` - Get subscribed podcasts
   - `POST /api/user/subscriptions` - Subscribe to podcast
   - `DELETE /api/user/subscriptions/{podcast_id}` - Unsubscribe

3. **Alerts:**
   - `GET /api/user/alerts` - Get active alerts
   - `POST /api/user/alerts` - Create alert (price target, news mention)
   - `DELETE /api/user/alerts/{alert_id}` - Delete alert

**Current Workaround:** All user preferences stored in `localStorage` via Zustand persist

**Action Required:** Backend should implement user data endpoints (requires authentication)

---

## Schema Comparison

### Episode Schema

**Backend Schema (OpenAPI):**
```yaml
Episode:
  properties:
    id: string
    podcast_name: string
    episode_title: string | null
    episode_number: integer | null
    transcript: string
    summary_content: string
    summary_image: string
    related_tickers: string[]
    tags: string[]  # ✅ Present in backend
    created_time: integer
    number_click: integer (default: 0)
    num_likes: integer (default: 0)
    raw_mp3: string | null
```

**Frontend Expects:**
- ✅ All fields match
- ✅ `tags` field is present (frontend was expecting this)

**Status:** ✅ **Match**

### Podcast Schema

**Backend Schema (OpenAPI):**
```yaml
Podcast:
  properties:
    id: string
    name: string
    episode_count: integer (default: 0)
    created_at: integer | null
    updated_at: integer | null
```

**Frontend May Need (Optional):**
- `avatar`: string (avatar image URL)
- `description`: string (podcast description)
- `categories`: string[] (content categories)
- `rating`: number (average rating)
- `subscriber_count`: number

**Status:** ✅ **Match** (additional fields are optional enhancements)

### Stock Schema Issues

**Backend `GET /api/stocks/{ticker}/basic`:**
- ❌ Empty schema `{}` in OpenAPI
- **Recommendation:** Define `StockBasicInfo` schema

**Backend `GET /api/stocks/{ticker}/history`:**
- ❌ Empty schema `{}` in OpenAPI
- **Recommendation:** Define `StockHistoryResponse` schema with price data points

---

## Priority Action Items

### HIGH Priority (Critical for Production)

1. **Frontend: Implement `GET /api/episodes/recent`**
   - Replace `getAllRecentEpisodes()` with direct API call
   - Much more efficient
   - **File:** `src/services/api/index.ts`

2. **Frontend: Implement `GET /api/episodes/by-ticker/{ticker}`**
   - Replace mock data filtering
   - **File:** `src/services/api/index.ts`

3. **Frontend: Use `GET /api/stocks` search parameter**
   - Use `q` parameter for stock search
   - Replace local mock data filtering
   - **File:** `src/services/api/index.ts`

4. **Backend: Define schemas for empty endpoints**
   - `GET /api/stocks/{ticker}/basic` → `StockBasicInfo` schema
   - `GET /api/stocks/{ticker}/history` → `StockHistoryResponse` schema
   - `GET /api/visuals/*` → `GraphData` schema
   - `GET /api/visuals/interactive-models` → `InteractiveModelData[]` schema

5. **Backend: Implement authentication**
   - `POST /api/auth/google` endpoint
   - User session management

### MEDIUM Priority (Improves UX)

6. **Frontend: Implement mock data endpoints**
   - `GET /api/tags` → `getTags()`
   - `GET /api/episodes/by-tag/{tag}` → `getEpisodesByTag()`
   - `GET /api/market/indices` → `getMarketIndices()`
   - `GET /api/concepts` → `getConcepts()`
   - `GET /api/top-movers` → `getTopMovers()`

7. **Frontend: Implement `GET /api/stocks/{ticker}/history`**
   - For sparkline charts
   - Replace random data generation

8. **Backend: Implement real data for mock endpoints**
   - Replace mock implementations with real data
   - `GET /api/tags`, `/api/episodes/by-tag/{tag}`, `/api/market/indices`, `/api/concepts`, `/api/top-movers`

### LOW Priority (Nice to Have)

9. **Backend: Add optional Podcast fields**
   - `avatar`, `description`, `categories`, `rating`, `subscriber_count`

10. **Backend: Implement user preferences endpoints**
    - Watchlist, subscriptions, alerts
    - Requires authentication first

---

## Migration Checklist

### Frontend Tasks

- [ ] Implement `getRecentEpisodes()` using `GET /api/episodes/recent`
- [ ] Implement `getEpisodesByTicker()` using `GET /api/episodes/by-ticker/{ticker}`
- [ ] Implement `getStockHistory()` using `GET /api/stocks/{ticker}/history`
- [ ] Update `getSortedStocks()` to use `q` and `limit` parameters
- [ ] Implement `getTags()` using `GET /api/tags`
- [ ] Implement `getEpisodesByTag()` using `GET /api/episodes/by-tag/{tag}`
- [ ] Implement `getMarketIndices()` using `GET /api/market/indices`
- [ ] Implement `getConcepts()` using `GET /api/concepts`
- [ ] Implement `getTopMovers()` using `GET /api/top-movers`
- [ ] Remove `getAllRecentEpisodes()` helper function
- [ ] Replace mock data filtering with API calls

### Backend Tasks

- [ ] Define `StockBasicInfo` schema for `GET /api/stocks/{ticker}/basic`
- [ ] Define `StockHistoryResponse` schema for `GET /api/stocks/{ticker}/history`
- [ ] Define `GraphData` schema for visual endpoints
- [ ] Define `InteractiveModelData[]` schema for `GET /api/visuals/interactive-models`
- [ ] Implement `POST /api/auth/google` endpoint
- [ ] Implement real data for mock endpoints (tags, market indices, concepts, top movers)
- [ ] Implement user preferences endpoints (requires auth)

---

## Notes

1. **Base URL:** Frontend uses `VITE_API_BASE_URL` env variable or defaults to:
   - Development: `https://staging-api.tinboker.com`
   - Production: `https://api.tinboker.com`

2. **Error Handling:** Frontend uses `fetchWithFallback()` pattern - tries API first, falls back to mock data on error/timeout

3. **Response Formats:** Some endpoints return wrapped format `{ data: {...}, timestamp: "..." }` while others return direct format. Frontend handles both.

4. **Timeout:** Frontend uses 150s default timeout, 30s for visual endpoints

5. **Mock Data:** Many endpoints marked as "MOCK DATA" in OpenAPI - these should be implemented with real data for production

