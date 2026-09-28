# API Gaps Documentation

> **Historical snapshot.** This document records earlier plans or implementation details.
> Routes, API gaps, and environment instructions below may be stale. For current
> frontend guidance, start with the [frontend docs index](../README.md).

This document identifies missing endpoints and data fields required by the frontend but not provided by the backend API (as defined in `src/schemas/openapi.yaml`).

---

## Recently Integrated APIs (TrendBrief WebUI Redesign)

The following APIs are now available in the backend and have been integrated:

### Podcast APIs (Available)

| Endpoint | Status | Usage |
|----------|--------|-------|
| `GET /api/podcast` | ✅ Integrated | Get list of podcasters/channels |
| `GET /api/podcast/{podcast_name}` | ✅ Integrated | Get podcaster details |
| `GET /api/podcast/{podcast_name}/episodes` | ✅ Integrated | Get episodes for a podcaster |
| `GET /api/podcast/{podcast_name}/episodes/{episode_id}` | ✅ Integrated | Get specific episode |

**Frontend Integration:** See `src/services/api/index.ts` - Podcast Endpoints section

---

## Content & Markdown Requirements (NEW)

### Content Rendering for `GET /api/podcast/{podcast_name}/episodes/{episode_id}`

The WebUI expects the episode content (or summary) to be in **Markdown format**. To support interactive features like clickable stock tickers, the backend should format stock mentions in a specific way.

**Requirement:**
- Tickers should be wrapped in a format that the frontend can parse and turn into links.
- **Preferred Format:** `[Display Text](ticker:SYMBOL)` or standard markdown links with a specific schema.
- **Current Mock Implementation:** The frontend currently parses plain text using a regex based on `summary.highlights`. 
- **Future Implementation:** To make the content fully dynamic, the backend should return Markdown where stock mentions are explicitly marked.

**Example Markdown from Backend:**
```markdown
本集重點分析 [台積電](ticker:2330) 的法說會內容，以及 [NVDA](ticker:NVDA) 在 AI 領域的最新進展。
```

**Frontend Rendering Logic:**
1.  The frontend will use `react-markdown` (or custom parser).
2.  It will look for links starting with `ticker:`.
3.  It will render these as clickable buttons that navigate to `/stock/{SYMBOL}`.

---

## Missing Endpoints (New for TrendBrief WebUI)

### 1. `GET /api/episodes/recent` (NEW - HIGH PRIORITY)
**Status:** Not in OpenAPI spec  
**Frontend Usage:** Homepage episode feed  
**Description:** Returns list of recent episodes across ALL podcasts, sorted by created_time descending

**Frontend Expects:**
```typescript
interface RecentEpisodesResponse {
  episodes: Episode[];
  total: number;
  hasMore: boolean;
}

// Query params:
// - limit: number (default 20)
// - offset: number (default 0)
// - podcast_name?: string (optional filter)
```

**Current Workaround:** 
- Using `getAllRecentEpisodes()` helper in `src/services/api/index.ts`
- This fetches all podcasts, then fetches episodes from each, which is inefficient
- Mock data used via `src/data/mockData.ts` - `MOCK_EPISODES`

**Recommendation:** Add a dedicated endpoint that queries all episodes sorted by `created_time`

---

### 2. `GET /api/episodes/by-ticker/{ticker}` (NEW - MEDIUM PRIORITY)
**Status:** Not in OpenAPI spec  
**Frontend Usage:** Stock/Ticker detail page - showing related podcast mentions  
**Description:** Returns episodes that mention a specific stock ticker

**Frontend Expects:**
```typescript
interface EpisodesByTickerResponse {
  ticker: string;
  episodes: Episode[];
  total: number;
}
```

**Current Workaround:** 
- Frontend filters `MOCK_EPISODES` by checking `summary.highlights` for matching ticker
- Could potentially use `related_tickers` field in Episode schema

**Recommendation:** Add endpoint or allow filtering episodes by `related_tickers` field

---

### 3. `GET /api/tags` (NEW - MEDIUM PRIORITY)
**Status:** Not in OpenAPI spec  
**Frontend Usage:** Tag pages, search suggestions  
**Description:** Returns list of available tags/topics with episode counts

