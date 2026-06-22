# TinBoker Issues & Status

The **canonical, curated issue list** for the platform. This replaces the old dated QA
snapshot (`qa-report-2026-05-09.md`, removed). Bug IDs (`BUG-N`) are retained as stable labels
that other docs cite — when you resolve one, move it to **Resolved** with a date + commit SHA
rather than deleting it.

Last updated: 2026-06-22

---

## Open issues

### BUG-2 — Industry analysis page uses stub data
**Severity:** Medium · **Files:** [`frontend/src/pages/IndustryAnalysis.tsx`](../frontend/src/pages/IndustryAnalysis.tsx), [`frontend/src/components/industry/TreeMap.tsx`](../frontend/src/components/industry/TreeMap.tsx), [`frontend/src/services/mocks/sectorData.ts`](../frontend/src/services/mocks/sectorData.ts)

The industry analysis page (S&P 500 treemap, sector bubbles, rotation chart) reads entirely
from hardcoded mock data in `sectorData.ts`. There is no backend sector/market endpoint
(`backend/src/routers/` has no sector router). The page is **not in the primary nav** (removed in
`3e95c67`) and is only reachable by direct URL, so it is low-impact — but it must be wired to a
real data source before it re-enters the nav.

**To fix:** add a `/api/sector/*` backend endpoint (or integrate a third-party feed such as
FinViz / Polygon / Massive), then point `IndustryAnalysis.tsx` at it via `fetchWithFallback`.

### GraphGallery → EpisodeDetail dead links
**Severity:** Low · **Files:** [`frontend/src/pages/GraphGallery.tsx`](../frontend/src/pages/GraphGallery.tsx), `EpisodeDetail`

Clicking a graph card in `/story` navigates to `/episode/{model-id}` (e.g. `/episode/supply-chain`).
Those are static interactive-model IDs, not real episode IDs, so EpisodeDetail shows
"找不到這集摘要。". This is intentional (the graph models are demo content) but a dedicated
`/story/:id` detail route would be cleaner.

---

## Resolved

| ID | Issue | Resolution |
|----|-------|------------|
| BUG-1 | Search/suggestion index never built (`@router.on_event` no-ops) | Built from the app `lifespan` in `main.py` (`await init_search_index()`) |
| BUG-3 | Backend unit tests failing | `pytest tests/unit/` is green (209 tests, 0 failed as of 2026-06-22) |
| BUG-4 | Backend CI never blocks PRs | `backend-ci.yml` uses a `ci-gate` aggregation job; no `continue-on-error` |
| BUG-5 | Zod schema validation crashes data fetches | `schemas.ts` uses `.catch(...)` fallbacks; `news.ts` filters invalid items via `safeParse` |
| BUG-7 | Stock "Key Statistics" fabricated (Open = price×0.98, P/E = 15.4) | `StockDashboard.tsx` derives stats from real OHLC chart data, falls back to `—` |
| BUG-9 | CORS origins included dead domain `trendbrief.xyz` | `config.py` CORS list is current domains only |
| BUG-10 | Recommendations endpoint 404 | Frontend uses `/api/ticker-insights/*`; legacy `/api/recommendations/*` kept as deprecated aliases |

---

## Architectural notes

### Deprecated recommendation paths
`/api/recommendations/*` ([`backend/src/routers/recommendations.py`](../backend/src/routers/recommendations.py))
are soft-deprecated (as of 2026-05-14, `deprecated=True`). The frontend reads
`/api/ticker-insights/*` via `getInsightsByTicker`, `getInsightsByPodcaster`, and
`getTrendingTickers`. Remove the legacy aliases once the compatibility window closes.

### Industry page is not in nav
`/industry` is live but unlinked from the primary nav. If it re-enters the nav, connect it to
real data first (see BUG-2).

---

## Reproducing & regression-testing

The per-bug repro recipes and the full QA suite live in
[`workflows/qa-flow.md`](workflows/qa-flow.md) and [`agents/qa-tester.md`](agents/qa-tester.md).
