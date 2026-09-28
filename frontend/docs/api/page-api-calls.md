# Page API Calls Documentation

> **Historical snapshot.** This document records earlier plans or implementation details.
> Routes, API gaps, and environment instructions below may be stale. For current
> frontend guidance, start with the [frontend docs index](../README.md).

This document lists all API calls made by each page in the frontend application, along with their definitions and locations in the codebase.

## Table of Contents

1. [Main Page (Landing)](#1-main-page-landing)
2. [Stock Page (`/stock/:ticker`)](#2-stock-page-stockticker)
3. [News Page (`/news/:id`)](#3-news-page-newsid)
4. [Podcaster Page (`/podcaster/:id`)](#4-podcaster-page-podcasterid)

---

## 1. Main Page (Landing)

**Route:** `/`  
**Component:** `src/pages/Landing.tsx`

### API Calls

#### 1.1 `getRecentEpisodes()`

- **Purpose:** Fetch recent episodes across all podcasts for the main feed
- **Called in:** `src/pages/Landing.tsx` (lines 86-90)
- **Definition:** `src/services/api/index.ts` (lines 791-803)
- **Endpoint:** `GET /api/episodes/recent`
- **Parameters:**
  - `limit`: 50 (maximum number of episodes)
- **Usage:**
```82:90:src/pages/Landing.tsx
  useEffect(() => {
    const fetchEpisodes = async () => {
      setLoading(true);
      try {
        const apiEpisodes = await fetchWithFallback(
          () => getRecentEpisodes({ limit: 50 }),
          [],
          'getRecentEpisodes'
        );
```

#### 1.2 `getTopMovers()`

- **Purpose:** Fetch top moving stocks for the Popular Tickers widget
- **Called in:** `src/components/home/DashboardWidgets.tsx` (lines 144-148) via `PopularTickersWidget` component
- **Definition:** `src/services/api/index.ts` (lines 775-782)
- **Endpoint:** `GET /api/top-movers`
- **Parameters:**
  - `limit`: 10
- **Usage:**
```140:148:src/components/home/DashboardWidgets.tsx
    const fetchStocks = async () => {
      setLoading(true);
      try {
        const topMovers = await fetchWithFallback(
          () => getTopMovers(10),
          [],
          'getTopMovers'
        );
        setStocks(topMovers);
```

#### 1.3 `getSortedPodcasts()`

- **Purpose:** Fetch sorted list of podcasts for the Active Channels widget
- **Called in:** `src/components/home/DashboardWidgets.tsx` (lines 232-236) via `ActiveChannelsWidget` component
- **Definition:** `src/services/api/index.ts` (lines 602-616)
- **Endpoint:** `GET /api/podcast`
- **Parameters:**
  - `limit`: 10
  - `sortBy`: 'updated_at'
  - `order`: 'desc'
- **Usage:**
```228:236:src/components/home/DashboardWidgets.tsx
    const fetchPodcasts = async () => {
      setLoading(true);
      try {
        const podcastList = await fetchWithFallback(
          () => getSortedPodcasts({ limit: 10, sortBy: 'updated_at', order: 'desc' }),
          [],
          'getSortedPodcasts'
        );
```

---

## 2. Stock Page (`/stock/:ticker`)

**Route:** `/stock/:ticker`  
**Component:** `src/pages/StockDashboard.tsx`

### API Calls

#### 2.1 `getStockByTicker()`

- **Purpose:** Fetch detailed stock information including price, change, and company details
- **Called in:** `src/pages/StockDashboard.tsx` (lines 76-80) via `StockHeaderCard` component
- **Definition:** `src/services/api/index.ts` (lines 188-194)
- **Endpoint:** `GET /api/stocks/:ticker`
- **Parameters:**
  - `ticker`: Stock ticker symbol from URL parameter
  - `timeframe`: Optional (not used in this page)
- **Usage:**
```73:80:src/pages/StockDashboard.tsx
  const fetchStockData = useCallback(async (ticker: string) => {
    setIsLoading(true);
    try {
      const data = await fetchWithFallback(
        () => getStockByTicker(ticker),
        mockCompanyDetails[ticker] || mockCompanyDetails['TSLA'],
        `GET /api/stocks/${ticker}`
      );
```

#### 2.2 `getEpisodesByTicker()`

- **Purpose:** Fetch all episodes that mention the specific stock ticker
- **Called in:** `src/pages/StockDashboard.tsx` (lines 202-206)
- **Definition:** `src/services/api/index.ts` (lines 673-683)
- **Endpoint:** `GET /api/episodes/by-ticker/:ticker`
- **Parameters:**
  - `ticker`: Stock ticker symbol from URL parameter
  - `limit`: 50 (maximum number of episodes)
- **Usage:**
```198:206:src/pages/StockDashboard.tsx
  useEffect(() => {
    const fetchEpisodes = async () => {
      setEpisodesLoading(true);
      try {
        const apiEpisodes = await fetchWithFallback(
          () => getEpisodesByTicker(symbol, { limit: 50 }),
          [],
          `getEpisodesByTicker(${symbol})`
        );
```

### Additional Features

- **WebSocket Connection:** The page also establishes a WebSocket connection for real-time price updates via `priceWebSocketClient` (lines 97-126). This is not a REST API call but provides real-time data updates.

---

## 3. News Page (`/news/:id`)

**Route:** `/news/:id`  
**Component:** `src/pages/NewsPage.tsx`

### API Calls

#### 3.1 `getInteractiveModels()`

- **Purpose:** Fetch interactive model data for the news/article page
- **Called in:** `src/pages/NewsPage.tsx` (lines 293-297)
- **Definition:** `src/services/api/index.ts` (lines 502-514)
- **Endpoint:** `GET /api/visuals/interactive-models`
- **Parameters:** None
- **Usage:**
```288:297:src/pages/NewsPage.tsx
  useEffect(() => {
    if (!id) return;

    const fetchModelData = async () => {
      try {
        const models = await fetchWithFallback(
          () => getInteractiveModels(),
          Object.values(INTERACTIVE_MODELS_DATA),
          'getInteractiveModels'
        );
```

#### 3.2 `getStockByTicker()` (Multiple Calls)

- **Purpose:** Enrich ticker data with real stock information for each ticker mentioned in the article
- **Called in:** `src/pages/NewsPage.tsx` (lines 347-351) - called multiple times in a loop
- **Definition:** `src/services/api/index.ts` (lines 188-194)
- **Endpoint:** `GET /api/stocks/:ticker`
- **Parameters:**
  - `ticker`: Stock ticker symbol (one call per ticker)
- **Usage:**
```342:351:src/pages/NewsPage.tsx
    const enrichTickers = async () => {
      if (tickersToEnrich.length === 0) return;

      const tickerPromises = tickersToEnrich.map(async (ticker: InteractiveEntity) => {
        try {
          const stock = await fetchWithFallback(
            () => getStockByTicker(ticker.symbol),
            null,
            `getStockByTicker(${ticker.symbol})`
          );
```

**Note:** This API is called once for each ticker mentioned in the article/model, so the number of calls depends on the number of tickers in the content.

---

## 4. Podcaster Page (`/podcaster/:id`)

**Route:** `/podcaster/:id`  
**Component:** `src/pages/PodcasterPage.tsx`

### API Calls

#### 4.1 `getPodcastByName()`

- **Purpose:** Fetch podcast metadata (name, episode count, etc.)
- **Called in:** `src/pages/PodcasterPage.tsx` (lines 81-85)
- **Definition:** `src/services/api/index.ts` (lines 622-625)
- **Endpoint:** `GET /api/podcast/:podcastName`
- **Parameters:**
  - `podcastName`: Podcast name from URL parameter (URL encoded)
- **Usage:**
```74:85:src/pages/PodcasterPage.tsx
    const fetchPodcastData = async () => {
      if (!podcasterName) return;
      
      setLoading(true);
      try {
        // Fetch podcast metadata
        const podcastData = await fetchWithFallback(
          () => getPodcastByName(podcasterName),
          null,
          `getPodcastByName(${podcasterName})`
        );
```

#### 4.2 `getPodcastEpisodes()`

- **Purpose:** Fetch all episodes for a specific podcast
- **Called in:** `src/pages/PodcasterPage.tsx` (lines 89-93)
- **Definition:** `src/services/api/index.ts` (lines 632-652)
- **Endpoint:** `GET /api/podcast/:podcastName/episodes`
- **Parameters:**
  - `podcastName`: Podcast name from URL parameter (URL encoded)
  - `limit`: 100
  - `sortBy`: 'created_time'
  - `order`: 'desc'
- **Usage:**
```88:93:src/pages/PodcasterPage.tsx
        // Fetch episodes
        const apiEpisodes = await fetchWithFallback(
          () => getPodcastEpisodes(podcasterName, { limit: 100, sortBy: 'created_time', order: 'desc' }),
          [],
          `getPodcastEpisodes(${podcasterName})`
        );
```

---

## API Function Definitions Location

All API functions are defined in:
- **File:** `src/services/api/index.ts`
- **Base Client:** `src/services/api/client.ts` (contains the `apiClient` instance)

### Common Patterns

All API calls in the pages use the `fetchWithFallback()` wrapper function from `src/services/api/migration.ts`, which:
1. Attempts to call the API function
2. Falls back to mock/placeholder data if the API call fails
3. Logs errors for debugging

### API Client Configuration

The API client is configured in:
- **File:** `src/services/api/client.ts`
- Uses axios with base URL configuration
- Handles authentication headers
- Manages request/response interceptors

---

## Summary Table

| Page | Route | API Calls | Total Calls |
|------|-------|-----------|-------------|
| Main Page | `/` | `getRecentEpisodes()`, `getTopMovers()`, `getSortedPodcasts()` | 3 |
| Stock Page | `/stock/:ticker` | `getStockByTicker()`, `getEpisodesByTicker()` | 2 |
| News Page | `/news/:id` | `getInteractiveModels()`, `getStockByTicker()` (N times) | 1 + N* |
| Podcaster Page | `/podcaster/:id` | `getPodcastByName()`, `getPodcastEpisodes()` | 2 |

\* N = number of tickers mentioned in the article/model

---

## Notes

1. **WebSocket Usage:** The Stock Page uses WebSocket for real-time price updates, which is not a REST API call but provides continuous data streaming.

2. **Error Handling:** All API calls use the `fetchWithFallback()` wrapper which provides graceful degradation to mock data when APIs fail.

3. **Caching:** The API client may implement caching strategies, but this is handled at the client level in `src/services/api/client.ts`.

4. **Authentication:** API calls may include authentication headers if the user is logged in. Check `src/services/api/client.ts` for authentication configuration.

