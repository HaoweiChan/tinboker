# Search & discovery domain

Tool-neutral reference for any agent working on search, suggestions, trending content, tags, or topic discovery. For code style, defer to [`backend/AGENTS.md`](../../backend/AGENTS.md) and [`frontend/AGENTS.md`](../../frontend/AGENTS.md).

## Scope

Everything a user encounters when finding content: the global search bar / overlay, autocomplete suggestions, trending stocks and channels widgets, tag pages, and the topics cloud. Owns both the backend suggestion index and the frontend search UX.

Boundaries: the underlying episode/stock data lives in [`podcast-domain.md`](./podcast-domain.md) and [`stock-data.md`](./stock-data.md). This domain is the discovery layer on top of them.

## Key files

### Backend

| Concern | File |
|---|---|
| Search + suggest endpoints | [`backend/src/routers/search.py`](../../backend/src/routers/search.py) |
| In-memory suggestion index | [`backend/src/services/suggestion_index.py`](../../backend/src/services/suggestion_index.py) |
| Trending stocks / channels | [`backend/src/services/trending.py`](../../backend/src/services/trending.py) |
| Tags API | [`backend/src/routers/tags.py`](../../backend/src/routers/tags.py) |
| Click analytics (drives trending) | [`backend/src/routers/analytics.py`](../../backend/src/routers/analytics.py) |

### Frontend

| Concern | File |
|---|---|
| Tag page | [`frontend/src/pages/TagPage.tsx`](../../frontend/src/pages/TagPage.tsx) |
| Topics cloud | [`frontend/src/pages/TopicsCloud.tsx`](../../frontend/src/pages/TopicsCloud.tsx) |
| Landing page hero / trending widgets | [`frontend/src/components/landing/`](../../frontend/src/components/landing/), [`frontend/src/components/home/`](../../frontend/src/components/home/) |
| Search overlay component | look under [`frontend/src/components/layout/`](../../frontend/src/components/layout/) and `common/` for the header search; recent UI work compacted the search bar (commit `480cee8 fix(ui): compact search bar and replace full-screen mobile overlay`) |
| API clients | [`frontend/src/services/api/search.ts`](../../frontend/src/services/api/search.ts), `analytics.ts` |

## Conventions

- **Fuzzy suggestions must return in under 50ms** with partial matches working for both English (`nvd` → `NVDA`) and Chinese (`台積` → `2330`). The index is in-memory; it must be built once at app start.
- **Single source for trending data.** Landing page "熱門標的"/"熱門頻道" widgets AND the search overlay BOTH consume `/api/search/popular`. Don't introduce a second endpoint for the same data.
- **Labels are fixed.** Use `熱門標的` for stocks (not "Trending Stocks"), `熱門頻道` for podcasts/channels (not "Trending Podcasters").
- **Icons by entity type.** Stocks render as rounded-square Clearbit logo. Podcasts render with `icon_url` from the backend (Spotify image). Don't use the generic `TrendingUp` icon for stocks — that's a bug pattern.
- **Trending stocks** = most-mentioned tickers in episodes over the last 7 days. **Trending channels** = click popularity from Redis sorted set, recorded via `POST /api/analytics/click`.
- **Trending stocks ship a 30-day change percent.** Computed as `(last_price - first_price) / first_price` over the sparkline window.
- **Recent search history** is persisted in `localStorage` (last 10 successful queries), shown in the "Recent" section of the overlay.
- **No double scrollbars.** When the search overlay opens, ensure the content area handles its own scrolling — don't nest scroll containers.

## Common pitfalls

- **BUG-1 (critical, historical):** The suggestion index was built via `@router.on_event("startup")` in [`backend/src/routers/search.py`](../../backend/src/routers/search.py) — but `on_event` only fires on the FastAPI `app`, not on routers. Build the index from the app's `lifespan` context in [`backend/src/main.py`](../../backend/src/main.py), or call the builder there explicitly. See [`../qa-report-2026-05-09.md`](../qa-report-2026-05-09.md) BUG-1 for the full root cause.
- **`asyncio.create_task(build_search_index())` inside `/suggest` is a race condition** — it doesn't block the response, so the first few requests see an empty index. Don't rely on this as a fallback.
- **Suggestion responses must be fast.** If a query starts taking > 200ms, the index has likely been rebuilt incorrectly or a downstream service is being hit per-request. Re-check that everything is in memory.
- **Trending data must not be mocked.** Earlier versions returned hardcoded values; the spec requires real platform data from `episodes.related_tickers` (stocks) and the Redis click sorted set (channels).

## External integrations

- **Redis** — sorted sets backing trending click counts (`trending:clicks:podcast`, etc.) and cached search results.
- **Firestore** `graphfolio-db` — source for episode mentions when building the trending stocks list.

## Cross-references

- Trending tickers data contract: [`../firestore-contract.md`](../firestore-contract.md) §5 (`trending_tickers/{ticker}`)
- Workflow for QA on broken search: [`../workflows/qa-flow.md`](../workflows/qa-flow.md) §2.2
- Backend code style: [`../../backend/AGENTS.md`](../../backend/AGENTS.md)
- Frontend zh-TW conventions: [`../../frontend/AGENTS.md`](../../frontend/AGENTS.md)
- Bugs: BUG-1 (search broken) in [`../qa-report-2026-05-09.md`](../qa-report-2026-05-09.md)
