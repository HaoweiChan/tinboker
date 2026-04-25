# Graph Report - .  (2026-04-25)

## Corpus Check
- 293 files · ~165,058 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1783 nodes · 3925 edges · 57 communities detected
- Extraction: 59% EXTRACTED · 41% INFERRED · 0% AMBIGUOUS · INFERRED: 1626 edges (avg confidence: 0.5)
- Token cost: 0 input · 0 output

## God Nodes (most connected - your core abstractions)
1. `FirestoreService` - 78 edges
2. `StockService` - 69 edges
3. `SearchResultItem` - 63 edges
4. `PodcastService` - 62 edges
5. `MassiveAPIService` - 58 edges
6. `FinMindAPIService` - 50 edges
7. `UserResponse` - 48 edges
8. `CompanyDetail` - 45 edges
9. `StockPriceHistory` - 45 edges
10. `Stock` - 45 edges

## Surprising Connections (you probably didn't know these)
- `Unified search endpoint.     Returns results for stocks, podcasts, episodes, and` --rationale_for--> `search()`  [EXTRACTED]
  backend/src/routers/search.py → frontend/src/services/api/search.ts
- `WebSocket subscriber manager for Redis pub/sub` --uses--> `RedisClient`  [INFERRED]
  backend/src/services/websocket_subscriber.py → backend/src/cache/redis_client.py
- `Manages WebSocket subscription to Redis channels` --uses--> `RedisClient`  [INFERRED]
  backend/src/services/websocket_subscriber.py → backend/src/cache/redis_client.py
- `Subscribe to stock updates for a ticker.          Args:             ticker: Stoc` --uses--> `RedisClient`  [INFERRED]
  backend/src/services/websocket_subscriber.py → backend/src/cache/redis_client.py
- `Unsubscribe from stock updates for a ticker.          Args:             ticker:` --uses--> `RedisClient`  [INFERRED]
  backend/src/services/websocket_subscriber.py → backend/src/cache/redis_client.py

## Communities

### Community 0 - "React App Shell"
Cohesion: 0.01
Nodes (21): fetchWithFallback(), fetchWithFallbackAndErrorHandler(), isMockModeForced(), setLegendContent(), updateLegend(), getTicker(), handleNavigate(), handleKeyDown() (+13 more)

### Community 1 - "Podcast Episodes API"
Cohesion: 0.03
Nodes (113): get_episodes_by_ticker(), get_recent_episodes(), Episodes API router for cross-podcast episode queries, Get recent episodes across all podcasts, sorted by created_time descending, Get episodes that mention a specific stock ticker          Path params:     - ti, FirestoreService, Generic Firestore service for data access, Get Firestore client, optionally with custom database ID. (+105 more)

### Community 2 - "Massive API Data Service"
Cohesion: 0.02
Nodes (91): MassiveAPIService, Massive API service wrapper.  This module provides a wrapper around the Massive, Get latest ticker snapshot (real-time OHLCV).         Uses most recent day's dat, Get daily ticker summary (OHLC) for a specific date.                  Args:, Get income statements for a ticker.                  Args:             ticker: S, Get financial ratios for a ticker.                  Args:             ticker: St, Service wrapper for Massive API., Get top market movers.         Note: Massive API doesn't have a direct top mover (+83 more)

### Community 3 - "Company Data Service"
Cohesion: 0.04
Nodes (95): ABC, CompanyDataService, FinMindCompanyDataService, MockCompanyDataService, Abstract base class for company data services, Retrieve US stock list from FinMind REST API, Retrieve list of all companies as StockMetadataCollection, Retrieve aggregated list of Taiwan and US stocks from FinMind API (+87 more)

### Community 4 - "Data Collection Pipeline"
Cohesion: 0.03
Nodes (86): DataCollectionService, Fetch daily aggregates from FinMind. Supports timeframe and before (pagination), ChartDataPoint, CompanyDetail, add_price_history(), create_or_update_stock(), delete_stock(), get_all_stocks() (+78 more)

### Community 5 - "Auth & Dependencies"
Cohesion: 0.05
Nodes (103): AdminTokenData, Data stored in admin JWT token., get_current_user(), FastAPI dependencies for authentication and authorization, Get current authenticated user from JWT token          Usage:         @router.ge, BulkMarkReadResponse, MarkReadResponse, NotificationListResponse (+95 more)

### Community 6 - "Admin Analytics"
Cohesion: 0.06
Nodes (90): get_analytics_overview(), Admin Analytics API - Fetches analytics data from Cloudflare., Get analytics overview - currently returns placeholder data.     Real analytics, AdminAccess, create_admin_token(), get_admin_access(), _get_admin_password(), get_current_admin() (+82 more)

