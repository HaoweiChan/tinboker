# Stock data domain

Tool-neutral reference for any agent working on Taiwan/US market data, stock charts, ticker insights, batch prices, WebSocket streaming, or stock translations. For code style, defer to [`backend/AGENTS.md`](../../backend/AGENTS.md) and [`frontend/AGENTS.md`](../../frontend/AGENTS.md).

## Scope

Everything related to stock and ticker data: live prices, OHLCV history, charts, company metadata, per-episode ticker insights, trending tickers, and ZH-TW name translations. Covers both Taiwan (FinMind) and US (Massive API) markets.

Boundaries: episode-level content rendering and the "mentioned in episodes" list use the [`podcast-domain.md`](./podcast-domain.md) APIs; the knowledge graph that connects companies belongs to [`graph-visuals.md`](./graph-visuals.md).

## Key files

### Backend

| Concern | File |
|---|---|
| Stock REST API (list, detail, history, batch prices) | [`backend/src/routers/stock.py`](../../backend/src/routers/stock.py) |
| Company metadata API | [`backend/src/routers/company.py`](../../backend/src/routers/company.py), [`backend/src/services/company_service.py`](../../backend/src/services/company_service.py) |
| Ticker insights API (Firestore-backed) | [`backend/src/routers/ticker_insights.py`](../../backend/src/routers/ticker_insights.py), [`backend/src/services/insight_service.py`](../../backend/src/services/insight_service.py) |
| WebSocket price stream | [`backend/src/routers/websocket_prices.py`](../../backend/src/routers/websocket_prices.py), [`backend/src/services/stock_publisher.py`](../../backend/src/services/stock_publisher.py), [`backend/src/services/websocket_subscriber.py`](../../backend/src/services/websocket_subscriber.py) |
| Translations API (public + admin) | [`backend/src/routers/translations.py`](../../backend/src/routers/translations.py), [`backend/src/routers/admin_translations.py`](../../backend/src/routers/admin_translations.py), [`backend/src/services/translation_service.py`](../../backend/src/services/translation_service.py) |
| Stock aggregation service | [`backend/src/services/stock.py`](../../backend/src/services/stock.py), [`backend/src/services/data_collection_service.py`](../../backend/src/services/data_collection_service.py) |
| FinMind (TW) integration | [`backend/src/services/finmind_service.py`](../../backend/src/services/finmind_service.py), [`backend/src/services/finmind_websocket_service.py`](../../backend/src/services/finmind_websocket_service.py) |
| Massive API (US) integration | [`backend/src/services/massive_service.py`](../../backend/src/services/massive_service.py), [`backend/src/services/massive_websocket_service.py`](../../backend/src/services/massive_websocket_service.py) |
| TradingView logo lookup | [`backend/src/services/tradingview_logo_service.py`](../../backend/src/services/tradingview_logo_service.py) |

### Frontend

| Concern | File |
|---|---|
| Main stock dashboard | [`frontend/src/pages/StockDashboard.tsx`](../../frontend/src/pages/StockDashboard.tsx) |
| Per-episode overlay | [`frontend/src/pages/StockOverlayPage.tsx`](../../frontend/src/pages/StockOverlayPage.tsx) |
| All-stocks index (Stock Index) | [`frontend/src/pages/StockIndex.tsx`](../../frontend/src/pages/StockIndex.tsx) |
| Company overview | [`frontend/src/pages/CompanyOverviewPage.tsx`](../../frontend/src/pages/CompanyOverviewPage.tsx) |
| Industry analysis (heatmap) | [`frontend/src/pages/IndustryAnalysis.tsx`](../../frontend/src/pages/IndustryAnalysis.tsx) |
| Stock/charts/financial components | [`frontend/src/components/stock/`](../../frontend/src/components/stock/), [`frontend/src/components/charts/`](../../frontend/src/components/charts/), [`frontend/src/components/financial/`](../../frontend/src/components/financial/), [`frontend/src/components/industry/`](../../frontend/src/components/industry/) |
| API clients | [`frontend/src/services/api/stocks.ts`](../../frontend/src/services/api/stocks.ts), `translations.ts` |
| Validation schemas (Zod) | [`frontend/src/validation/schemas.ts`](../../frontend/src/validation/schemas.ts) |

## Conventions