**Frontend Expects:**
```typescript
interface Tag {
  id: string;
  name: string;          // e.g., "#AI伺服器", "#散熱"
  episode_count: number;
}

interface TagsResponse {
  tags: Tag[];
}
```

**Current Workaround:** 
- Extracting tags from episode data (`episode.tags` field)
- Tags are extracted from mock episodes in `MOCK_EPISODES`

**Recommendation:** 
- Option 1: Add tags endpoint that aggregates unique tags from episodes
- Option 2: Add `tags` field to Episode schema (already exists in mock data)

---

### 4. `GET /api/episodes/by-tag/{tag}` (NEW - MEDIUM PRIORITY)
**Status:** Not in OpenAPI spec  
**Frontend Usage:** Tag detail page  
**Description:** Returns episodes with a specific tag

**Frontend Expects:**
```typescript
interface EpisodesByTagResponse {
  tag: string;
  episodes: Episode[];
  total: number;
}
```

**Current Workaround:** Frontend filters episodes by tag locally

**Recommendation:** Add endpoint or add `tags` to Episode schema and allow filtering

---

### 5. `GET /api/market/indices` (NEW - LOW PRIORITY)
**Status:** Not in OpenAPI spec  
**Frontend Usage:** Header ticker bar showing market indices  
**Description:** Returns current market index values

**Frontend Expects:**
```typescript
interface MarketIndex {
  id: string;
  name: string;      // e.g., "加權", "櫃買", "NVDA"
  ticker: string;    // Symbol for navigation
  value: string;     // Current value
  change: string;    // Change indicator
  isPositive: boolean;
}
```

**Current Workaround:** Using static mock data in `src/data/market.ts` - `TICKER_DATA`

**Recommendation:** Could derive from existing stock endpoints or add dedicated endpoint

---

### 6. Existing Gaps (Previously Documented)

#### 6.1 `GET /api/concepts`
**Status:** Not in OpenAPI spec  
**Frontend Usage:** `src/services/mocks/concepts.ts` - `mockConcepts`  
**Description:** Returns list of available industry concepts/themes (e.g., robotics, ai, energy)

**Frontend Expects:**
```typescript
interface ConceptMetadata {
  id: string;              // e.g., 'robotics', 'ai', 'energy'
  title: string;           // e.g., 'Robotics & Automation'
  description: string;     // Short description for card display
  icon: string;            // Icon/emoji representation
  gradient: string;        // Tailwind gradient classes
}
```

**Current Workaround:** Using `mockConcepts` from `src/services/mocks/concepts.ts`

---

#### 6.2 `GET /api/top-movers`
**Status:** Not in OpenAPI spec  
**Frontend Usage:** `src/services/mocks/topMovers.ts` - `mockTopMovers`  
**Description:** Returns list of top moving stocks (by price change percentage)

**Frontend Expects:**
```typescript
interface TopMover {
  ticker: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
}
```

**Current Workaround:** Using `mockTopMovers` from `src/services/mocks/topMovers.ts`

**Recommendation:** Could derive from `GET /api/stocks?sort_by=change_percent&limit=10`

---

#### 6.3 Sector/Industry Data Endpoints
**Status:** Not in OpenAPI spec  
**Frontend Usage:** `src/services/mocks/sectorData.ts`

**Missing Functions:**
- `getSectorBubbleData()` - Sector bubble chart data
- `getSectorPerformanceStats()` - Sector performance statistics
- `getTreeMapData()` - Tree map visualization data

---

## Authentication Endpoints (Required for Google Login)

### 7. `POST /api/auth/google` (NEW - HIGH PRIORITY)
**Status:** Not in OpenAPI spec
**Frontend Usage:** Google Login Callback
**Description:** Verifies Google ID Token sent from frontend and establishes user session