### Community 7 - "Graph Visualization Engine"
Cohesion: 0.09
Nodes (78): BaseModel, ConceptMetadata, Config, create_graph(), add_edge_to_graph(), add_node_to_graph(), create_graph(), delete_graph() (+70 more)

### Community 8 - "Analytics Tracking"
Cohesion: 0.04
Nodes (43): ClickEvent, process_click_event(), Track user clicks for trending analytics.     Fire-and-forget style., Increment click counters in Redis.     We use Sorted Sets (ZSET) for easy rankin, track_click(), create_jwt_token(), get_current_user(), google_login() (+35 more)

### Community 9 - "Admin UI Pages"
Cohesion: 0.06
Nodes (19): adminAuthConfig(), adminLogin(), adminLogout(), bulkImportCSV(), bulkImportJSON(), clearAdminToken(), createTranslation(), deleteTranslation() (+11 more)

### Community 10 - "Notifications System"
Cohesion: 0.11
Nodes (45): Config, cleanup_old_notifications(), create_notification(), delete_notification(), _dict_to_notification_response(), _firestore_timestamp_to_datetime(), _get_firestore_service(), get_notification_by_id() (+37 more)

### Community 11 - "Database Index Operations"
Cohesion: 0.05
Nodes (6): getAllRecentEpisodes(), getClusterVisual(), getOwnershipVisual(), getSortedPodcasts(), getSupplyChainVisual(), processGraphDataResponse()

### Community 12 - "Admin System Management"
Cohesion: 0.1
Nodes (31): Admin API endpoints for system status and monitoring., Get system status for admin dashboard.      Returns health metrics for:     - Ba, system_status(), adminAuthConfig(), BackendStatus, getSystemStatus(), HealthCheckResponse, PostgresStatus (+23 more)

### Community 13 - "App Configuration"
Cohesion: 0.07
Nodes (17): BaseSettings, GCPSecretManagerSource, Custom Pydantic settings source that loads secrets from Google Cloud Secret Mana, Configuration management for Graphfolio Backend.  This module handles: - System/, Parse CORS origins from string or list, Get PostgreSQL connection string from DATABASE_URL or individual settings., PostgreSQL URL for recommendation/podcast_db. Uses POSTGRES_* when set; host/por, Get Redis connection string from REDIS_URL or individual settings. (+9 more)

### Community 14 - "CDN Cache Layer"
Cohesion: 0.09
Nodes (30): build_cache_header(), CacheProfile, cdn_cache_news(), cdn_cache_podcast(), cdn_cache_stock(), cdn_cache_trending(), cdn_cached(), cdn_no_cache() (+22 more)

### Community 15 - "Stock Recommendations"
Cohesion: 0.13
Nodes (16): _default_start_end(), _parse_date(), Recommendation service: read-only access to ticker recommendations (podcast_db)., Return most-discussed tickers in the last `days` days., Default timeframe: today − 7 days, today., Service for ticker/podcaster recommendations and buzz., Return recommendations for the ticker. Default: last 7 days., Return recommendations from the podcaster. Default: last 7 days. Optional podcas (+8 more)

### Community 16 - "Redis Cache Client"
Cohesion: 0.15
Nodes (17): cache_delete(), cache_delete_pattern(), cache_get(), cache_set(), close(), close_all(), close_pubsub(), create_subscriber() (+9 more)

### Community 17 - "Industry Color Utils"
Cohesion: 0.11
Nodes (5): getIndustryColor(), hashString(), getBubbleVisuals(), hexToRgb(), toRgba()

### Community 18 - "Live Price WebSocket"
Cohesion: 0.2
Nodes (2): getWebSocketURL(), PriceWebSocketClient

### Community 19 - "UI Icon Library"
Cohesion: 0.12
Nodes (0): 

### Community 20 - "Recommendation DB Queries"
Cohesion: 0.23
Nodes (11): _format_iso(), get_by_podcaster(), get_by_ticker(), get_most_discussed(), Read-only DB queries for ticker recommendations (podcast_db). Assumes table tick, Return most-discussed tickers in the date range as TickerBuzz:     ticker, count, Map a DB row to frontend TickerRecommendation shape., Format timestamp/date to ISO string. (+3 more)

### Community 21 - "PostgreSQL Setup"
Cohesion: 0.23
Nodes (11): create_all_tables(), drop_all_tables(), get_database_url(), get_session(), init_engine(), PostgreSQL database connection and session management using SQLAlchemy., Create all database tables based on SQLAlchemy models.          Note: For produc, Drop all database tables.          WARNING: This will delete all data! Use only (+3 more)

### Community 22 - "Recommendation DB Pool"
Cohesion: 0.18
Nodes (11): close_pool(), get_connection(), get_pool(), init_pool(), is_available(), PostgreSQL connection for recommendation/podcast_db. Data is prepared elsewhere;, Initialize the recommendation Postgres connection pool., Close the recommendation Postgres connection pool. (+3 more)