- **Market routing.** FinMind handles Taiwan tickers (4-digit codes like `2330`). Massive handles US tickers (1-5 letter symbols like `NVDA`). The aggregation lives in `backend/src/services/stock.py`; new market support means adding a service + dispatcher entry, not modifying call sites.
- **Cache-first, fetch-on-miss.** All stock detail/list endpoints use the `cache_get` → compute → `cache_set` pattern with Redis. TTLs are short for prices (seconds), longer for static metadata (hours).
- **Batch prices route must precede single-ticker route.** FastAPI matches routes top-down, so `/api/stocks/batch-prices` is declared BEFORE `/api/stocks/{ticker}` in [`backend/src/routers/stock.py`](../../backend/src/routers/stock.py). Don't reorder.
- **Chart timeframe params.** `timeframe` accepts `1D`, `1W`, `1M`, etc. The backend maps these to Massive API timespans. Moving averages (MA5, MA20, MA60) toggle independently in the chart config.
- **WebSocket prices.** Live updates go through `/ws/prices`. Server publishes via `stock_publisher`, clients subscribe via `websocket_subscriber`. Don't use these for one-shot price reads — use the REST batch endpoint instead.
- **Stock translations are public read, admin write.** `GET /api/stocks/translations/{ticker}?market=US` requires no auth. Admin endpoints under `/api/admin/translations/*` require the admin JWT (see [`auth-admin.md`](./auth-admin.md)).
- **Display format with translation.** When a ZH-TW translation exists, the frontend displays `"{TICKER} {NAME_ZH_TW}"` (e.g. `"NVDA 輝達"`); without translation it falls back to `"{TICKER} {NAME_EN}"`.

## Common pitfalls

- **BUG-7 (medium):** [`frontend/src/pages/StockDashboard.tsx`](../../frontend/src/pages/StockDashboard.tsx) historically fabricated "Key Statistics" (Open = price × 0.98, P/E = 15.4). Any change to that section must read from actual OHLC data, not multipliers. See [`../issues.md`](../issues.md) BUG-7.
- **BUG-10 (medium):** Frontend recommendation client called `/api/recommendations/ticker/2330` but the real route is `/api/recommendations/by-ticker/2330`. The new flow uses `/api/ticker-insights/*` — prefer those when wiring new consumers. See [`../firestore-contract.md`](../firestore-contract.md) §4.
- **`marketCapTier` Zod validation.** [`frontend/src/validation/schemas.ts`](../../frontend/src/validation/schemas.ts) requires `large | medium | small` but the API returns other values on some nodes. Either keep the field optional or fix the producer — not both with a fallback that masks the error. See [`../issues.md`](../issues.md) BUG-5.
- **Postgres pool DNS error in prod.** The legacy recommendation Postgres reports `pool_not_initialized` because `docker-db_postgres-1` is unreachable. Migrating reads to Firestore (via ticker-insights) is the actual fix, not a Postgres workaround. See [`../firestore-contract.md`](../firestore-contract.md) Phase A.
- **TradingView logo URLs are external.** Render with a graceful broken-image state; don't block on logo load.

## External integrations

- **FinMind** (`FINMIND_API_KEY` from Secret Manager) — Taiwan stock prices, OHLCV history.
- **Massive API** (`MASSIVE_API_KEY` from Secret Manager) — US market data, including WebSocket price stream.
- **Firestore** `graphfolio-db` — ticker_insights, trending_tickers (per [`../firestore-contract.md`](../firestore-contract.md)).
- **PostgreSQL** Cloud SQL (`POSTGRES_HOST`, `POSTGRES_PASSWORD`) — stock translations + legacy recommendations.
- **TradingView** — public-CDN ticker logos; lookup table in `tradingview_logo_service.py`.

## Cross-references

- Data contract: [`../firestore-contract.md`](../firestore-contract.md) §4 (ticker_insights), §5 (trending_tickers)
- Workflow for Firestore changes: [`../workflows/firestore-data-change.md`](../workflows/firestore-data-change.md)
- Backend code style: [`../../backend/AGENTS.md`](../../backend/AGENTS.md)
- Frontend zh-TW glossary (stock terms): [`../../frontend/AGENTS.md`](../../frontend/AGENTS.md)
- QA bugs in this domain: BUG-5, BUG-7, BUG-9, BUG-10 in [`../issues.md`](../issues.md)