**Frontend Expects:**
```typescript
// Request Body
interface GoogleLoginRequest {
  idToken: string; // The token returned by Google OAuth flow
}

// Response
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

**Current Workaround:** None (Auth is not implemented)

**Recommendation:** Implement backend verification of Google ID Token (using `google-auth-library` or similar) and JWT issuance.

---

### 8. `GET /api/stocks` (NEW - MEDIUM PRIORITY)
**Status:** Not in OpenAPI spec
**Frontend Usage:** Watchlist search modal, Popular Tickers widget, Stock Search
**Description:** Returns a searchable list of all available stocks/companies.

**Frontend Expects:**
```typescript
interface StockBasic {
  symbol: string;    // e.g., "2330"
  name: string;      // e.g., "台積電"
  market: string;    // e.g., "TW", "US" (optional)
  sector?: string;   // e.g., "Semiconductor" (optional)
}

interface StockSearchResponse {
  results: StockBasic[];
  total: number;
}

// Query params:
// - q: string (search query)
// - limit: number
```

**Current Workaround:**
- Frontend filters `MOCK_STOCKS` array locally in `ProfilePage.tsx` and `DashboardWidgets.tsx`.
- Real-time stock search functionality in the "Add to Watchlist" modal relies entirely on mock data.

**Recommendation:** Add a lightweight endpoint for stock searching/autocomplete.

---

## User Preferences & State Sync (NEW - HIGH PRIORITY)

To persist user actions like "Add to Watchlist", "Subscribe", and "Set Alert" across sessions/devices, we need backend endpoints to sync this state. Currently, the frontend uses `localStorage` (Zustand persist).

### 9. User Data Endpoints

**9.1 Watchlist**
- `GET /api/user/watchlist` - Get user's watchlist
- `POST /api/user/watchlist` - Add stock to watchlist
- `DELETE /api/user/watchlist/{symbol}` - Remove stock from watchlist

**9.2 Subscriptions**
- `GET /api/user/subscriptions` - Get subscribed podcasts
- `POST /api/user/subscriptions` - Subscribe to podcast
- `DELETE /api/user/subscriptions/{podcast_id}` - Unsubscribe

**9.3 Alerts**
- `GET /api/user/alerts` - Get active alerts
- `POST /api/user/alerts` - Create alert (e.g., price target, news mention)
- `DELETE /api/user/alerts/{alert_id}` - Delete alert

**Status:** Not in OpenAPI spec
**Frontend Usage:** `src/store/useAppStore.ts` (currently mock/local persistence)

---

## Stock Data & Sparklines (NEW - MEDIUM PRIORITY)

### 10. `GET /api/stocks/{symbol}/history`
**Status:** Not in OpenAPI spec
**Frontend Usage:** Sparkline charts in Watchlist and Sidebar
**Description:** Returns historical price data for a stock (e.g., last 30 days or intraday) to render sparklines.

**Frontend Expects:**
```typescript
interface StockHistoryResponse {
  symbol: string;
  data: number[]; // Array of price points (normalized or raw)
  // or
  data: { time: string; price: number }[];
}
```

**Current Workaround:**
- Frontend generates random data in `src/components/charts/SimpleSparkline.tsx` to simulate charts.

**Recommendation:** Provide a lightweight history endpoint optimized for small charts (sparklines).

---

## Episode Schema Enhancement Needed

The current `Episode` schema in OpenAPI is missing some fields needed by the new UI:

### Missing Episode Fields

| Field | Type | Description | Priority |
|-------|------|-------------|----------|
| `tags` | `string[]` | Topic tags (e.g., "#AI伺服器", "#散熱") | HIGH |
| `is_hot` | `boolean` | Whether episode is trending/hot | LOW |
| `time_ago` | `string` | Human-readable time (e.g., "2小時前") | LOW (can derive from created_time) |
| `summary_points` | `SummaryPoint[]` | Structured summary with highlights | MEDIUM |

**Recommended `SummaryPoint` structure:**
```typescript
interface SummaryPoint {
  text: string;
  highlights?: Array<{
    text: string;
    symbol?: string;    // Stock ticker if applicable
    type?: 'stock';     // Highlight type
  }>;
}
```

**Current Workaround:** 
- Using mock data structure from `src/data/mockData.ts`
- Frontend manually parses `summary_content` markdown

---

## Podcast Schema Enhancement Needed

### Missing Podcast Fields

| Field | Type | Description | Priority |
|-------|------|-------------|----------|
| `avatar` | `string` | Avatar image URL or initials | MEDIUM |
| `color_class` | `string` | CSS class for avatar background | LOW |
| `description` | `string` | Podcast description | MEDIUM |
| `categories` | `string[]` | Content categories (e.g., "財經", "投資", "科技") | LOW |
| `rating` | `number` | Average rating (1-5) | LOW |
| `subscriber_count` | `number` | Number of subscribers | LOW |

**Current Workaround:** Using mock data in `src/data/mockData.ts` - `ACTIVE_CHANNELS`

---

## Missing Data Fields (Graph/Stock Related)

### GraphNode/StockNodeData Fields

| Field | Description | Status |
|-------|-------------|--------|
| `history: number[]` | Normalized sparkline data (0-1) | Use `generateSparklineHistory()` |
| `layerLabel: string` | Layer label for DAG visualization | Derive from visual endpoints |
| `rank: number` | Rank/order for DAG | Derive from position |
| `isRoot: boolean` | Root node indicator for tree | Derive from edges |
| `ownership: string` | Ownership percentage | May be on edges |
| `group: string` | Cluster group identifier | From cluster endpoint |
| `name: string` | Company name | Fetch from stock endpoint |
| `price: number` | Current stock price | Fetch from stock endpoint |
| `changePct: number` | Price change percentage | Fetch from stock endpoint |

---

## Visual Graph Endpoints Schema Gaps

The following endpoints have empty schemas (`schema: {}`) in OpenAPI:

- `GET /api/visuals/supply-chain`
- `GET /api/visuals/ownership`
- `GET /api/visuals/cluster`
- `GET /api/visuals/interactive-models`
- `GET /api/stocks/{ticker}/basic`

**Recommendation:** Backend should define response schemas for these endpoints.

---

## Priority Summary

### HIGH Priority (Required for TrendBrief MVP)
1. **`GET /api/episodes/recent`** - Critical for homepage feed
2. **Add `tags` field to Episode schema** - Needed for tag filtering/pages
3. **`GET /api/episodes/by-ticker/{ticker}`** - For stock detail pages
4. **`POST /api/auth/google`** - For User Authentication
5. **`GET /api/stocks` (Search)** - Critical for Watchlist/Search functionality
6. **User Preferences APIs** (Watchlist/Subs/Alerts) - For personalized experience

### MEDIUM Priority (Improves UX)
1. **`GET /api/tags`** - Tag listing and search
2. **`GET /api/episodes/by-tag/{tag}`** - Tag detail pages
3. **Add `summary_points` structured field to Episode** - Better summary display
4. **Add `avatar`, `description` to Podcast schema** - Podcaster pages
5. **`GET /api/stocks/{symbol}/history`** - For Sparklines

### LOW Priority (Nice to have)
1. **`GET /api/market/indices`** - Can use static data
2. **Add `is_hot`, `rating` fields** - Enhancement only
3. **Define schemas for visual endpoints** - Existing code handles it

---

## Current Workarounds Summary

| Feature | Workaround |
|---------|------------|
| Recent Episodes | `getAllRecentEpisodes()` helper fetches from all podcasts |
| Episodes by Ticker | Frontend filters mock data by highlights |
| Tags | Extracted from episode mock data |
| Episodes by Tag | Frontend filters by tag |
| Market Indices | Static data in `src/data/market.ts` |
| Podcaster Details | Mock data in `src/data/mockData.ts` |
| Auth | None (Dummy UI) |
| Stock Search | Frontend filters `MOCK_STOCKS` locally |
| Watchlist/Subs | LocalStorage (`useAppStore` persist) |
| Sparklines | Random generated data |

---

## Migration Notes

- All missing endpoints fall back to mock data via `fetchWithFallback()`
- Podcast APIs are now integrated but homepage still uses mock data for speed
- Consider implementing `/api/episodes/recent` for production use
- Tags system needs backend support or consistent Episode schema updates