### Community 23 - "Podcast Player Events"
Cohesion: 0.23
Nodes (1): PlayerBroadcastService

### Community 24 - "SQLite DB Client"
Cohesion: 0.29
Nodes (9): ensure_db_initialized(), get_connection(), get_db_path(), init_db(), Database initialization and connection management for SQLite, Get database file path, creating directory if needed, Ensure database is initialized (call on startup)., Get SQLite database connection (+1 more)

### Community 25 - "Stock Channels API"
Cohesion: 0.2
Nodes (9): all_stocks_channel(), Redis channel name utilities for pub/sub, Get Redis channel name for stock price updates, Get Redis channel name for stock news updates, Get Redis channel name for all stocks updates, Get Redis channel name for stock OHLCV updates, stock_news_channel(), stock_ohlcv_channel() (+1 more)

### Community 26 - "Blob Storage Client"
Cohesion: 0.44
Nodes (8): _blob_path(), _build_client(), _ensure_bucket(), _get_client(), get_ticker_content(), list_content(), Create a storage client, optionally using a JSON key from env., _signed_url()

### Community 27 - "Notification UI"
Cohesion: 0.29
Nodes (2): formatTimeAgo(), mapToDisplay()

### Community 28 - "DB Init Script"
Cohesion: 0.5
Nodes (3): main(), Database initialization script. Creates all tables defined in the models., Initialize database and create all tables.

### Community 29 - "OpenAPI Export Script"
Cohesion: 0.5
Nodes (3): dump_openapi_to_file(), Utility script to dump OpenAPI schema to YAML file.  Usage:     python -m src.ut, Dump OpenAPI schema to YAML file

### Community 30 - "Graph Thumbnail Gen"
Cohesion: 0.67
Nodes (0): 

### Community 31 - "Animated Background"
Cohesion: 0.67
Nodes (0): 

### Community 32 - "Company Router"
Cohesion: 1.0
Nodes (1): Company/stock router (for backward compatibility) Redirects to stock router

### Community 33 - "WebSocket Router"
Cohesion: 1.0
Nodes (1): WebSocket router (for backward compatibility) Stock WebSocket functionality is i

### Community 34 - "DB Migration Script"
Cohesion: 1.0
Nodes (1): Database migration script for Render deployment

### Community 35 - "Cache Configuration"
Cohesion: 1.0
Nodes (1): Cache configuration - TTL values and key prefixes

### Community 36 - "Graph Layout Utils"
Cohesion: 1.0
Nodes (0): 

### Community 37 - "ELK Layout Algorithm"
Cohesion: 1.0
Nodes (0): 

### Community 38 - "Summary Parser"
Cohesion: 1.0
Nodes (0): 

### Community 39 - "UI Control Button"
Cohesion: 1.0
Nodes (0): 

### Community 40 - "Redis Rationale (1)"
Cohesion: 1.0
Nodes (1): Initialize Redis connection with retry logic.                  Args:

### Community 41 - "Redis Rationale (2)"
Cohesion: 1.0
Nodes (1): Get Redis client instance

### Community 42 - "Redis Rationale (3)"
Cohesion: 1.0
Nodes (1): Close Redis connection

### Community 43 - "Redis Rationale (4)"
Cohesion: 1.0
Nodes (1): Check if Redis is available

### Community 44 - "Redis Rationale (5)"
Cohesion: 1.0
Nodes (1): Get separate Redis client for pub/sub (recommended)

### Community 45 - "Redis Rationale (6)"
Cohesion: 1.0
Nodes (1): Publish a message to a Redis channel.                  Args:             channel

### Community 46 - "Redis Rationale (7)"
Cohesion: 1.0
Nodes (1): Create a Redis pub/sub subscriber.                  Returns:             PubSub

### Community 47 - "Redis Rationale (8)"
Cohesion: 1.0
Nodes (1): Subscribe to a Redis channel

### Community 48 - "Redis Rationale (9)"
Cohesion: 1.0
Nodes (1): Unsubscribe from a Redis channel

### Community 49 - "Redis Rationale (10)"
Cohesion: 1.0
Nodes (1): Close pub/sub connection

### Community 50 - "Redis Rationale (11)"
Cohesion: 1.0
Nodes (1): Close all Redis connections

### Community 51 - "Massive WS Rationale (1)"
Cohesion: 1.0
Nodes (1): Check if WebSocket is connected.

### Community 52 - "Massive WS Rationale (2)"
Cohesion: 1.0
Nodes (1): Get current subscriptions.

### Community 53 - "PWA Types"
Cohesion: 1.0
Nodes (0): 

### Community 54 - "Technical Indicators Types"
Cohesion: 1.0
Nodes (0): 

