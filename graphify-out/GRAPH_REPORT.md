# Graph Report - .  (2026-05-13)

## Corpus Check
- 228 files · ~99,999 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 2802 nodes · 4985 edges · 249 communities detected
- Extraction: 65% EXTRACTED · 35% INFERRED · 0% AMBIGUOUS · INFERRED: 1736 edges (avg confidence: 0.51)
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
9. `DataCollectionService` - 43 edges
10. `GraphData` - 40 edges

## Surprising Connections (you probably didn't know these)
- `Google OAuth to JWT Auth Flow` --references--> `create_jwt_token()`  [EXTRACTED]
  frontend/docs/google-login-complete-reference.md → backend/src/utils/auth.py
- `Gitflow Branching Strategy` --semantically_similar_to--> `Backend CI/CD Pipeline`  [INFERRED] [semantically similar]
  frontend/docs/process/branching-strategy.md → backend/AGENTS.md
- `Spec Req: JWT Token 24h Expiry Validation` --semantically_similar_to--> `JWT Utilities (src/utils/auth.py)`  [INFERRED] [semantically similar]
  openspecs/admin-auth/spec.md → backend/docs/guides/google-oauth-implementation.md
- `Spec Req: Cache-Control Headers for Episode Endpoints` --semantically_similar_to--> `TTL Strategy Configuration (CACHE_TTL)`  [INFERRED] [semantically similar]
  openspecs/backend-caching/spec.md → backend/docs/infrastructure/redis-setup.md
- `Redis Sorted Set for Click Trending` --semantically_similar_to--> `Redis Rate Limiting Pattern`  [INFERRED] [semantically similar]
  openspecs/search-api/spec.md → backend/docs/infrastructure/redis-setup.md

## Hyperedges (group relationships)
- **Marp Slide Render Pipeline** — util_marp_parser, util_marp_post_processor, marp_core_lib [INFERRED 0.92]
- **Auth and User Session UI Cluster** — component_user_menu, component_login_button, store_use_app_store [EXTRACTED 0.95]
- **Search Interaction Feature Cluster** — component_search_dropdown, hook_use_search_history, hook_use_adaptive_debounce [EXTRACTED 0.93]
- **Podcast Timestamp Playback Pattern** — TickerInsightCard_component, PodcasterPicksList_component, usePlayerStore_store [EXTRACTED 0.95]
- **Stock Event Visualization Subsystem** — EventDetailsGrid_component, EventTimeline_component, EventIconsOverlay_component [EXTRACTED 0.90]
- **Responsive Navigation Shell** — AppLayout_component, Sidebar_component, BottomTabs_component [EXTRACTED 0.95]
- **Sentiment Display Pipeline** — sentiment_sentimenttype, sentiment_normalizesentiment, sentiment_getsentimentdisplay, sentimentchip_sentimentchip [EXTRACTED 0.95]
- **Global Player + Spotify Embed + Player Store System** — globalplayer_globalplayer, spotifyembed_spotifyembed, useplayerstore_playerstore [EXTRACTED 0.98]
- **HomeRail Composite Widget** — homerail_todaypulse, homerail_toptickers, homerail_toppodcasters [EXTRACTED 0.97]
- **Pages using fetchWithFallback + EpisodeCardV2** — tagpage, podcasterpage, episodedetail, api_migration, episodecardv2 [EXTRACTED 0.95]
- **StockDashboard real-time data pipeline** — stockheadercard, pricewssclient, type_realtimeprice, tradingviewchart [EXTRACTED 0.95]
- **Industry Visualization backed by Mock Sector Data (BUG-2)** — industryanalysis, sectordata_mock, bug2_stub_sectordata [EXTRACTED 0.90]
- **All frontend API modules share single axios client singleton** — api_content, api_podcasts, api_stocks, api_client [EXTRACTED 1.00]
- **Stock API to Zod Schema to parseResponse validation pipeline** — fn_getStockByTicker, schema_CompanyDetailSchema, schema_parseResponse [EXTRACTED 1.00]
- **All backend test suites share temp SQLite via conftest fixtures** — conftest_fixtures, test_graph_service, test_news_service, test_stock_service [EXTRACTED 1.00]
- **Stock Translation Data Pipeline** — migrate_ticker_json_script, seed_translations_script, cleanup_translations_script, external_TranslationService, models_StockTranslation [INFERRED 0.90]
- **Firestore Podcast Upload Pipeline** — upload_to_firebase_FirebaseService, podcast_models_PodcastEpisode, external_FirestoreDB [EXTRACTED 0.95]
- **Search Index Build Pipeline** — routers_search_init_search_index, routers_search_build_search_index, external_SuggestionIndex, external_StockService, external_PodcastService [EXTRACTED 0.95]
- **Podcast Episode Mutation Pipeline** — podcast_save_modified_summary, gcs_upload_content, podcast_invalidate_cache [EXTRACTED 0.95]
- **Firestore Dict to GCS Enrichment to Episode Model Pipeline** — episode_transformer_EpisodeTransformer, episode_transformer_enrich_with_content, episode_transformer_to_episode [EXTRACTED 0.95]
- **TW/US Stock Routing Pattern** — data_collection_collect_stock_data, data_collection_collect_finmind, data_collection_collect_massive [EXTRACTED 0.95]
- **Production Reliability Stack (Systemd + GitHub Actions + UptimeRobot)** — prod_reliability_systemd, prod_reliability_github_actions, prod_reliability_uptimerobot [EXTRACTED 0.95]
- **Real-Time Stock Data Pipeline** — massive_api_websocket, backend_readme_websocket, realtime_stock_reqs_websocket_arch [INFERRED 0.85]
- **Frontend Mock Fallback Pattern** — page_api_calls_fetchwithfallback, api_gaps_missing_recent_episodes, be_fe_comparison_inefficient_recent [INFERRED 0.88]
- **WebSocket Real-Time Price Pipeline: Publisher, Redis Pub/Sub, Subscriber** — ws_redis_pubsub_stock_publisher, websocket_testing_redis_channels, ws_redis_pubsub_ws_subscriber [EXTRACTED 0.95]
- **Admin Translation System: Auth + Dashboard + Translation Management** — spec_admin_auth, spec_admin_dashboard, spec_stock_translations [EXTRACTED 0.90]
- **Stock Data Cache-Aside Flow: StockService, RedisClient, MassiveAPIService** — stock_router_stock_service, cache_debugging_redis_client, stock_router_massive_api_service [INFERRED 0.85]
- **PWA Installation Requirements: Manifest + Service Worker + Icons** — pwa_manifest_spec, pwa_service_worker, pwa_icons_spec [EXTRACTED 0.95]
- **Multi-Environment Infrastructure Stack** — infra_caddy, infra_docker, infra_shared_redis, infra_multi_env [EXTRACTED 0.90]
- **Episode Card Design System: Visuals + Backend Data + UI/UX** — visuals_spec, backenddata_key_insights, uiux_modern_saas_aesthetic, visuals_key_insights_rendering [INFERRED 0.82]
- **TinBoker PWA Standard Icon Size Variants** — pwa_icon_72, pwa_icon_96, pwa_icon_128, pwa_icon_144, pwa_icon_152, pwa_icon_512 [INFERRED 0.95]
- **TinBoker PWA Maskable Icon Size Variants** — pwa_maskable_192, pwa_maskable_512 [EXTRACTED 1.00]
- **All TinBoker PWA Icons** — pwa_icon_72, pwa_icon_96, pwa_icon_128, pwa_icon_144, pwa_icon_152, pwa_icon_512, pwa_maskable_192, pwa_maskable_512 [EXTRACTED 1.00]

## Communities

### Community 0 - "Frontend App + Pages"
Cohesion: 0.01
Nodes (74): API Migration / fetchWithFallback, apiEpisodeToCardV2 Adapter, AppLayout(), pageTitle(), AppLogo Component, BracketMark(), authApi Service, BUG-2: Stub Sector Data (+66 more)

### Community 1 - "Company Data Service"
Cohesion: 0.02
Nodes (132): ABC, CompanyDataService, FinMindCompanyDataService, MockCompanyDataService, Abstract base class for company data services, Abstract base class for company data services, Retrieve US stock list from FinMind REST API, Retrieve aggregated list of Taiwan and US stocks from FinMind API (+124 more)

### Community 2 - "Episode Transformer"
Cohesion: 0.02
Nodes (133): datetime_to_timestamp_ms(), EpisodeTransformer, extract_tags_from_text(), Episode data transformation: Firestore dicts -> Episode models with GCS enrichme, Converts raw Firestore dicts to Episode models, optionally enriching with GCS co, Fetch missing content fields from GCS/HTTP URLs in parallel, Convert datetime (or ISO string) to Unix timestamp in milliseconds, Convert a Firestore episode dict to an Episode model (+125 more)

