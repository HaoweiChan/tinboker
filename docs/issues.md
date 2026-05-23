# TinBoker Issues & Status

Last updated: 2026-05-24

---

## Fixed in This Session

### Zod schema validation crashes (was BUG-5)
**Files:** `frontend/src/validation/schemas.ts`, `frontend/src/services/api/news.ts`

The Zod schemas used for API response validation were too strict, causing hard throws that could
crash entire data-fetching flows when the backend returned unexpected-but-harmless values.

**Changes made:**
- `GraphNodeDataSchema.marketCapTier`: narrow enum → `.catch(undefined)` — unexpected values now
  silently map to `undefined` instead of throwing. Prevents `getGraphById` from crashing on nodes
  with non-standard tier values.
- `GraphEdgeDataSchema.category`: same treatment as above.
- `CompanyStatsSchema` (volume, beta, volatility): added `.catch(0)` — missing or null stats fields
  default to 0 instead of breaking stock page validation.
- `CompanyDetailSchema` (price, change, changePercent, marketCap, about): added `.catch(defaultValue)`
  — prevents hard crashes when fields are null/missing in API response.
- `InteractiveModelDataSchema.graphType`: added `.catch('force')` — unknown graph type now defaults
  to force layout instead of throwing.
- `getSortedNews` in `news.ts`: changed `Array.map(parseResponse)` → `reduce` with `safeParse` —
  individual invalid news items are now silently filtered out instead of crashing the whole fetch.

---

## Already Fixed (Pre-Existing Fixes Confirmed)

### BUG-1: Search index never built
**Status: FIXED** — `main.py:68` calls `await init_search_index()` inside the `lifespan`
context manager (correct pattern, not deprecated `@app.on_event("startup")`).

### BUG-4: Backend CI never blocks PRs
**Status: FIXED** — `.github/workflows/backend-ci.yml` has no `continue-on-error: true`.
It uses a proper `ci-gate` aggregation job (job 4) that fails if `test` or `lint` jobs fail.

### BUG-9: CORS origins include old domain trendbrief.xyz
**Status: FIXED** — `backend/src/config.py` CORS origins list no longer contains
`trendbrief.xyz`. Only current domains are present.

### BUG-10: Recommendations endpoint 404
**Status: RESOLVED** — The deprecated `/api/recommendations/by-ticker/`,
`/api/recommendations/by-podcaster/`, and `/api/recommendations/buzz` endpoints still exist
in `backend/src/routers/recommendations.py` and return data (logged as deprecated). Active
frontend code in `StockDashboard.tsx` already uses the new `/api/ticker-insights/` endpoints
(`getInsightsByTicker`). The `recommendationService.ts` wraps the deprecated paths as a
migration shim; these can be removed once callers are migrated.

### BUG-7: Stock key statistics fabricated
**Status: RESOLVED** — `StockDashboard.tsx` now derives key stats (open, high, low, volume)
from the last chart data point returned by the API (`latest?.open`, `latest?.high`, etc.)
and falls back to `—` when data is unavailable. Market cap and P/E come from the validated
API response.

---

## Open Issues (Require Backend Work)

### BUG-2: Industry heatmap / analysis page uses stub data
**Severity:** Medium (page is functional but shows static demo data)
**File:** `frontend/src/pages/IndustryAnalysis.tsx`, `frontend/src/services/mocks/sectorData.ts`

The industry analysis page (S&P 500 treemap, sector bubbles, rotation chart) reads entirely
from hardcoded mock data in `sectorData.ts`. No backend API endpoint for sector/market data
exists (`backend/src/routers/` has no sector router).

**To fix:** Implement a `/api/sector/treemap` and `/api/sector/performance` backend endpoint
(or integrate a third-party data source like FinViz, Polygon, or Massive), then wire up
`IndustryAnalysis.tsx` to call it with `fetchWithFallback`.

### BUG-3: 18/51 unit tests failing
**Severity:** Critical (CI quality gate is only as good as the tests)
**File:** `backend/tests/unit/test_graph_service.py` and others

Backend unit tests have failures. Run `cd backend && pytest tests/unit/ -v` to see current
failures. Until these are fixed, the CI gate gives false confidence.

---

## Architectural Notes

### Deprecated recommendation paths
`/api/recommendations/*` routes are soft-deprecated as of 2026-05-14 per spec § 4.4.
Frontend `recommendationService.ts` still wraps them. Migration to `/api/ticker-insights/*`
is partially done (StockDashboard uses the new path). Remove the old service methods and
the backend routes once all callers are migrated.

### Industry page
`/industry` is not in the primary nav (`3e95c67` removed it). The page is live but
unreachable without a direct URL. If the page re-enters nav, connect it to real data first.

### GraphGallery → EpisodeDetail navigation
Clicking a graph card in `/story` navigates to `/episode/{model-id}` (e.g.
`/episode/supply-chain`). These are static interactive-model IDs, not real episode IDs.
EpisodeDetail shows "找不到這集摘要。" for these URLs. This is intentional (the graph
models are demo content) but could be improved with a dedicated `/story/:id` detail route.
