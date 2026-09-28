# Podcast domain

Tool-neutral reference for any agent (Claude Code, Codex, Cursor, etc.) working on episodes, podcasts, content, comments, recommendations, or news. For code style/conventions, defer to [`backend/AGENTS.md`](../../backend/AGENTS.md) and [`frontend/AGENTS.md`](../../frontend/AGENTS.md).

## Scope

This domain owns everything a user sees when consuming podcast content — the home feed, episode detail page, podcaster profiles, comments, and recommendation surfaces. The `pipelines/` tier writes episode content to VPS Postgres and media to VPS disk; the backend serves it through HTTP APIs.

Boundaries: stock-data, search, and the knowledge-graph visualizations are **separate domains** even though they appear inside episode pages — see [`stock-data.md`](./stock-data.md), [`search-discovery.md`](./search-discovery.md), [`graph-visuals.md`](./graph-visuals.md).

## Key files

### Backend

| Concern | File |
|---|---|
| Podcast/episode listing + detail API | [`backend/src/routers/podcast.py`](../../backend/src/routers/podcast.py), [`backend/src/routers/episodes.py`](../../backend/src/routers/episodes.py) |
| Content/article API (VPS disk-backed) | [`backend/src/routers/content.py`](../../backend/src/routers/content.py) |
| Episode comments | [`backend/src/routers/comments.py`](../../backend/src/routers/comments.py), [`backend/src/database/comment_db.py`](../../backend/src/database/comment_db.py) |
| Ticker insights (Postgres-backed) | [`backend/src/routers/ticker_insights.py`](../../backend/src/routers/ticker_insights.py), [`backend/src/services/insight_service.py`](../../backend/src/services/insight_service.py) |
| News aggregation | [`backend/src/routers/news.py`](../../backend/src/routers/news.py), [`backend/src/services/news.py`](../../backend/src/services/news.py) |
| Content reads | [`backend/src/services/postgres_mirror_service.py`](../../backend/src/services/postgres_mirror_service.py) |
| Episode/podcast services | [`backend/src/services/podcast.py`](../../backend/src/services/podcast.py), [`backend/src/services/episode_transformer.py`](../../backend/src/services/episode_transformer.py) |
| Local media file access (historical class name) | [`backend/src/services/gcs_content.py`](../../backend/src/services/gcs_content.py) |

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

- **Postgres is the content source of truth.** `pipelines/` writes `firestore_mirror.episodes`, `podcasts`, `ticker_insights`, and `trending_tickers` in `podcast_db`; the backend uses `content_read_service()`. The schema name is historical. See [`../firestore-contract.md`](../firestore-contract.md#current-state-2026-09-27).
- **Markdown may be inline or stored on VPS disk.** `*_markdown_content` fields can hold the body; `*_url` fields point to stable media URLs. Use the existing content service for fallback reads.
- **Cache pattern.** All read endpoints follow the `cache_get` → compute → `cache_set` pattern from [`backend/AGENTS.md`](../../backend/AGENTS.md#caching-pattern). Episode detail uses 1-hour TTL, recent episodes use 5-minute TTL (see HTTP `Cache-Control` headers).
- **Cross-tab player sync.** The Spotify player synchronizes state across browser tabs via `BroadcastChannel`. Episode change, seek, close, and open all propagate. See [`frontend/src/components/player/`](../../frontend/src/components/player/).
- **Comments require login.** The comments widget is gated by JWT auth — anonymous users see comments but cannot post.
- **Marp slide rendering.** When `marp_markdown_content` is present, render as a horizontally scrollable image carousel with a constrained height; clicking a slide opens a lightbox. Force a light background on the slide itself even in dark mode (slide text is black).
- **Modified-by-user fields are platform-owned.** The agents pipeline must NOT overwrite `modified_summary_url`, `modified_summary_content`, `modified_by`, `modified_at` on regeneration — these come from `PUT /api/podcast/{name}/episodes/{id}/summary`.

## Common pitfalls

- **`created_time` is immutable after first write.** The pipeline merge preserves it. Notification fan-out uses the separate Postgres `first_seen_at` insertion timestamp.
- **`spotify_release_date` is sometimes a number, sometimes a string.** Frontend type is `string | number | null`. Spec wants string `YYYY-MM-DD`; normalize defensively when parsing.
- **Episode comments table schema and Comment Pydantic model can drift.** Recent commits (`e7f2348 fix(types): add missing Comment fields and CommentForm props to fix CI build`) point to this — add new fields to both `backend/src/database/comment_db.py` AND the model, plus the frontend `Comment` type, in the same change.
- **Don't bypass `episode_transformer.py`.** It normalizes stored episode JSON into the canonical `Episode` shape. Adding a new field requires updating the transformer plus the Pydantic model plus the frontend type.
- **Ticker insights have one read path.** The legacy `/api/recommendations/*` aliases (flat Postgres `ticker_insights` table, which never existed on the VPS) were removed 2026-09-06; `/api/ticker-insights/*` reads `firestore_mirror.ticker_insights` via `content_read_service()`.

## Financial content rules

> Migrated 2026-07-04 from the root `AGENTS.md`.

Tinboker can provide market intelligence and source-grounded summaries. Avoid creating
output that sounds like direct investment advice.

Use language such as: "mentioned by podcasts", "historical performance after mention",
"possible bull case", "possible bear case", "risk factors", "not investment advice".

Avoid first-version output such as: "buy", "sell", "target price", "guaranteed",
"must enter", "sure win".

## External integrations

- **Postgres** `podcast_db` — shared by deployed environments for content, users, notifications, and platform SQL tables. Local development may use SQLite for supported platform tables; check the specific service before changing its storage.
- **VPS media disk** `/srv/tinboker-media` — markdown, transcripts, slides, and other artifacts served through `/media`. `graphfolio-articles` is a directory segment retained from old URLs.
- **Spotify** — episode embed URLs, cover art images (`spotify_images[]`, smallest-first). No write integration; the agents pipeline ingests Spotify metadata upstream.

## Cross-references

- Data contract: [`../firestore-contract.md`](../firestore-contract.md) (§2 episodes, §3 tickers/tags indices, §4 ticker_insights, §5 trending_tickers, §6 users/notifications)
- Workflow for shared-data changes: [`../workflows/firestore-data-change.md`](../workflows/firestore-data-change.md)
- Backend code style: [`../../backend/AGENTS.md`](../../backend/AGENTS.md)
- Frontend conventions (zh-TW, no emoji): [`../../frontend/AGENTS.md`](../../frontend/AGENTS.md)