### Community 55 - "Global Types"
Cohesion: 1.0
Nodes (0): 

### Community 56 - "Market Module"
Cohesion: 1.0
Nodes (0): 

## Knowledge Gaps
- **230 isolated node(s):** `Custom Pydantic settings source that loads secrets from Google Cloud Secret Mana`, `Parse admin emails from comma-separated string or list`, `Parse JWT expiration hours, handling empty strings`, `Enforce PostgreSQL usage in production environment`, `Parse CORS origins from string or list` (+225 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Company Router`** (2 nodes): `company.py`, `Company/stock router (for backward compatibility) Redirects to stock router`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `WebSocket Router`** (2 nodes): `websocket.py`, `WebSocket router (for backward compatibility) Stock WebSocket functionality is i`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `DB Migration Script`** (2 nodes): `migrate.py`, `Database migration script for Render deployment`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Cache Configuration`** (2 nodes): `cache_config.py`, `Cache configuration - TTL values and key prefixes`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Graph Layout Utils`** (2 nodes): `graphLayout.ts`, `calculateHierarchicalLayout()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `ELK Layout Algorithm`** (2 nodes): `elkLayout.ts`, `calculateELKLayout()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Summary Parser`** (2 nodes): `summaryParser.ts`, `parseSummaryTopics()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `UI Control Button`** (2 nodes): `ControlButton.tsx`, `ControlButton()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Redis Rationale (1)`** (1 nodes): `Initialize Redis connection with retry logic.                  Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Redis Rationale (2)`** (1 nodes): `Get Redis client instance`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Redis Rationale (3)`** (1 nodes): `Close Redis connection`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Redis Rationale (4)`** (1 nodes): `Check if Redis is available`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Redis Rationale (5)`** (1 nodes): `Get separate Redis client for pub/sub (recommended)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Redis Rationale (6)`** (1 nodes): `Publish a message to a Redis channel.                  Args:             channel`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Redis Rationale (7)`** (1 nodes): `Create a Redis pub/sub subscriber.                  Returns:             PubSub`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Redis Rationale (8)`** (1 nodes): `Subscribe to a Redis channel`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Redis Rationale (9)`** (1 nodes): `Unsubscribe from a Redis channel`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Redis Rationale (10)`** (1 nodes): `Close pub/sub connection`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Redis Rationale (11)`** (1 nodes): `Close all Redis connections`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Massive WS Rationale (1)`** (1 nodes): `Check if WebSocket is connected.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Massive WS Rationale (2)`** (1 nodes): `Get current subscriptions.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `PWA Types`** (1 nodes): `pwa.d.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Technical Indicators Types`** (1 nodes): `technicalindicators.d.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Global Types`** (1 nodes): `global.d.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Market Module`** (1 nodes): `market.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `SearchResultItem` connect `Podcast Episodes API` to `Data Collection Pipeline`, `Graph Visualization Engine`?**
  _High betweenness centrality (0.096) - this node is a cross-community bridge._
- **Why does `RedisClient` connect `Massive API Data Service` to `Data Collection Pipeline`, `Graph Visualization Engine`, `Analytics Tracking`, `Admin System Management`, `Redis Cache Client`?**
  _High betweenness centrality (0.077) - this node is a cross-community bridge._
- **Why does `Background workers for Graphfolio Backend` connect `Graph Visualization Engine` to `Podcast Episodes API`, `Massive API Data Service`, `Data Collection Pipeline`, `Auth & Dependencies`, `CDN Cache Layer`?**
  _High betweenness centrality (0.075) - this node is a cross-community bridge._
- **Are the 65 inferred relationships involving `FirestoreService` (e.g. with `User database operations using Firestore` and `Get or create FirestoreService instance`) actually correct?**
  _`FirestoreService` has 65 INFERRED edges - model-reasoned connections that need verification._
- **Are the 54 inferred relationships involving `StockService` (e.g. with `Get sorted stocks list with optional search          Query params:     - sort_by` and `Get stock by ticker          Returns full stock information including chart data`) actually correct?**
  _`StockService` has 54 INFERRED edges - model-reasoned connections that need verification._
- **Are the 61 inferred relationships involving `SearchResultItem` (e.g. with `Unified search endpoint.     Returns results for stocks, podcasts, episodes, and` and `Fast typeahead suggestions.     Returns instant suggestions for autocomplete. Ta`) actually correct?**
  _`SearchResultItem` has 61 INFERRED edges - model-reasoned connections that need verification._
- **Are the 37 inferred relationships involving `PodcastService` (e.g. with `Get sorted podcasts list          Query params:     - sort_by: Sort field (name,` and `Get podcast by name          Returns podcast metadata including episode count an`) actually correct?**
  _`PodcastService` has 37 INFERRED edges - model-reasoned connections that need verification._