### Community 3 - "Admin Analytics API"
Cohesion: 0.04
Nodes (117): get_analytics_overview(), Admin Analytics API - Fetches analytics data from Cloudflare., Get analytics overview - currently returns placeholder data.     Real analytics, AdminAccess, create_admin_token(), get_admin_access(), _get_admin_password(), get_current_admin() (+109 more)

### Community 4 - "Cloudflare Middleware"
Cohesion: 0.03
Nodes (77): BaseHTTPMiddleware, _build_cloudflare_networks(), CloudflareMiddleware, is_cloudflare_ip(), Cloudflare middleware for trusted proxy handling. Extracts real client IP from C, Build list of Cloudflare IP networks for validation., Check if an IP address belongs to Cloudflare., Middleware to handle requests proxied through Cloudflare.          When a reques (+69 more)

### Community 5 - "Admin Auth + Dependencies"
Cohesion: 0.05
Nodes (103): AdminTokenData, Data stored in admin JWT token., get_current_user(), FastAPI dependencies for authentication and authorization, Get current authenticated user from JWT token          Usage:         @router.ge, BulkMarkReadResponse, MarkReadResponse, NotificationListResponse (+95 more)

### Community 6 - "Graph Models + DB"
Cohesion: 0.09
Nodes (79): BaseModel, ConceptMetadata, Config, create_graph(), add_edge_to_graph(), add_node_to_graph(), create_graph(), delete_graph() (+71 more)

### Community 7 - "Stock Data Models"
Cohesion: 0.06
Nodes (52): Add stock to collection, ChartDataPoint, CompanyDetail, add_price_history(), create_or_update_stock(), delete_stock(), get_all_stocks(), get_latest_price() (+44 more)

### Community 8 - "Graph Service + Tests"
Cohesion: 0.04
Nodes (38): graph_db (backend SQLite ops), GraphService (backend), Integration tests for graph API endpoints, Test PUT /api/graphs/{graph_id}/edges/{edge_id}, Test DELETE /api/graphs/{graph_id}, Test DELETE /api/graphs/{graph_id}/nodes/{node_id}, Test DELETE /api/graphs/{graph_id}/edges/{edge_id}, Sample graph creation data (+30 more)

### Community 9 - "Analytics + Click Tracking"
Cohesion: 0.04
Nodes (24): ClickEvent, process_click_event(), Track user clicks for trending analytics.     Fire-and-forget style., Increment click counters in Redis.     We use Sorted Sets (ZSET) for easy rankin, track_click(), checkUrlAvailability(), createApiClient(), extractBranchFromPagesUrl() (+16 more)

### Community 10 - "Visual Graph Service"
Cohesion: 0.05
Nodes (43): _build_nodes(), get_cluster(), _get_cluster_structure(), get_interactive_models(), get_ownership(), _get_ownership_structure(), get_supply_chain(), _get_supply_chain_structure() (+35 more)

### Community 11 - "Admin Dashboard UI"
Cohesion: 0.06
Nodes (19): adminAuthConfig(), adminLogin(), adminLogout(), bulkImportCSV(), bulkImportJSON(), clearAdminToken(), createTranslation(), deleteTranslation() (+11 more)

### Community 12 - "Notification System"
Cohesion: 0.11
Nodes (45): Config, cleanup_old_notifications(), create_notification(), delete_notification(), _dict_to_notification_response(), _firestore_timestamp_to_datetime(), _get_firestore_service(), get_notification_by_id() (+37 more)

### Community 13 - "Firestore Subcollection Scripts"
Cohesion: 0.07
Nodes (28): check_subcollection_structure(), main(), Main function to check subcollection structure., Check the subcollection structure for tickers or tags.          Args:         se, from_firestore_dict(), PodcastCollection, PodcastEpisode, Podcast data models for Firestore integration. (+20 more)

### Community 14 - "Cache + Redis Debugging"
Cohesion: 0.05
Nodes (48): RedisClient (cache_get/cache_set silent failure), Cache Debugging: Redis Not Connected at Startup, Rationale: Silent Cache Failure Pattern (returns None when Redis unavailable), Rationale: Timeframe-Based Data Granularity Strategy, Massive API get_minute_aggregates, Minute-Level Aggregates Requirement (1H/1D timeframes), Chart Data Requirements (TradingView/Yahoo Finance Comparison), OHLCV Data Structure (+40 more)

### Community 15 - "News System"
Cohesion: 0.07
Nodes (30): Config, create_news(), delete_news(), get_all_news(), get_news_by_tickers(), News database CRUD operations, Delete news and related tickers, Insert news with related tickers (+22 more)

### Community 16 - "FinMind Integration Tests"
Cohesion: 0.06
Nodes (29): FinMind External API, TestFinMindDataLoader Test Suite, get_taiwan_stock_daily(), Integration tests for FinMind DataLoader API Tests the taiwan_stock_daily functi, Test that returned DataFrame has correct schema, Test that API token login is called when token is available, Test that function works without API token, Test handling of empty DataFrame result (+21 more)

### Community 17 - "Admin System Status API"
Cohesion: 0.1
Nodes (31): Admin API endpoints for system status and monitoring., Get system status for admin dashboard.      Returns health metrics for:     - Ba, system_status(), adminAuthConfig(), BackendStatus, getSystemStatus(), HealthCheckResponse, PostgresStatus (+23 more)

### Community 18 - "Graph API Endpoints"
Cohesion: 0.05
Nodes (6): getAllRecentEpisodes(), getClusterVisual(), getOwnershipVisual(), getSortedPodcasts(), getSupplyChainVisual(), processGraphDataResponse()

### Community 19 - "News DB + Service + Tests"
Cohesion: 0.05
Nodes (19): news_db (backend SQLite ops), NewsService (backend), Integration tests for news API endpoints, Test news API endpoints, Test GET /api/news/{news_id}, Test GET /api/news/{news_id} with non-existent ID, TestNewsAPI, Unit tests for news database operations (+11 more)

### Community 20 - "Stock DB + Service + Tests"
Cohesion: 0.06
Nodes (26): stock_db (backend SQLite ops), StockService (backend), Unit tests for stock database operations, Test retrieving price history with date range, Test retrieving latest price, Test stock database CRUD operations, Test creating a new stock, Test updating an existing stock (+18 more)

### Community 21 - "Frontend Layout Components"
Cohesion: 0.06
Nodes (37): ApiEpisode Type, AppLayout, Route Navigation Map, AppLogo, BottomTabs, Change, ChartDataPoint Type, EpisodeCardV2 (+29 more)

### Community 22 - "GCP Cloud SQL + Auth Setup"
Cohesion: 0.07
Nodes (36): Cloud SQL Authorized Networks (Netcup VPS IP), Cloud SQL PostgreSQL Instance (tinboker-db), GCP Cloud SQL PostgreSQL Setup Guide, Rationale: Firebase Admin SDK for Backend Google Token Verification, Auth Router (src/routers/auth.py), Firebase Admin SDK (Token Verification), Google OAuth Implementation Guide, JWT Utilities (src/utils/auth.py) (+28 more)

### Community 23 - "Auth Utils (JWT + Google)"
Cohesion: 0.07
Nodes (28): Clock Skew Tolerance Retry Pattern, create_jwt_token(), get_current_user(), google_login(), Google OAuth ID Token Verification Flow, logout(), Authentication utilities for Google OAuth and JWT tokens, Verify Google OAuth Access Token by calling UserInfo endpoint          Args: (+20 more)

### Community 24 - "Backend Config + Settings"
Cohesion: 0.07
Nodes (17): BaseSettings, GCPSecretManagerSource, Custom Pydantic settings source that loads secrets from Google Cloud Secret Mana, Configuration management for TinBoker Backend.  This module handles: - System/ap, Parse CORS origins from string or list, Get PostgreSQL connection string from DATABASE_URL or individual settings., PostgreSQL URL for recommendation/podcast_db. Uses POSTGRES_* when set; host/por, Get Redis connection string from REDIS_URL or individual settings. (+9 more)

### Community 25 - "CDN Cache Headers"
Cohesion: 0.09
Nodes (30): build_cache_header(), CacheProfile, cdn_cache_news(), cdn_cache_podcast(), cdn_cache_stock(), cdn_cache_trending(), cdn_cached(), cdn_no_cache() (+22 more)

### Community 26 - "Recommendation Service"
Cohesion: 0.13
Nodes (16): _default_start_end(), _parse_date(), Recommendation service: read-only access to ticker recommendations (podcast_db)., Return most-discussed tickers in the last `days` days., Default timeframe: today − 7 days, today., Service for ticker/podcaster recommendations and buzz., Return recommendations for the ticker. Default: last 7 days., Return recommendations from the podcaster. Default: last 7 days. Optional podcas (+8 more)

