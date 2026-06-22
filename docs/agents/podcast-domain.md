# Podcast domain

Tool-neutral reference for any agent (Claude Code, Codex, Cursor, etc.) working on episodes, podcasts, content, comments, recommendations, or news. For code style/conventions, defer to [`backend/AGENTS.md`](../../backend/AGENTS.md) and [`frontend/AGENTS.md`](../../frontend/AGENTS.md).

## Scope

This domain owns everything a user sees when consuming podcast content — the home feed, episode detail page, podcaster profiles, comments, and recommendation surfaces. It also owns the backend pipeline that hydrates this content from Firestore and GCS.

Boundaries: stock-data, search, and the knowledge-graph visualizations are **separate domains** even though they appear inside episode pages — see [`stock-data.md`](./stock-data.md), [`search-discovery.md`](./search-discovery.md), [`graph-visuals.md`](./graph-visuals.md).

## Key files

### Backend

| Concern | File |
|---|---|
| Podcast/episode listing + detail API | [`backend/src/routers/podcast.py`](../../backend/src/routers/podcast.py), [`backend/src/routers/episodes.py`](../../backend/src/routers/episodes.py) |
| Content/article API (GCS-backed) | [`backend/src/routers/content.py`](../../backend/src/routers/content.py) |
| Episode comments | [`backend/src/routers/comments.py`](../../backend/src/routers/comments.py), [`backend/src/database/comment_db.py`](../../backend/src/database/comment_db.py) |
| Recommendations (legacy Postgres) | [`backend/src/routers/recommendations.py`](../../backend/src/routers/recommendations.py), [`backend/src/services/recommendation_service.py`](../../backend/src/services/recommendation_service.py) |
| Ticker insights (new Firestore-backed) | [`backend/src/routers/ticker_insights.py`](../../backend/src/routers/ticker_insights.py), [`backend/src/services/insight_service.py`](../../backend/src/services/insight_service.py) |
| News aggregation | [`backend/src/routers/news.py`](../../backend/src/routers/news.py), [`backend/src/services/news.py`](../../backend/src/services/news.py) |
| Firestore I/O | [`backend/src/services/firestore_service.py`](../../backend/src/services/firestore_service.py) |
| Episode/podcast services | [`backend/src/services/podcast.py`](../../backend/src/services/podcast.py), [`backend/src/services/episode_transformer.py`](../../backend/src/services/episode_transformer.py) |
| GCS file fetch | [`backend/src/services/gcs_content.py`](../../backend/src/services/gcs_content.py) |

### Frontend

| Concern | File |
|---|---|
| Home feed | [`frontend/src/pages/HomeFeed.tsx`](../../frontend/src/pages/HomeFeed.tsx) |
| Episode detail (incl. comments widget) | [`frontend/src/pages/EpisodeDetail.tsx`](../../frontend/src/pages/EpisodeDetail.tsx) |
| Podcaster profile + index | [`frontend/src/pages/PodcasterPage.tsx`](../../frontend/src/pages/PodcasterPage.tsx), [`frontend/src/pages/PodcasterIndex.tsx`](../../frontend/src/pages/PodcasterIndex.tsx) |
| Watchlist (per-user latest episodes) | [`frontend/src/pages/WatchlistPage.tsx`](../../frontend/src/pages/WatchlistPage.tsx) |
| News redirect | [`frontend/src/pages/NewsRedirect.tsx`](../../frontend/src/pages/NewsRedirect.tsx) |
| Episode/podcast/home components | [`frontend/src/components/episode/`](../../frontend/src/components/episode/), [`frontend/src/components/podcast/`](../../frontend/src/components/podcast/), [`frontend/src/components/home/`](../../frontend/src/components/home/), [`frontend/src/components/player/`](../../frontend/src/components/player/) |
| API clients | [`frontend/src/services/api/podcasts.ts`](../../frontend/src/services/api/podcasts.ts), `episodes.ts`, `comments.ts`, `content.ts`, `news.ts` |

## Conventions