### Community 27 - "Redis Client"
Cohesion: 0.15
Nodes (17): cache_delete(), cache_delete_pattern(), cache_get(), cache_set(), close(), close_all(), close_pubsub(), create_subscriber() (+9 more)

### Community 28 - "App Shell Components"
Cohesion: 0.1
Nodes (21): App Root Component, AppLayout Component, GlobalPlayer Component, NotificationDropdown Component, PlayerConfirmationModal Component, SearchDropdown Component, ThemeToggle Component, UserMenu Component (+13 more)

### Community 29 - "Price WebSocket Client"
Cohesion: 0.2
Nodes (2): getWebSocketURL(), PriceWebSocketClient

### Community 30 - "Icons.tsx"
Cohesion: 0.12
Nodes (0): 

### Community 31 - "compare_openapi_schemas.py"
Cohesion: 0.24
Nodes (12): compare_endpoints(), compare_schemas(), get_endpoint_details(), get_endpoints(), get_schemas(), load_yaml(), main(), Extract all endpoint paths from schema (+4 more)

### Community 32 - "recommendation_queries.py"
Cohesion: 0.23
Nodes (11): _format_iso(), get_by_podcaster(), get_by_ticker(), get_most_discussed(), Read-only DB queries for ticker recommendations (podcast_db). Assumes table tick, Return most-discussed tickers in the date range as TickerBuzz:     ticker, count, Map a DB row to frontend TickerRecommendation shape., Format timestamp/date to ISO string. (+3 more)

### Community 33 - "postgres.py"
Cohesion: 0.23
Nodes (11): create_all_tables(), drop_all_tables(), get_database_url(), get_session(), init_engine(), PostgreSQL database connection and session management using SQLAlchemy., Create all database tables based on SQLAlchemy models.          Note: For produc, Drop all database tables.          WARNING: This will delete all data! Use only (+3 more)

### Community 34 - "recommendation_db.py"
Cohesion: 0.18
Nodes (11): close_pool(), get_connection(), get_pool(), init_pool(), is_available(), PostgreSQL connection for recommendation/podcast_db. Data is prepared elsewhere;, Initialize the recommendation Postgres connection pool., Close the recommendation Postgres connection pool. (+3 more)

### Community 35 - "GlobalPlayer Component"
Cohesion: 0.18
Nodes (6): GlobalPlayer Component, SlideScaler(), SlideViewer Component, Spotify IFrame API, SpotifyEmbed Component, SpotifyEmbedRef Interface

### Community 36 - "conftest.py"
Cohesion: 0.17
Nodes (11): db_connection(), Pytest configuration and fixtures, Sample news data for testing, Create a temporary in-memory SQLite database for testing, Get database connection for testing, Sample stock data for testing, Sample graph data for testing, sample_graph_data() (+3 more)

### Community 37 - "test_stock_api.py"
Cohesion: 0.17
Nodes (6): Integration tests for stock API endpoints, Test stock API endpoints, Test GET /api/stocks/{ticker}, Test GET /api/stocks/{ticker} with non-existent ticker, Test GET /api/stocks/{ticker}/basic, TestStockAPI

### Community 38 - "Caddy Web Server with Auto-HTTPS"
Cohesion: 0.2
Nodes (12): Caddy Web Server with Auto-HTTPS, Cloudflare CDN and DNS Configuration, Hybrid Data Storage: Firestore + SQLite + PostgreSQL, Backend Docker Containerization, Multi-Environment VPS Deployment (prod/staging/dev), Single Shared Redis Instance for All Environments, Two-Tier Caching: Cloudflare Edge + Redis Origin, Netcup VPS Hosting (Debian 13, Germany) (+4 more)

### Community 39 - "Pytest Fixtures (conftest.py)"
Cohesion: 0.25
Nodes (10): Pytest Fixtures (conftest.py), ensure_db_initialized(), get_connection(), get_db_path(), init_db / get_connection, Database initialization and connection management for SQLite, Get database file path, creating directory if needed, Ensure database is initialized (call on startup). (+2 more)

### Community 40 - "PlayerBroadcastService"
Cohesion: 0.25
Nodes (1): PlayerBroadcastService

### Community 41 - "EpisodeTransformer.to_episode Metho"
Cohesion: 0.18
Nodes (11): EpisodeTransformer.enrich_with_content Method, EpisodeTransformer.extract_tags_from_text, EpisodeTransformer.to_episode Method, GCSContentService.fetch_gcs_content Method, GCS Asyncio Semaphore (concurrency=20), Graph Pydantic Models, Backend Models Package Init, News Pydantic Models (+3 more)

### Community 42 - "Backend Data Specification"
Cohesion: 0.18
Nodes (11): Key Insights Field in Episode API Response, Backend Data Specification, Design Pattern: Dark Mode (slate-900 bg), Design Pattern: Light Mode (white bg), Screenshot: Home Page Dark Mode, Screenshot: Home Page Light Mode, Screenshot: Stock Dashboard Dark Mode, Screenshot: Stock Dashboard Light Mode (+3 more)

### Community 43 - "channels.py"
Cohesion: 0.2
Nodes (9): all_stocks_channel(), Redis channel name utilities for pub/sub, Get Redis channel name for stock price updates, Get Redis channel name for stock news updates, Get Redis channel name for all stocks updates, Get Redis channel name for stock OHLCV updates, stock_news_channel(), stock_ohlcv_channel() (+1 more)

### Community 44 - "Critical Known Issues Table (CLAUDE"
Cohesion: 0.2
Nodes (10): Critical Known Issues Table (CLAUDE.md), BUG-10: Recommendations Endpoint 404, BUG-1: Search Index Never Built, BUG-2: Industry Heatmap Blank, BUG-3: 18/51 Unit Tests Failing, BUG-4: Backend CI Never Blocks, BUG-5: Graph Gallery Zod Validation Errors, BUG-7: Fabricated Stock Key Statistics (+2 more)

### Community 45 - "PWA Icon 128x128"
Cohesion: 0.2
Nodes (10): PWA Icon 128x128, PWA Icon 144x144, PWA Icon 152x152, PWA Icon 512x512, PWA Icon 72x72, PWA Icon 96x96, TinBoker PWA Maskable Icon, TinBoker PWA Standard Icon (+2 more)

### Community 46 - "TinBoker Favicon PNG"
Cohesion: 0.22
Nodes (9): TinBoker Favicon PNG, TinBoker Favicon SVG — Bracket Mark, PWA App Icon 192x192, PWA Icons for Android and iOS, Web App Manifest Requirement, Rationale: No Service Worker in Development, Service Worker Registration and Caching Strategy, PWA Support Specification (+1 more)

### Community 47 - "parseTimestampedSections.ts"
Cohesion: 0.32
Nodes (3): formatTimeFromMs(), formatTimeFromSeconds(), parseTimeCodes()

### Community 48 - "load_graph_data_api.py"
Cohesion: 0.32
Nodes (7): check_existing_graphs(), load_graph_via_api(), load_graphs(), Script to load graph data to production API using HTTP requests.  This script lo, Check if a graph already exists for the given concept_id, Load a graph via API          Returns:         (success: bool, message: str), Load all graph data into the database via API

### Community 49 - "StockHoverCard Component"
Cohesion: 0.25
Nodes (8): StockHoverCard Component, @marp-team/marp-core Library, Marp Custom Link Protocol #tag:, Marp Custom Link Protocol #ticker:, Marp Custom Link Protocol #time:, usePlayerStore (Zustand), Marp Parser Utilities, Marp Post-Processor

### Community 50 - "MockEpisode Type"
Cohesion: 0.43
Nodes (8): MockEpisode Type, PodcasterPicksList, TickerInsightCard, TickerRecommendation Type, Podcast Playback Pattern via PlayerStore, Spotify Fallback Pattern, recommendationService, usePlayerStore

### Community 51 - "PodcastService"
Cohesion: 0.29
Nodes (8): PodcastService, StockService, auth utils (verify_google_token, create_jwt_token), user_db Module, FastAPI App (main.py), Auth API Router, Search API Router, Tags API Router

### Community 52 - "test_websocket.py"
Cohesion: 0.29
Nodes (3): Integration tests for WebSocket endpoints, Test WebSocket endpoints, TestWebSocket

### Community 53 - "Graphs API (graphs.ts)"
Cohesion: 0.33
Nodes (7): Graphs API (graphs.ts), News API (news.ts), Visuals API (visuals.ts), API Response Validation Script, Validate Mocks Script, GraphData Type, Zod Validation Schemas (frontend)

### Community 54 - "sparklineUtils.ts"
Cohesion: 0.33
Nodes (0): 

### Community 55 - "migrate_ticker_json.py"
Cohesion: 0.47
Nodes (5): main(), migrate_tw_tickers(), migrate_us_tickers(), Migrate US tickers from JSON file.     Format: {"TICKER": "English Name"}     Re, Migrate TW tickers from JSON file.     Format: {"TICKER.TW": {"name_zh": "...",

### Community 56 - "API Client (axios singleton)"
Cohesion: 0.47
Nodes (6): API Client (axios singleton), Content API Service, API Service Barrel Re-export, Podcasts API Service, Stocks API Service, Environment-Aware API URL Routing

### Community 57 - "cleanup_translations Script"
Cohesion: 0.53
Nodes (6): cleanup_translations Script, PostgreSQL Database, TranslationService, migrate_ticker_json Migration Script, StockTranslation ORM Model, seed_translations Script

### Community 58 - "Screenshot: Tag Browse Page Dark Mo"
Cohesion: 0.33
Nodes (6): Screenshot: Tag Browse Page Dark Mode, Contextual Navigation by Stock Filter, Landing Page Hero with Freshness Indicator, Mobile First Content Hierarchy, Modern SaaS Visual Design Standard, UI/UX Specification

### Community 59 - "Marp Slide Visualization Carousel"
Cohesion: 0.4
Nodes (6): Cross-Tab Player Synchronization via BroadcastChannel, Marp Slide Visualization Carousel, Rationale: BroadcastChannel API for Cross-Tab Player Sync, News UI Specification, Interactive Timestamp Markers on Progress Bar, Screenshot: News/Podcast Detail Page Dark Mode

### Community 60 - "Redis Cache Key Patterns"
Cohesion: 0.4
Nodes (5): Redis Caching Test Results (75% faster cache hits), Redis Cache Key Patterns, Backend Redis Caching Pattern, Backend Code Style Guidelines, FinMind Caching Strategy

### Community 61 - "init_postgres.py"
Cohesion: 0.5
Nodes (3): main(), Database initialization script. Creates all tables defined in the models., Initialize database and create all tables.

### Community 62 - "dump_openapi.py"
Cohesion: 0.5
Nodes (3): dump_openapi_to_file(), Utility script to dump OpenAPI schema to YAML file.  Usage:     python -m src.ut, Dump OpenAPI schema to YAML file

### Community 63 - "SimpleSparkline.tsx"
Cohesion: 0.5
Nodes (0): 

### Community 64 - "validate-api-responses.ts"
Cohesion: 1.0
Nodes (3): getBaseURL(), main(), validateEndpoint()

### Community 65 - "load_graph_data.py"
Cohesion: 0.5
Nodes (3): load_graphs(), Script to load graph data from mockData.ts into the database.  This script loads, Load all graph data into the database

### Community 66 - "PWA Web App Manifest"
Cohesion: 0.5
Nodes (3): PWA Web App Manifest, VitePWA Plugin, Workbox Service Worker Caching Strategy

### Community 67 - "Google Cloud Firestore Database"
Cohesion: 0.5
Nodes (4): Google Cloud Firestore Database, PodcastCollection Dataclass, PodcastEpisode Dataclass, FirebaseService Upload Service

### Community 68 - "EpisodeTransformer Class"
Cohesion: 0.67
Nodes (4): EpisodeTransformer Class, GCSContentService Class, GCS Multi-Source Credential Resolution Chain, PodcastService Class

### Community 69 - "Module Group 69"
Cohesion: 0.5
Nodes (4): DataCollectionService._collect_from_finmind, DataCollectionService._collect_from_massive, DataCollectionService.collect_stock_data, DataCollectionService._is_taiwan_stock

### Community 70 - "GCSContentService.upload_content Me"
Cohesion: 0.5
Nodes (4): GCSContentService.upload_content Method, PodcastService._invalidate_episode_cache, poll_regeneration_status Background Task, PodcastService.save_modified_summary

### Community 71 - "GCS Bucket: tinboker-articles"
Cohesion: 0.5
Nodes (4): GCS Bucket: tinboker-articles, Content API GCS Router (src/routers/content.py), GCS Signed URL Generation (v4), Rationale: Signed URLs for Private GCS Access

### Community 72 - "Module Group 72"
Cohesion: 0.5
Nodes (4): Production Container Reliability Implementation, GitHub Actions Health Check Workflow (every 10 min), Systemd Services for Docker Container Auto-start, UptimeRobot External Monitoring (every 5 min)

### Community 73 - "graphThumbnail.ts"
Cohesion: 0.67
Nodes (0): 

### Community 74 - "StormBackground.tsx"
Cohesion: 0.67
Nodes (0): 

### Community 75 - "test-episodes-by-tag.js"
Cohesion: 1.0
Nodes (2): main(), testEpisodesByTag()

### Community 76 - "test_search_optimization.py"
Cohesion: 0.67
Nodes (0): 

### Community 77 - "seed_translations.py"
Cohesion: 0.67
Nodes (2): Seed common translations into the database., seed_translations()

### Community 78 - "dagre Layout Library"
Cohesion: 0.67
Nodes (3): dagre Layout Library, reactflow Library, Graph Layout Utilities (dagre)

### Community 79 - "PlayerBroadcast Service"
Cohesion: 0.67
Nodes (3): Cross-Tab Player State Broadcast (BroadcastChannel), PlayerBroadcast Service, usePlayerStore (Zustand)

### Community 80 - "Optimistic UI Update Pattern"
Cohesion: 0.67
Nodes (3): Optimistic UI Update Pattern, useAppStore (Zustand persist), User API Service

### Community 81 - "getStockByTicker (with Zod validati"
Cohesion: 0.67
Nodes (3): getStockByTicker (with Zod validation), CompanyDetailSchema (Zod), parseResponse helper

### Community 82 - "transformEdge"
Cohesion: 0.67
Nodes (3): transformEdge, transformGraphData, transformNode

### Community 83 - "VisualGraphService Class"
Cohesion: 0.67
Nodes (3): VisualGraphService Class, VisualGraphService._enrich_node_with_financials_async, Static EV Graph Structures

### Community 84 - "Module Group 84"
Cohesion: 0.67
Nodes (3): Ticker Markdown Format Requirement for Episodes, Stock Ticker Markdown Format (#ticker:SYMBOL), Tag Buttons Markdown Format (#tag:TAG_NAME)

### Community 85 - "Module Group 85"
Cohesion: 0.67
Nodes (3): Missing GET /api/episodes/by-ticker/{ticker}, Missing GET /api/episodes/recent Endpoint, Inefficient getAllRecentEpisodes Workaround

### Community 86 - "Backend Database Schema"
Cohesion: 0.67
Nodes (3): Backend Database Schema, Backend Tech Stack (FastAPI, SQLite/PostgreSQL, Redis, Massive, FinMind), Backend WebSocket /ws/prices Endpoint

### Community 87 - "Backend CI/CD Pipeline"
Cohesion: 0.67
Nodes (3): Backend CI/CD Pipeline, Backend Deployment Rules (No direct SSH/rsync), Gitflow Branching Strategy

### Community 88 - "UptimeRobot External Monitoring"
Cohesion: 0.67
Nodes (3): GitHub Actions Health Check Auto-Recovery, Production Reliability via Systemd Services, UptimeRobot External Monitoring

### Community 89 - "Massive API REST Endpoints"
Cohesion: 0.67
Nodes (3): Massive API REST Endpoints, Massive API WebSocket, Real-Time Stock WebSocket Architecture Requirements

### Community 90 - "Backend Aggregation Logic for Chart"
Cohesion: 0.67
Nodes (3): Backend Aggregation Logic for Charts, Charting Specification, Weekly/Monthly Timeframe Mapping to Massive API

### Community 91 - "company.py"
Cohesion: 1.0
Nodes (1): Company/stock router (for backward compatibility) Redirects to stock router

### Community 92 - "websocket.py"
Cohesion: 1.0
Nodes (1): WebSocket router (for backward compatibility) Stock WebSocket functionality is i

### Community 93 - "migrate.py"
Cohesion: 1.0
Nodes (1): Database migration script for Render deployment

### Community 94 - "cache_config.py"
Cohesion: 1.0
Nodes (1): Cache configuration - TTL values and key prefixes

### Community 95 - "markdownParser.ts"
Cohesion: 1.0
Nodes (0): 

### Community 96 - "graphLayout.ts"
Cohesion: 1.0
Nodes (0): 

### Community 97 - "navigation.ts"
Cohesion: 1.0
Nodes (0): 

### Community 98 - "elkLayout.ts"
Cohesion: 1.0
Nodes (0): 

### Community 99 - "summaryParser.ts"
Cohesion: 1.0
Nodes (0): 

### Community 100 - "ControlButton.tsx"
Cohesion: 1.0
Nodes (0): 

### Community 101 - "DonationCard.tsx"
Cohesion: 1.0
Nodes (0): 

### Community 102 - "Skeleton.tsx"
Cohesion: 1.0
Nodes (0): 

### Community 103 - "test-episodes-by-ticker.js"
Cohesion: 1.0
Nodes (0): 

### Community 104 - "test_search_latency.py"
Cohesion: 1.0
Nodes (0): 

### Community 105 - "WeeklyBuzzWidget Component"
Cohesion: 1.0
Nodes (2): WeeklyBuzzWidget Component, Recommendation Service

### Community 106 - "CompanyData Type"
Cohesion: 1.0
Nodes (2): CompanyData Type, PersonNode

### Community 107 - "GraphNodeSchema (Zod)"
Cohesion: 1.0
Nodes (2): GraphNodeSchema (Zod), VisualGraphNodeSchema (Zod)

### Community 108 - "checkUrlAvailability"
Cohesion: 1.0
Nodes (2): checkUrlAvailability, initializeApiUrl (async branch API probe)

### Community 109 - "generateSparklineHistory"
Cohesion: 1.0
Nodes (2): generateSparklineHistory, hydrateNodeWithStockData

### Community 110 - "load_graph_data_api Script (HTTP)"
Cohesion: 1.0
Nodes (2): load_graph_data_api Script (HTTP), load_graph_data Script (Direct DB)

### Community 111 - "CompanyDataService Abstract Base Cl"
Cohesion: 1.0
Nodes (2): CompanyDataService Abstract Base Class, FinMindCompanyDataService Class

### Community 112 - "Rationale: Never Deploy Directly to"
Cohesion: 1.0
Nodes (2): Deployment Architecture (Cloudflare Edge to Caddy to Docker), Rationale: Never Deploy Directly to VPS

### Community 113 - "TinBoker Platform README"
Cohesion: 1.0
Nodes (2): Tech Stack Overview (React 19 + FastAPI + Redis + GCP), TinBoker Platform README

### Community 114 - "NewsPage Using Wrong API"
Cohesion: 1.0
Nodes (2): NewsPage Using Wrong API, New Data Flow: EpisodeCard to NewsPage to Podcast API

### Community 115 - "Schema.org Structured Data"
Cohesion: 1.0
Nodes (2): Schema.org Structured Data, Technical SEO Strategy (react-helmet-async, JSON-LD, Sitemap)

### Community 116 - "Missing POST /api/auth/google Endpo"
Cohesion: 1.0
Nodes (2): Missing POST /api/auth/google Endpoint, Google OAuth Backend Endpoint Requirement

### Community 117 - "FinMind API: taiwan_stock_tick_snap"
Cohesion: 1.0
Nodes (2): FinMind API: taiwan_stock_tick_snapshot, Real-Time Stock Data Structures

### Community 118 - "Module Group 118"
Cohesion: 1.0
Nodes (2): Institution Reports (FED, HBR, Bloomberg, Reuters), KOL Information Sharing (股癌, Podcasters, YouTubers)

### Community 119 - "Financial Information Source Analys"
Cohesion: 1.0
Nodes (2): Financial Information Source Analysis, Rationale: Reliability Weighting for Information Aggregation

### Community 120 - "Module Group 120"
Cohesion: 1.0
Nodes (2): Firestore created_time Type Handling Fix, Firestore Subcollection Structure (tickers/{ticker}/episodes)

### Community 121 - "Recent Search History (Last 10 Quer"
Cohesion: 1.0
Nodes (2): Recent Search History (Last 10 Queries), Search UI Specification

### Community 122 - "Module Group 122"
Cohesion: 1.0
Nodes (1): Initialize Redis connection with retry logic.                  Args:

### Community 123 - "Get Redis client instance"
Cohesion: 1.0
Nodes (1): Get Redis client instance

### Community 124 - "Close Redis connection"
Cohesion: 1.0
Nodes (1): Close Redis connection

### Community 125 - "Check if Redis is available"
Cohesion: 1.0
Nodes (1): Check if Redis is available

### Community 126 - "Module Group 126"
Cohesion: 1.0
Nodes (1): Get separate Redis client for pub/sub (recommended)

### Community 127 - "Module Group 127"
Cohesion: 1.0
Nodes (1): Publish a message to a Redis channel.                  Args:             channel

### Community 128 - "Module Group 128"
Cohesion: 1.0
Nodes (1): Create a Redis pub/sub subscriber.                  Returns:             PubSub

### Community 129 - "Subscribe to a Redis channel"
Cohesion: 1.0
Nodes (1): Subscribe to a Redis channel

### Community 130 - "Unsubscribe from a Redis channel"
Cohesion: 1.0
Nodes (1): Unsubscribe from a Redis channel

### Community 131 - "Close pub/sub connection"
Cohesion: 1.0
Nodes (1): Close pub/sub connection

### Community 132 - "Close all Redis connections"
Cohesion: 1.0
Nodes (1): Close all Redis connections

### Community 133 - "Check if WebSocket is connected."
Cohesion: 1.0
Nodes (1): Check if WebSocket is connected.

### Community 134 - "Get current subscriptions."
Cohesion: 1.0
Nodes (1): Get current subscriptions.

### Community 135 - "pwa.d.ts"
Cohesion: 1.0
Nodes (0): 

### Community 136 - "technicalindicators.d.ts"
Cohesion: 1.0
Nodes (0): 

### Community 137 - "global.d.ts"
Cohesion: 1.0
Nodes (0): 

### Community 138 - "market.ts"
Cohesion: 1.0
Nodes (0): 

### Community 139 - "postcss.config.js"
Cohesion: 1.0
Nodes (0): 

### Community 140 - "generate-logo.js"
Cohesion: 1.0
Nodes (0): 

### Community 141 - "StatGroup.tsx"
Cohesion: 1.0
Nodes (0): 

### Community 142 - "ListRow.tsx"
Cohesion: 1.0
Nodes (0): 

### Community 143 - "FilterPills.tsx"
Cohesion: 1.0
Nodes (0): 

### Community 144 - "Module Group 144"
Cohesion: 1.0
Nodes (1): Test getting stock info via mocked external API

### Community 145 - "Module Group 145"
Cohesion: 1.0
Nodes (1): Test getting basic stock info (no chart data)

### Community 146 - "Test getting sorted stocks list"
Cohesion: 1.0
Nodes (1): Test getting sorted stocks list

### Community 147 - "Module Group 147"
Cohesion: 1.0
Nodes (1): Test graceful handling when external API returns nothing

### Community 148 - "Test creating a graph"
Cohesion: 1.0
Nodes (1): Test creating a graph

### Community 149 - "Test retrieving graph by ID"
Cohesion: 1.0
Nodes (1): Test retrieving graph by ID

### Community 150 - "Test getting sorted graphs"
Cohesion: 1.0
Nodes (1): Test getting sorted graphs

### Community 151 - "Test getting news by ID"
Cohesion: 1.0
Nodes (1): Test getting news by ID

### Community 152 - "Test getting sorted news"
Cohesion: 1.0
Nodes (1): Test getting sorted news

### Community 153 - "Module Group 153"
Cohesion: 1.0
Nodes (1): Test WebSocket connection for OHLCV updates

### Community 154 - "Module Group 154"
Cohesion: 1.0
Nodes (1): Test WebSocket connection with invalid ticker

### Community 155 - "Mock successful DataLoader response"
Cohesion: 1.0
Nodes (1): Mock successful DataLoader response

### Community 156 - "Module Group 156"
Cohesion: 1.0
Nodes (1): Integration test with actual FinMind DataLoader API call                  Debugg

### Community 157 - "Integration test with invalid stock"
Cohesion: 1.0
Nodes (1): Integration test with invalid stock ID

### Community 158 - "Mock successful API response"
Cohesion: 1.0
Nodes (1): Mock successful API response

### Community 159 - "Mock API error response"
Cohesion: 1.0
Nodes (1): Mock API error response

### Community 160 - "Mock API response with empty data"
Cohesion: 1.0
Nodes (1): Mock API response with empty data

### Community 161 - "Module Group 161"
Cohesion: 1.0
Nodes (1): Integration test with actual FinMind API call                  Debugging options

### Community 162 - "Integration test with invalid stock"
Cohesion: 1.0
Nodes (1): Integration test with invalid stock ID

### Community 163 - "Module Group 163"
Cohesion: 1.0
Nodes (1): Create PodcastEpisode from Firestore document.                  Args:

### Community 164 - "Module Group 164"
Cohesion: 1.0
Nodes (1): Create from Firestore document.                  Args:             data: Diction

### Community 165 - "Parse CORS origins from string or l"
Cohesion: 1.0
Nodes (1): Parse CORS origins from string or list

### Community 166 - "Module Group 166"
Cohesion: 1.0
Nodes (1): Get PostgreSQL connection string from DATABASE_URL or individual settings.

### Community 167 - "Module Group 167"
Cohesion: 1.0
Nodes (1): PostgreSQL URL for recommendation/podcast_db. Uses POSTGRES_* when set; host/por

### Community 168 - "Module Group 168"
Cohesion: 1.0
Nodes (1): Get Redis connection string from REDIS_URL or individual settings.

### Community 169 - "Module Group 169"
Cohesion: 1.0
Nodes (1): Define priority of settings sources.         Priority (Highest to Lowest):

### Community 170 - "Module Group 170"
Cohesion: 1.0
Nodes (1): Check if running in production environment

### Community 171 - "Module Group 171"
Cohesion: 1.0
Nodes (1): Check if running in development environment

### Community 172 - "Module Group 172"
Cohesion: 1.0
Nodes (1): Parse GCS URL into (bucket_name, blob_path) or None if invalid

### Community 173 - "Module Group 173"
Cohesion: 1.0
Nodes (1): Extract tag IDs from markdown links like [Name](#tag:ID)

### Community 174 - "Module Group 174"
Cohesion: 1.0
Nodes (1): Retrieve list of all companies as StockMetadataCollection

### Community 175 - "Module Group 175"
Cohesion: 1.0
Nodes (1): Retrieve detailed information for a specific company as Stock object

### Community 176 - "Retrieve top moving stocks"
Cohesion: 1.0
Nodes (1): Retrieve top moving stocks

### Community 177 - "Test Episodes By Ticker Script"
Cohesion: 1.0
Nodes (1): Test Episodes By Ticker Script

### Community 178 - "Generate Logo Script"
Cohesion: 1.0
Nodes (1): Generate Logo Script

### Community 179 - "Test Episodes By Tag Script"
Cohesion: 1.0
Nodes (1): Test Episodes By Tag Script

### Community 180 - "PricePoint Interface"
Cohesion: 1.0
Nodes (1): PricePoint Interface

### Community 181 - "DonationCard Component"
Cohesion: 1.0
Nodes (1): DonationCard Component

### Community 182 - "TopStoryCard Component"
Cohesion: 1.0
Nodes (1): TopStoryCard Component

### Community 183 - "Mock Data Services"
Cohesion: 1.0
Nodes (1): Mock Data Services

### Community 184 - "Auth API Service"
Cohesion: 1.0
Nodes (1): Auth API Service

### Community 185 - "PWAUpdatePrompt Component"
Cohesion: 1.0
Nodes (1): PWAUpdatePrompt Component

### Community 186 - "StockLogo Component"
Cohesion: 1.0
Nodes (1): StockLogo Component

### Community 187 - "PodcastAvatar Component"
Cohesion: 1.0
Nodes (1): PodcastAvatar Component

### Community 188 - "LoginButton Component"
Cohesion: 1.0
Nodes (1): LoginButton Component

### Community 189 - "TickerBuzz Type"
Cohesion: 1.0
Nodes (1): TickerBuzz Type

### Community 190 - "Module Group 190"
Cohesion: 1.0
Nodes (1): API Endpoint: GET /api/episodes/by-ticker/{ticker}

### Community 191 - "Module Group 191"
Cohesion: 1.0
Nodes (1): API Endpoint: GET /api/episodes/by-tag/{tag}

### Community 192 - "Staging API: staging-api.tinboker.c"
Cohesion: 1.0
Nodes (1): Staging API: staging-api.tinboker.com

### Community 193 - "technicalindicators Library"
Cohesion: 1.0
Nodes (1): technicalindicators Library

### Community 194 - "Notification Type: new_episode"
Cohesion: 1.0
Nodes (1): Notification Type: new_episode

### Community 195 - "Notification Type: stock_mention"
Cohesion: 1.0
Nodes (1): Notification Type: stock_mention

### Community 196 - "Notification Type: price_alert"
Cohesion: 1.0
Nodes (1): Notification Type: price_alert

### Community 197 - "PageContent"
Cohesion: 1.0
Nodes (1): PageContent

### Community 198 - "SentBar"
Cohesion: 1.0
Nodes (1): SentBar

### Community 199 - "StatGroup"
Cohesion: 1.0
Nodes (1): StatGroup

### Community 200 - "ListRow"
Cohesion: 1.0
Nodes (1): ListRow

### Community 201 - "FilterPills"
Cohesion: 1.0
Nodes (1): FilterPills

### Community 202 - "Breadcrumbs Component"
Cohesion: 1.0
Nodes (1): Breadcrumbs Component

### Community 203 - "Sentiment Library"
Cohesion: 1.0
Nodes (1): Sentiment Library

### Community 204 - "Episode Mock Data Interface"
Cohesion: 1.0
Nodes (1): Episode Mock Data Interface

### Community 205 - "TodayPulse Sub-component"
Cohesion: 1.0
Nodes (1): TodayPulse Sub-component

### Community 206 - "TopTickers Sub-component"
Cohesion: 1.0
Nodes (1): TopTickers Sub-component

### Community 207 - "TopPodcasters Sub-component"
Cohesion: 1.0
Nodes (1): TopPodcasters Sub-component

### Community 208 - "Services Types (types.ts)"
Cohesion: 1.0
Nodes (1): Services Types (types.ts)

### Community 209 - "Services Index (index.ts)"
Cohesion: 1.0
Nodes (1): Services Index (index.ts)

### Community 210 - "CompanyDetail Type"
Cohesion: 1.0
Nodes (1): CompanyDetail Type

### Community 211 - "TickerRecommendation Type"
Cohesion: 1.0
Nodes (1): TickerRecommendation Type

### Community 212 - "RealTimePriceUpdate Type"
Cohesion: 1.0
Nodes (1): RealTimePriceUpdate Type

### Community 213 - "TickerBuzz Type (services/types.ts)"
Cohesion: 1.0
Nodes (1): TickerBuzz Type (services/types.ts)

### Community 214 - "TimeframeOption Type"
Cohesion: 1.0
Nodes (1): TimeframeOption Type

### Community 215 - "SectorBubbleData Type"
Cohesion: 1.0
Nodes (1): SectorBubbleData Type

### Community 216 - "TreeMapItem Type"
Cohesion: 1.0
Nodes (1): TreeMapItem Type

### Community 217 - "Data Transformers (backend to front"
Cohesion: 1.0
Nodes (1): Data Transformers (backend to frontend)

### Community 218 - "Zod Validation Schemas"
Cohesion: 1.0
Nodes (1): Zod Validation Schemas

### Community 219 - "getBaseURL (env-aware URL resolver)"
Cohesion: 1.0
Nodes (1): getBaseURL (env-aware URL resolver)

### Community 220 - "transformCompanyDetail"
Cohesion: 1.0
Nodes (1): transformCompanyDetail

### Community 221 - "transformApiEpisodeToMock"
Cohesion: 1.0
Nodes (1): transformApiEpisodeToMock

### Community 222 - "getRecentEpisodes"
Cohesion: 1.0
Nodes (1): getRecentEpisodes

### Community 223 - "SuggestionIndex (backend)"
Cohesion: 1.0
Nodes (1): SuggestionIndex (backend)

### Community 224 - "TestStockAPI Integration Suite"
Cohesion: 1.0
Nodes (1): TestStockAPI Integration Suite

### Community 225 - "Module Group 225"
Cohesion: 1.0
Nodes (1): Firestore Subcollection Structure Tester

### Community 226 - "check_subcollection_structure Scrip"
Cohesion: 1.0
Nodes (1): check_subcollection_structure Script

### Community 227 - "compare_openapi_schemas Script"
Cohesion: 1.0
Nodes (1): compare_openapi_schemas Script

### Community 228 - "Module Group 228"
Cohesion: 1.0
Nodes (1): GCSContentService.fetch_url_content Method

### Community 229 - "DataCollectionService Class"
Cohesion: 1.0
Nodes (1): DataCollectionService Class

### Community 230 - "Module Group 230"
Cohesion: 1.0
Nodes (1): FinMindCompanyDataService.get_company_detail

### Community 231 - "CLAUDE.md Project Instructions"
Cohesion: 1.0
Nodes (1): CLAUDE.md Project Instructions

### Community 232 - "Frontend AGENTS.md"
Cohesion: 1.0
Nodes (1): Frontend AGENTS.md

### Community 233 - "Google Login Complete Reference Doc"
Cohesion: 1.0
Nodes (1): Google Login Complete Reference Doc

### Community 234 - "Module Group 234"
Cohesion: 1.0
Nodes (1): PR: Episode Re-generation + Marp SlideViewer Integration

### Community 235 - "Frontend README"
Cohesion: 1.0
Nodes (1): Frontend README

### Community 236 - "fetchWithFallback Pattern (docs)"
Cohesion: 1.0
Nodes (1): fetchWithFallback Pattern (docs)

### Community 237 - "Module Group 237"
Cohesion: 1.0
Nodes (1): Empty OpenAPI Schemas for Visual Endpoints

### Community 238 - "Glass and Glow UI Design (Selected)"
Cohesion: 1.0
Nodes (1): Glass and Glow UI Design (Selected)

### Community 239 - "Google OAuth GCP Console Configurat"
Cohesion: 1.0
Nodes (1): Google OAuth GCP Console Configuration

### Community 240 - "FastAPI Backend Dependencies"
Cohesion: 1.0
Nodes (1): FastAPI Backend Dependencies

### Community 241 - "GCP Dependencies"
Cohesion: 1.0
Nodes (1): GCP Dependencies

### Community 242 - "Container Debugging Guide"
Cohesion: 1.0
Nodes (1): Container Debugging Guide

### Community 243 - "Module Group 243"
Cohesion: 1.0
Nodes (1): Fundamental Financial Information Sources

### Community 244 - "Module Group 244"
Cohesion: 1.0
Nodes (1): Social Media Information (PTT, Reddit, Thread)

### Community 245 - "MockCompanyDataService (Fallback)"
Cohesion: 1.0
Nodes (1): MockCompanyDataService (Fallback)

### Community 246 - "Module Group 246"
Cohesion: 1.0
Nodes (1): Rationale: Stop Markdown Parsing, Use Structured Backend Fields

### Community 247 - "Knowledge Graph Report (April 2026)"
Cohesion: 1.0
Nodes (1): Knowledge Graph Report (April 2026)

### Community 248 - "Module Group 248"
Cohesion: 1.0
Nodes (1): Screenshot: Podcast Channel Page Dark Mode

## Knowledge Gaps
- **713 isolated node(s):** `Custom Pydantic settings source that loads secrets from Google Cloud Secret Mana`, `Parse admin emails from comma-separated string or list`, `Parse JWT expiration hours, handling empty strings`, `Enforce PostgreSQL usage in production environment`, `Parse CORS origins from string or list` (+708 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `company.py`** (2 nodes): `company.py`, `Company/stock router (for backward compatibility) Redirects to stock router`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `websocket.py`** (2 nodes): `websocket.py`, `WebSocket router (for backward compatibility) Stock WebSocket functionality is i`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `migrate.py`** (2 nodes): `migrate.py`, `Database migration script for Render deployment`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `cache_config.py`** (2 nodes): `cache_config.py`, `Cache configuration - TTL values and key prefixes`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `markdownParser.ts`** (2 nodes): `markdownParser.ts`, `extractSections()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `graphLayout.ts`** (2 nodes): `graphLayout.ts`, `calculateHierarchicalLayout()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `navigation.ts`** (2 nodes): `navigation.ts`, `handleNavigation()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `elkLayout.ts`** (2 nodes): `elkLayout.ts`, `calculateELKLayout()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `summaryParser.ts`** (2 nodes): `summaryParser.ts`, `parseSummaryTopics()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `ControlButton.tsx`** (2 nodes): `ControlButton.tsx`, `ControlButton()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `DonationCard.tsx`** (2 nodes): `DonationCard.tsx`, `DonationCard()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Skeleton.tsx`** (2 nodes): `Skeleton.tsx`, `Skeleton()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `test-episodes-by-ticker.js`** (2 nodes): `test-episodes-by-ticker.js`, `testEpisodesByTicker()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `test_search_latency.py`** (2 nodes): `test_search_latency.py`, `benchmark_search()`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `WeeklyBuzzWidget Component`** (2 nodes): `WeeklyBuzzWidget Component`, `Recommendation Service`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `CompanyData Type`** (2 nodes): `CompanyData Type`, `PersonNode`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `GraphNodeSchema (Zod)`** (2 nodes): `GraphNodeSchema (Zod)`, `VisualGraphNodeSchema (Zod)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `checkUrlAvailability`** (2 nodes): `checkUrlAvailability`, `initializeApiUrl (async branch API probe)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `generateSparklineHistory`** (2 nodes): `generateSparklineHistory`, `hydrateNodeWithStockData`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `load_graph_data_api Script (HTTP)`** (2 nodes): `load_graph_data_api Script (HTTP)`, `load_graph_data Script (Direct DB)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `CompanyDataService Abstract Base Cl`** (2 nodes): `CompanyDataService Abstract Base Class`, `FinMindCompanyDataService Class`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Rationale: Never Deploy Directly to`** (2 nodes): `Deployment Architecture (Cloudflare Edge to Caddy to Docker)`, `Rationale: Never Deploy Directly to VPS`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `TinBoker Platform README`** (2 nodes): `Tech Stack Overview (React 19 + FastAPI + Redis + GCP)`, `TinBoker Platform README`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `NewsPage Using Wrong API`** (2 nodes): `NewsPage Using Wrong API`, `New Data Flow: EpisodeCard to NewsPage to Podcast API`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Schema.org Structured Data`** (2 nodes): `Schema.org Structured Data`, `Technical SEO Strategy (react-helmet-async, JSON-LD, Sitemap)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Missing POST /api/auth/google Endpo`** (2 nodes): `Missing POST /api/auth/google Endpoint`, `Google OAuth Backend Endpoint Requirement`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `FinMind API: taiwan_stock_tick_snap`** (2 nodes): `FinMind API: taiwan_stock_tick_snapshot`, `Real-Time Stock Data Structures`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 118`** (2 nodes): `Institution Reports (FED, HBR, Bloomberg, Reuters)`, `KOL Information Sharing (股癌, Podcasters, YouTubers)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Financial Information Source Analys`** (2 nodes): `Financial Information Source Analysis`, `Rationale: Reliability Weighting for Information Aggregation`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 120`** (2 nodes): `Firestore created_time Type Handling Fix`, `Firestore Subcollection Structure (tickers/{ticker}/episodes)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Recent Search History (Last 10 Quer`** (2 nodes): `Recent Search History (Last 10 Queries)`, `Search UI Specification`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 122`** (1 nodes): `Initialize Redis connection with retry logic.                  Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Get Redis client instance`** (1 nodes): `Get Redis client instance`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Close Redis connection`** (1 nodes): `Close Redis connection`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Check if Redis is available`** (1 nodes): `Check if Redis is available`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 126`** (1 nodes): `Get separate Redis client for pub/sub (recommended)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 127`** (1 nodes): `Publish a message to a Redis channel.                  Args:             channel`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 128`** (1 nodes): `Create a Redis pub/sub subscriber.                  Returns:             PubSub`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Subscribe to a Redis channel`** (1 nodes): `Subscribe to a Redis channel`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Unsubscribe from a Redis channel`** (1 nodes): `Unsubscribe from a Redis channel`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Close pub/sub connection`** (1 nodes): `Close pub/sub connection`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Close all Redis connections`** (1 nodes): `Close all Redis connections`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Check if WebSocket is connected.`** (1 nodes): `Check if WebSocket is connected.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Get current subscriptions.`** (1 nodes): `Get current subscriptions.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `pwa.d.ts`** (1 nodes): `pwa.d.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `technicalindicators.d.ts`** (1 nodes): `technicalindicators.d.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `global.d.ts`** (1 nodes): `global.d.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `market.ts`** (1 nodes): `market.ts`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `postcss.config.js`** (1 nodes): `postcss.config.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `generate-logo.js`** (1 nodes): `generate-logo.js`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `StatGroup.tsx`** (1 nodes): `StatGroup.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `ListRow.tsx`** (1 nodes): `ListRow.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `FilterPills.tsx`** (1 nodes): `FilterPills.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 144`** (1 nodes): `Test getting stock info via mocked external API`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 145`** (1 nodes): `Test getting basic stock info (no chart data)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Test getting sorted stocks list`** (1 nodes): `Test getting sorted stocks list`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 147`** (1 nodes): `Test graceful handling when external API returns nothing`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Test creating a graph`** (1 nodes): `Test creating a graph`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Test retrieving graph by ID`** (1 nodes): `Test retrieving graph by ID`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Test getting sorted graphs`** (1 nodes): `Test getting sorted graphs`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Test getting news by ID`** (1 nodes): `Test getting news by ID`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Test getting sorted news`** (1 nodes): `Test getting sorted news`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 153`** (1 nodes): `Test WebSocket connection for OHLCV updates`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 154`** (1 nodes): `Test WebSocket connection with invalid ticker`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Mock successful DataLoader response`** (1 nodes): `Mock successful DataLoader response`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 156`** (1 nodes): `Integration test with actual FinMind DataLoader API call                  Debugg`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Integration test with invalid stock`** (1 nodes): `Integration test with invalid stock ID`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Mock successful API response`** (1 nodes): `Mock successful API response`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Mock API error response`** (1 nodes): `Mock API error response`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Mock API response with empty data`** (1 nodes): `Mock API response with empty data`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 161`** (1 nodes): `Integration test with actual FinMind API call                  Debugging options`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Integration test with invalid stock`** (1 nodes): `Integration test with invalid stock ID`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 163`** (1 nodes): `Create PodcastEpisode from Firestore document.                  Args:`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 164`** (1 nodes): `Create from Firestore document.                  Args:             data: Diction`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Parse CORS origins from string or l`** (1 nodes): `Parse CORS origins from string or list`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 166`** (1 nodes): `Get PostgreSQL connection string from DATABASE_URL or individual settings.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 167`** (1 nodes): `PostgreSQL URL for recommendation/podcast_db. Uses POSTGRES_* when set; host/por`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 168`** (1 nodes): `Get Redis connection string from REDIS_URL or individual settings.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 169`** (1 nodes): `Define priority of settings sources.         Priority (Highest to Lowest):`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 170`** (1 nodes): `Check if running in production environment`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 171`** (1 nodes): `Check if running in development environment`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 172`** (1 nodes): `Parse GCS URL into (bucket_name, blob_path) or None if invalid`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 173`** (1 nodes): `Extract tag IDs from markdown links like [Name](#tag:ID)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 174`** (1 nodes): `Retrieve list of all companies as StockMetadataCollection`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 175`** (1 nodes): `Retrieve detailed information for a specific company as Stock object`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Retrieve top moving stocks`** (1 nodes): `Retrieve top moving stocks`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Test Episodes By Ticker Script`** (1 nodes): `Test Episodes By Ticker Script`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Generate Logo Script`** (1 nodes): `Generate Logo Script`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Test Episodes By Tag Script`** (1 nodes): `Test Episodes By Tag Script`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `PricePoint Interface`** (1 nodes): `PricePoint Interface`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `DonationCard Component`** (1 nodes): `DonationCard Component`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `TopStoryCard Component`** (1 nodes): `TopStoryCard Component`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Mock Data Services`** (1 nodes): `Mock Data Services`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Auth API Service`** (1 nodes): `Auth API Service`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `PWAUpdatePrompt Component`** (1 nodes): `PWAUpdatePrompt Component`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `StockLogo Component`** (1 nodes): `StockLogo Component`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `PodcastAvatar Component`** (1 nodes): `PodcastAvatar Component`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `LoginButton Component`** (1 nodes): `LoginButton Component`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `TickerBuzz Type`** (1 nodes): `TickerBuzz Type`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 190`** (1 nodes): `API Endpoint: GET /api/episodes/by-ticker/{ticker}`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 191`** (1 nodes): `API Endpoint: GET /api/episodes/by-tag/{tag}`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Staging API: staging-api.tinboker.c`** (1 nodes): `Staging API: staging-api.tinboker.com`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `technicalindicators Library`** (1 nodes): `technicalindicators Library`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Notification Type: new_episode`** (1 nodes): `Notification Type: new_episode`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Notification Type: stock_mention`** (1 nodes): `Notification Type: stock_mention`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Notification Type: price_alert`** (1 nodes): `Notification Type: price_alert`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `PageContent`** (1 nodes): `PageContent`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `SentBar`** (1 nodes): `SentBar`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `StatGroup`** (1 nodes): `StatGroup`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `ListRow`** (1 nodes): `ListRow`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `FilterPills`** (1 nodes): `FilterPills`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Breadcrumbs Component`** (1 nodes): `Breadcrumbs Component`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Sentiment Library`** (1 nodes): `Sentiment Library`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Episode Mock Data Interface`** (1 nodes): `Episode Mock Data Interface`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `TodayPulse Sub-component`** (1 nodes): `TodayPulse Sub-component`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `TopTickers Sub-component`** (1 nodes): `TopTickers Sub-component`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `TopPodcasters Sub-component`** (1 nodes): `TopPodcasters Sub-component`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Services Types (types.ts)`** (1 nodes): `Services Types (types.ts)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Services Index (index.ts)`** (1 nodes): `Services Index (index.ts)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `CompanyDetail Type`** (1 nodes): `CompanyDetail Type`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `TickerRecommendation Type`** (1 nodes): `TickerRecommendation Type`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `RealTimePriceUpdate Type`** (1 nodes): `RealTimePriceUpdate Type`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `TickerBuzz Type (services/types.ts)`** (1 nodes): `TickerBuzz Type (services/types.ts)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `TimeframeOption Type`** (1 nodes): `TimeframeOption Type`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `SectorBubbleData Type`** (1 nodes): `SectorBubbleData Type`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `TreeMapItem Type`** (1 nodes): `TreeMapItem Type`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Data Transformers (backend to front`** (1 nodes): `Data Transformers (backend to frontend)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Zod Validation Schemas`** (1 nodes): `Zod Validation Schemas`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `getBaseURL (env-aware URL resolver)`** (1 nodes): `getBaseURL (env-aware URL resolver)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `transformCompanyDetail`** (1 nodes): `transformCompanyDetail`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `transformApiEpisodeToMock`** (1 nodes): `transformApiEpisodeToMock`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `getRecentEpisodes`** (1 nodes): `getRecentEpisodes`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `SuggestionIndex (backend)`** (1 nodes): `SuggestionIndex (backend)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `TestStockAPI Integration Suite`** (1 nodes): `TestStockAPI Integration Suite`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 225`** (1 nodes): `Firestore Subcollection Structure Tester`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `check_subcollection_structure Scrip`** (1 nodes): `check_subcollection_structure Script`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `compare_openapi_schemas Script`** (1 nodes): `compare_openapi_schemas Script`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 228`** (1 nodes): `GCSContentService.fetch_url_content Method`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `DataCollectionService Class`** (1 nodes): `DataCollectionService Class`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 230`** (1 nodes): `FinMindCompanyDataService.get_company_detail`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `CLAUDE.md Project Instructions`** (1 nodes): `CLAUDE.md Project Instructions`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Frontend AGENTS.md`** (1 nodes): `Frontend AGENTS.md`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Google Login Complete Reference Doc`** (1 nodes): `Google Login Complete Reference Doc`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 234`** (1 nodes): `PR: Episode Re-generation + Marp SlideViewer Integration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Frontend README`** (1 nodes): `Frontend README`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `fetchWithFallback Pattern (docs)`** (1 nodes): `fetchWithFallback Pattern (docs)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 237`** (1 nodes): `Empty OpenAPI Schemas for Visual Endpoints`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Glass and Glow UI Design (Selected)`** (1 nodes): `Glass and Glow UI Design (Selected)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Google OAuth GCP Console Configurat`** (1 nodes): `Google OAuth GCP Console Configuration`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `FastAPI Backend Dependencies`** (1 nodes): `FastAPI Backend Dependencies`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `GCP Dependencies`** (1 nodes): `GCP Dependencies`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Container Debugging Guide`** (1 nodes): `Container Debugging Guide`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 243`** (1 nodes): `Fundamental Financial Information Sources`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 244`** (1 nodes): `Social Media Information (PTT, Reddit, Thread)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `MockCompanyDataService (Fallback)`** (1 nodes): `MockCompanyDataService (Fallback)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 246`** (1 nodes): `Rationale: Stop Markdown Parsing, Use Structured Backend Fields`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Knowledge Graph Report (April 2026)`** (1 nodes): `Knowledge Graph Report (April 2026)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Group 248`** (1 nodes): `Screenshot: Podcast Channel Page Dark Mode`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `SearchResultItem` connect `Episode Transformer` to `Graph Models + DB`, `Stock Data Models`?**
  _High betweenness centrality (0.058) - this node is a cross-community bridge._
- **Why does `StockService` connect `Graph Models + DB` to `Company Data Service`, `Visual Graph Service`, `Episode Transformer`, `Stock Data Models`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **Why does `Background workers for TinBoker Backend` connect `Graph Models + DB` to `Episode Transformer`, `Cloudflare Middleware`, `Admin Auth + Dependencies`, `Stock Data Models`, `News System`, `CDN Cache Headers`?**
  _High betweenness centrality (0.039) - this node is a cross-community bridge._
- **Are the 65 inferred relationships involving `FirestoreService` (e.g. with `User database operations using Firestore` and `Get or create FirestoreService instance`) actually correct?**
  _`FirestoreService` has 65 INFERRED edges - model-reasoned connections that need verification._
- **Are the 54 inferred relationships involving `StockService` (e.g. with `Visual graph service: enriches graph structures with real financial data from St` and `Get sorted stocks list with optional search          Query params:     - sort_by`) actually correct?**
  _`StockService` has 54 INFERRED edges - model-reasoned connections that need verification._
- **Are the 61 inferred relationships involving `SearchResultItem` (e.g. with `Unified search endpoint.     Returns results for stocks, podcasts, episodes, and` and `Fast typeahead suggestions.     Returns instant suggestions for autocomplete. Ta`) actually correct?**
  _`SearchResultItem` has 61 INFERRED edges - model-reasoned connections that need verification._
- **Are the 35 inferred relationships involving `PodcastService` (e.g. with `Get sorted podcasts list          Query params:     - sort_by: Sort field (name,` and `Get podcast by name          Returns podcast metadata including episode count an`) actually correct?**
  _`PodcastService` has 35 INFERRED edges - model-reasoned connections that need verification._