- **Firestore is the read source of truth.** The platform reads episodes/podcasts from Firestore (`graphfolio-db`). The agents pipeline (separate repo) is the only writer for the `episodes`, `tickers/*`, `tags/*`, `ticker_insights/*`, and `trending_tickers/*` collections. See [`../firestore-contract.md`](../firestore-contract.md) for the full schema.
- **Markdown content is cached in Firestore.** `events_markdown_content`, `sentences_markdown_content`, etc. mirror what `*_url` points to in GCS. Read inline first; fall back to GCS only when missing.
- **Cache pattern.** All read endpoints follow the `cache_get` → compute → `cache_set` pattern from [`backend/AGENTS.md`](../../backend/AGENTS.md#caching-pattern). Episode detail uses 1-hour TTL, recent episodes use 5-minute TTL (see HTTP `Cache-Control` headers).
- **Cross-tab player sync.** The Spotify player synchronizes state across browser tabs via `BroadcastChannel`. Episode change, seek, close, and open all propagate. See [`frontend/src/components/player/`](../../frontend/src/components/player/).
- **Comments require login.** The comments widget is gated by JWT auth — anonymous users see comments but cannot post.
- **Marp slide rendering.** When `marp_markdown_content` is present, render as a horizontally scrollable image carousel with a constrained height; clicking a slide opens a lightbox. Force a light background on the slide itself even in dark mode (slide text is black).
- **Modified-by-user fields are platform-owned.** The agents pipeline must NOT overwrite `modified_summary_url`, `modified_summary_content`, `modified_by`, `modified_at` on regeneration — these come from `PUT /api/podcast/{name}/episodes/{id}/summary`.

## Common pitfalls

- **`created_time` is immutable after first write.** Mutating it re-fires `new_episode` notifications. The agents-side regenerator must merge other fields without touching `created_time`.
- **`spotify_release_date` is sometimes a number, sometimes a string.** Frontend type is `string | number | null`. Spec wants string `YYYY-MM-DD`; normalize defensively when parsing.
- **Episode comments table schema and Comment Pydantic model can drift.** Recent commits (`e7f2348 fix(types): add missing Comment fields and CommentForm props to fix CI build`) point to this — add new fields to both `backend/src/database/comment_db.py` AND the model, plus the frontend `Comment` type, in the same change.
- **Don't bypass `episode_transformer.py`.** It normalizes raw Firestore docs into the canonical `Episode` shape. Adding a new field requires updating the transformer plus the Pydantic model plus the frontend type.
- **Two recommendation paths exist in parallel.** Legacy `/api/recommendations/*` (Postgres-backed, **soft-deprecated** — `deprecated=True`, kept as an alias for one release) and new `/api/ticker-insights/*` (Firestore-backed). New work goes through ticker-insights.

## External integrations

- **Firestore** `graphfolio-db` — episodes, podcasts, comments, ticker_insights, trending_tickers, users, notifications. Via service account JSON. See [`../firestore-contract.md`](../firestore-contract.md).
- **GCS bucket** `graphfolio-articles` — large markdown files, transcripts, Marp slides. URLs stored on episode docs as `*_url` (gs://) and `*_public_url` (HTTPS).
- **Spotify** — episode embed URLs, cover art images (`spotify_images[]`, smallest-first). No write integration; the agents pipeline ingests Spotify metadata upstream.
- **PostgreSQL** `podcast_db` — read-only, used by the legacy recommendation router only. Will be retired once the ticker_insights migration completes (see firestore-contract.md § 7).

## Cross-references

- Data contract: [`../firestore-contract.md`](../firestore-contract.md) (§2 episodes, §3 tickers/tags indices, §4 ticker_insights, §5 trending_tickers, §6 users/notifications)
- Workflow for schema changes: [`../workflows/firestore-data-change.md`](../workflows/firestore-data-change.md)
- Backend code style: [`../../backend/AGENTS.md`](../../backend/AGENTS.md)
- Frontend conventions (zh-TW, no emoji): [`../../frontend/AGENTS.md`](../../frontend/AGENTS.md)
