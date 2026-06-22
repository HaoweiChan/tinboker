# Firestore data contract

> **This is the authoritative data contract between the backend (`backend/`, reader) and the content pipelines (`pipelines/`, writer) — two tiers of this monorepo.** Edits here require coordination across both tiers.
>
> **Status:** Authoritative. § 10 now records accepted implementation decisions rather than open blockers. (Originally drafted when `pipelines/` was the separate `tinboker-agents` repo; the two are now merged, but the reader/writer boundary still holds.)
> **Owners:** the `backend/` (platform) tier owns this doc; the `pipelines/` tier owns the write contract.
> **Doc location:** `docs/firestore-contract.md` (moved from `openspecs/firestore-schema/spec.md`).
> **Document version:** see `schema_version: 3` in § Scope. Bump `schema_version` inline rather than forking the doc.

---

## Purpose

This spec is the **data contract between the content pipelines (`pipelines/`, writer) and the backend (`backend/`, reader)** for everything that flows through Firestore.

Today the platform infers the agents' shape from production traffic. That arrangement is breaking down:

1. **Stock Index is empty in production.** Probes on 2026-05-13:
   - `GET https://api.tinboker.com/api/recommendations/buzz?days=30&limit=100` → `[]`
   - `GET https://api.tinboker.com/api/recommendations/buzz?days=365&limit=100` → `[]`
   - `GET https://api.tinboker.com/api/recommendations/by-ticker/{NVDA|2330|AAPL}` → `[]`
   - Root cause from `/health`: `recommendation_db: pool_not_initialized`, main Postgres DNS error `could not translate host name "docker-db_postgres-1"`. Firestore-backed endpoints (`/api/podcast`, `/api/episodes/recent`) are fine.
   - **Implication:** the `ticker_recommendations` Postgres table is unreachable in prod. Moving this data to Firestore isn't an optimization — it's the actual fix.

2. **The `episodes` document shape isn't written down anywhere.** Field-level expectations (which are required, which are sometimes-omitted, which are stale) live in tribal knowledge and in the [backend Pydantic model](../backend/src/models/podcast.py), but the agents team has no contract to write against.

This doc replaces that arrangement. It enumerates every Firestore path the platform reads or writes, lists every field with type and fulfillment expectation, and defines the exact JSON shape each public-facing endpoint must return.

---

## Scope

**In scope (agents must fulfill):**
- `episodes/{episode_id}` (existing — documented and lightly cleaned up)
- `tickers/{ticker}/episodes/*` (existing inverted index — documented)
- `tags/{tag}/episodes/*` (existing inverted index — documented)
- `ticker_insights/{episode_id}/tickers/{ticker}` (new — replaces Postgres `ticker_recommendations`)
- `trending_tickers/{ticker}` (new — replaces Postgres-backed `/buzz` aggregate)
- Sector/theme exposure fields embedded on `episodes/{episode_id}` (new metadata layer; no standalone `sectors/*` or `themes/*` collections yet)

**In scope (platform-owned, listed for completeness):**
- `users/{user_id}`
- `users/{user_id}/notifications/{notification_id}`

**Out of scope — agents are NOT on the hook for these:**
- Live market data: `price`, `change`, `changePercent`, `marketCap`, `volume`, `pe`, `dividendYield`, `chartData[]`. Source: FinMind (TW) and Massive API (US) via the backend's `stock_service`.
- User state: `watchlist`, `podcast_subscriptions`, `episode_bookmarks`, `alerts`, `tag_subscriptions`, `notification_preferences`. Platform-owned writes.
- Top Movers / sector heatmaps (currently mocked). These come from market price feeds.

**Versioning:** every agent-written document carries a `schema_version: <int>` field. This doc defines `schema_version: 3`. Bumping the integer requires updating this spec.

**Terminology:** "the agents pipeline" / "the pipelines tier" = `pipelines/` (the content/agent backend, formerly the separate `tinboker-agents` repo). "The platform" = `backend/` + `frontend/`. All now live in this one `tinboker` monorepo; the writer/reader split is a tier boundary, not a repo boundary.

---

## § 1. Ownership matrix

| Path | Writer | Reader(s) | Lifecycle | Section |
|------|--------|-----------|-----------|---------|
| `episodes/{episode_id}` | agents (full doc); platform (`modified_summary_*` only) | backend `podcast_service`; all episode-consuming UI | one doc/episode, mutable | § 2 |
| `tickers/{ticker}/episodes/*` | agents | backend `get_episodes_by_ticker` | append-only index | § 3 |
| `tags/{tag}/episodes/*` | agents | backend tag pages, `get_all_tags` | append-only index | § 3 |
| `ticker_insights/{episode_id}/tickers/{ticker}` | agents | backend `/api/ticker-insights/by-ticker/{ticker}`, `/by-podcaster/{name}`; `StockDashboard`, `TickerInsightCard` | one doc/(episode,ticker), mutable | § 4 |
| `trending_tickers/{ticker}` | agents (hourly delta job + full backfill mode) | backend `/api/ticker-insights/trending`; `StockIndex`, `WeeklyBuzzWidget`, `HomeRail` | rolling, recomputed for touched tickers | § 5 |
| `users/{user_id}` | **platform** | platform only | per-user lifecycle | § 6 |
| `users/{user_id}/notifications/{notification_id}` | **platform** | platform only | append + cleanup | § 6 |

---

## § 2. `episodes/{episode_id}` — canonical document

Authoritative reference: [backend/src/models/podcast.py:8-71](../backend/src/models/podcast.py#L8-L71). Every field below must appear in that Pydantic model; if the model changes, this spec is the contract being broken.

### 2.1 Field catalog

Legend for **Fulfilled by agents**:
- `always` — every episode doc must have this field set (non-null, non-empty for collections).
- `usually` — present in ≥ 90% of episodes; missing only when source data lacks it.
- `sometimes` — opportunistic; agents populate when available, platform tolerates absence.
- `never` — agents must not write this field (platform-owned).

#### Identity (always)

| Field | Type | Fulfilled | Notes |
|------|------|-----------|-------|
| `id` | string | always | Doc ID. Stable, opaque. Used as foreign key in indices. |
| `podcast_name` | string | always | Used as the de-facto "podcast" entity ID — the `Podcast` aggregate is computed from this. Must be stable; renaming a podcast breaks all subscriptions. |
| `episode_title` | string \| null | usually | |
| `episode_number` | int \| null | usually | |

#### Content (text)

| Field | Type | Fulfilled | Notes |
|------|------|-----------|-------|
| `transcript` | string \| null | sometimes | Raw transcript text. Large field — agents may omit from list responses and only populate on detail fetches via the GCS URL. |
| `summary_content` | string \| null | always | Markdown summary. Primary teaser text for HomeFeed/EpisodeDetail. |
| `summary_image` | string \| null | sometimes | SVG markup. |
| `key_insights` | string[] | **required** | 3–8 plain-text bullet takeaways, no markdown — the episode's precomputed "essence". Rendered on EpisodeDetail **and** as the primary content of `EpisodeCardV2` across all browsing pages (HomeFeed / Podcaster / Tag / Stock / Watchlist / Profile). Those list views deliberately do **not** hydrate `summary_content` (perf — transcripts are large), so `key_insights` is the only insight source available to cards. Agents must populate this on every processed, non-placeholder episode; the pipeline uses deterministic markdown fallback when LLM extraction is sparse or fails. |
| `raw_mp3` | string \| null | never (local-dev only) | Present in the Pydantic model as a local filesystem path used during agent processing; **not stored in Firestore** in production. Listed here only to match the model contract; agents must omit when writing to Firestore. |

#### Metadata

| Field | Type | Fulfilled | Notes |
|------|------|-----------|-------|
| `related_tickers` | string[] | always (may be empty) | Symbol-only. Mixed TW/US OK. Used by `tickers/{ticker}/episodes` index hydration. |
| `tags` | string[] | always (may be empty) | Topic tags (e.g. `法說`, `AI`, `科技`). Used by `tags/{tag}/episodes` index hydration. |
| `created_time` | int (Unix ms) | always | **Immutable after first write.** The notification fan-out service uses this to detect new episodes; mutating it re-fires notifications. |
| `released_at_ms` | int (Unix ms) | partial → **must become `always`** | True episode **publish** time. **Now consumed by the platform** (backend `Episode` model + transformer; frontend display + the release recency filter). Already written by agents but currently derived from `spotify_release_date` → `created_time`, so it is unreliable (null/ingestion-time) whenever Spotify is unmatched. **Required fix:** source it from the feed's `datePublished` (already fetched by the pipeline). See § 2.3 cleanup #1. |
| `number_click` | int | always | Default 0; agents seed, platform updates. |
| `num_likes` | int | always | Default 0; agents seed, platform updates. |
| `retracted_at` | int \| null | sometimes | Soft-delete/retraction marker. `null`/missing means active; Unix ms means the episode was retracted at that time. Agents should keep the episode doc in place so inverted indices and foreign keys do not break. |

#### Sector/theme exposure metadata

These fields are inferred metadata only. They MUST NOT be copied into `related_tickers`, `tickers/{ticker}/episodes/*`, or company-level `ticker_insights`; direct ticker mentions remain the only source for watchlist notifications and stock-page episode membership.

| Field | Type | Fulfilled | Notes |
|------|------|-----------|-------|
| `sector_exposures` | object[] | always (may be empty) | Resolved sector/theme mentions from clustered podcast events. Uses capped representative baskets, not exhaustive ticker expansion. See § 2.1.1. |
| `sector_exposure_ids` | string[] | always (may be empty) | Flat companion array for Firestore `array-contains` filters. Contains both sector and theme exposure IDs. |
| `sector_ids` | string[] | always (may be empty) | Flat sector-only IDs for future filtering. |
| `theme_ids` | string[] | always (may be empty) | Flat theme-only IDs for future filtering. |
| `unresolved_market_trends` | object[] | always (may be empty) | Plausible but unmapped emerging market concepts for demand-driven curation. |
| `unresolved_market_trend_ids` | string[] | always (may be empty) | Normalized unresolved trend IDs for aggregation/filtering. |

##### 2.1.1 `sector_exposures[]` object shape

```jsonc
{
  "exposure_id": "theme_ai_server",
  "exposure_type": "theme",              // sector | theme
  "sector_id": null,
  "theme_id": "ai_server",
  "display_name": "AI 伺服器",
  "mention_text": "AI 伺服器",
  "confidence": 1.0,
  "start_index": 120,
  "end_index": 145,
  "start_time": 530000,
  "end_time": 552000,
  "resolved_tickers": [
    { "ticker": "2382", "name": "廣達", "market": "TW", "source": "curated" },
    { "ticker": "NVDA", "name": "NVIDIA", "market": "US", "source": "issuer_etf" }
  ],
  "total_matches": 18
}
```

Rules:
- `resolved_tickers` supports `market: "TW" | "US"` and is capped to at most 10 members per exposure to avoid API payload bloat.
- `total_matches` preserves the full candidate count before the cap.
- Deterministic exact keyword/alias matches use `confidence: 1.0`. Fuzzy or semantic extraction must use a calculated confidence score and retain provenance.
- Runtime extraction reads the compiled `sector_and_theme_universe.json` artifact only. Static compilation/curation may use FinMind, official ETF issuer CSVs, and reviewed `curated_themes.json`, but request-time extraction must stay offline.
- Matching uses Chinese/English normalization, many-to-many alias mapping, and longest-match-first matching.

##### 2.1.2 `unresolved_market_trends[]` object shape

```jsonc
{
  "mention_text": "CPO",
  "normalized_text": "cpo",
  "context": "主持人提到 CPO 會帶動下一波光通訊需求",
  "start_time": 840000,
  "confidence": 0.74
}
```

#### File pointers — GCS gs:// URLs

| Field | Type | Fulfilled | Notes |
|------|------|-----------|-------|
| `mp3_url` | string \| null | always | |
| `transcript_url` | string \| null | usually | |
| `summary_url` | string \| null | always | |
| `summary_image_url` | string \| null | sometimes | |
| `events_markdown_url` | string \| null | usually | |
| `sentences_markdown_url` | string \| null | usually | |
| `marp_markdown_url` | string \| null | sometimes | |
| `ticker_marp_markdown_url` | string \| null | sometimes | |
| `ticker_insights_url` | string \| null | usually | JSON of per-ticker insights. Source for `ticker_insights/*` documents (§ 4). Historical docs may still carry `ticker_recommendations_url`; readers map it as a legacy fallback only. |

#### File pointers — public HTTPS URLs

Each `*_url` above has an optional `*_public_url` counterpart. Backend reads from `*_public_url` first when present. **See § 2.3 cleanup #2** — these are proposed for deprecation pending audit.

#### Inlined markdown content (cache layer)

| Field | Type | Fulfilled | Notes |
|------|------|-----------|-------|
| `events_markdown_content` | string \| null | usually | Markdown with `(#time: MSEC)` chapter markers. Cached in Firestore so the frontend doesn't fetch GCS per page load. |
| `sentences_markdown_content` | string \| null | usually | Markdown with `(#time: MSEC)` clip markers. |
| `marp_markdown_content` | string \| null | sometimes | |
| `ticker_marp_markdown_content` | string \| null | sometimes | |
| `ticker_insights_content` | string \| null | usually | JSON-as-string cache of the per-ticker insights payload. Historical docs may still carry `ticker_recommendations_content`; readers map it as a legacy fallback only. Superseded by `ticker_insights/*` collection (§ 4) post-migration. |

#### Spotify metadata

| Field | Type | Fulfilled | Notes |
|------|------|-----------|-------|
| `spotify_embed_url` | string \| null | usually | |
| `spotify_id` | string \| null | usually | |
| `spotify_url` | string \| null | usually | |
| `spotify_release_date` | string \| null | usually | `YYYY-MM-DD`. **Mixed type today** — string OR number; spec requires string. |
| `spotify_description` | string \| null | sometimes | |
| `spotify_duration_ms` | int \| null | usually | |
| `spotify_images` | string[] | usually | List of cover image URLs, smallest-first. |

#### Platform-owned (agents MUST NOT write)

| Field | Type | Notes |
|------|------|-------|
| `modified_summary_url` | string \| null | User edit to summary. Written by `PUT /api/podcast/{name}/episodes/{id}/summary`. |
| `modified_summary_content` | string \| null | Inline content of user-edited summary. |
| `modified_by` | string \| null | Email/ID of editing user. |
| `modified_at` | int (Unix ms) \| null | Edit timestamp. |

Regenerating an episode in the agents pipeline must **preserve** these fields. The platform reads `modified_summary_content` in preference to `summary_content` when both are present.

### 2.2 Per-surface field consumption

This table maps every UI surface to the subset of episode fields it actually reads. Source: walk of `frontend/src/pages/*` and `frontend/src/components/redesign/*`. Fields not listed here are not consumed by any UI today — they may still be required for backend logic.

| Surface | File | Required fields |
|---|---|---|
| HomeFeed (+ all `EpisodeCardV2` lists) | [frontend/src/pages/HomeFeed.tsx](../frontend/src/pages/HomeFeed.tsx), [frontend/src/components/redesign/EpisodeCardV2.tsx](../frontend/src/components/redesign/EpisodeCardV2.tsx) | `id`, `podcast_name`, `episode_title`, `episode_number`, `released_at_ms` (preferred for display) ∥ `spotify_release_date` ∥ `created_time`, `key_insights` (card essence; falls back to `summary_content` ∥ `modified_summary_content`), `related_tickers`, `tags`, `num_likes`, `number_click`, `spotify_images` |
| EpisodeDetail | [frontend/src/pages/EpisodeDetail.tsx](../frontend/src/pages/EpisodeDetail.tsx) | HomeFeed + `key_insights`, `events_markdown_content`, `sentences_markdown_content`, `spotify_id`, `spotify_url`, `spotify_embed_url` |
| StockDashboard ("Mentioned in episodes") | [frontend/src/pages/StockDashboard.tsx](../frontend/src/pages/StockDashboard.tsx) | HomeFeed subset, filtered by `related_tickers` |
| TagPage | [frontend/src/pages/TagPage.tsx](../frontend/src/pages/TagPage.tsx) | HomeFeed subset, filtered by `tags` |
| PodcasterPage | [frontend/src/pages/PodcasterPage.tsx](../frontend/src/pages/PodcasterPage.tsx) | HomeFeed subset, filtered by `podcast_name` |
| WatchlistPage | [frontend/src/pages/WatchlistPage.tsx](../frontend/src/pages/WatchlistPage.tsx) | HomeFeed subset (latest 3 per subscribed podcast) |
| ProfilePage (My Subscriptions tab) | [frontend/src/pages/ProfilePage.tsx](../frontend/src/pages/ProfilePage.tsx) | HomeFeed subset |
| PodcasterIndex | [frontend/src/pages/PodcasterIndex.tsx](../frontend/src/pages/PodcasterIndex.tsx) | Aggregated only: `podcast_name`, `created_time`, `spotify_images[0]` (for cover) |

### 2.3 Targeted cleanup status

These are contract cleanups tracked across platform and pipeline work.

1. **Timestamp normalization — `released_at_ms` from the feed publish date.** Status: **pipeline write path implemented for new episodes**. The pipeline wires feed `datePublished` into `released_at_ms` and uses it as the creation-time fallback when Spotify is absent. Existing episodes still require the historical feed-driven backfill before the platform can safely enable `RELEASE_EPISODE_MAX_AGE_DAYS`. **Do NOT mutate `created_time` on existing episodes** (§ 6.3) — only set `released_at_ms`.

2. **Audit the `*_url` / `*_public_url` pairs.** The Episode model defines both `gs://` and HTTPS variants for each artifact. Most of the time the backend hydrates content via `episode_transformer.py` from `*_content` directly. We propose:
   - Drop the `*_public_url` half of every pair where the backend can sign GCS URLs on demand.
   - Keep both only for fields the frontend fetches directly without backend mediation.
   - Action: a separate sub-doc auditing each pair's usage; merge with this spec or land alongside.

3. **`modified_*` is platform-only.** Agents pipeline must not overwrite `modified_summary_url`, `modified_summary_content`, `modified_by`, `modified_at` during regenerations. Spec requires agents to perform Firestore writes with `merge=True` *excluding* these fields. Pipeline episode update/regeneration paths enforce this; backend writes already use `merge=True` for adds and `DELETE_FIELD` for removals.

4. **`*_content` fields are a cache, not a source.** Document that inlined markdown duplicates what `*_url` points to. Staleness rule: when agents regenerate the GCS file, they MUST also rewrite the matching `*_content` field in the same Firestore commit. Otherwise readers see drift.

5. **`spotify_release_date` typed as string.** Backend model declares `Optional[str]` but production data sometimes contains numbers (per frontend type `string | number | null`). Spec mandates string `YYYY-MM-DD`; agents normalize on write for all new/updated episode docs.

---

## § 3. `tickers/{ticker}/episodes/*` and `tags/{tag}/episodes/*` — inverted indices

Read-only indices written by the agents pipeline. The platform queries these to answer "which episodes mention ticker X" or "which episodes have tag Y" without scanning the full `episodes` collection.

### 3.1 Document shape

For both collections, each child document references an episode:

```jsonc
{
  "episode_id": "ep_abc123",     // foreign key into episodes/{episode_id}
  "created_time": 1730000000000  // mirrors episode created_time; used for ORDER BY
}
```

Agents may write additional fields; backend reads only `episode_id` and `created_time`. The episode itself is the source of truth — anything else here is denormalized cache.

### 3.2 Invariants

- Every entry in `episodes/{id}.related_tickers` must produce a corresponding `tickers/{ticker}/episodes/{auto_id}` doc.
- Every entry in `episodes/{id}.tags` must produce a corresponding `tags/{tag}/episodes/{auto_id}` doc.
- Removing a ticker/tag from an episode requires the agents pipeline to also remove the matching index entry.
- These indices are NOT used to gate notifications. The notification fan-out service reads `episodes` directly, querying by `array_contains` on `related_tickers` and on `users.watchlist` / `users.podcast_subscriptions`.

---

## § 4. `ticker_insights/{episode_id}/tickers/{ticker}` — per-episode ticker insights (NEW)

This replaces the Postgres `ticker_recommendations` table. Renamed end-to-end from "recommendations" → "ticker insights" — matches the existing [TickerInsightCard.tsx](../frontend/src/components/financial/TickerInsightCard.tsx) UI component, avoids regulated investment-advice terminology, and reads more naturally ("NVDA insights from this episode").

### 4.1 Document schema

```jsonc
{
  "schema_version": 3,
  "episode_id": "ep_abc123",
  "podcaster": "股癌",
  "podcast_launch_time": "2026-05-12T08:30:00Z",   // ISO 8601 UTC
  "ticker": "NVDA",
  "market": "US",                                  // internal namespace: TW | US | other future market
  "bluf_thesis": "AI capex cycle has another 4-6 quarters of upside.",
  "time_horizon": "中期",                            // 短期 | 中期 | 長期

  // Sentiment — sentiment_score is INTERNAL ONLY. Stays in Firestore for sort/aggregation;
  // public API responses MUST NOT return it. Frontends consume sentiment_label only.
  "sentiment_score": 0.78,                           // internal — 0.0–1.0, do not expose
  "sentiment_label": "BULLISH",                      // 5-tier enum, see § 4.2

  "reasons": [
    {
      "title": "Hyperscaler 2026 capex guidance",
      "category": "fundamental",
      "description": "...",
      "start_time": 1235000,                         // ms from episode start
      "end_time": 1305000,
      "start_index": 4210,                           // transcript char offset (inclusive)
      "end_index": 4480                              // transcript char offset (exclusive)
    }
  ],
  "risks": [
    {
      "title": "China export controls",
      "severity": "MEDIUM",                          // HIGH | MEDIUM | LOW
      "description": "...",
      "start_time": 1820000,
      "end_time": 1880000,
      "start_index": 5630,
      "end_index": 5790
    }
  ],

  "created_at": "2026-05-13T03:14:00Z"               // ISO 8601 UTC, agent-write timestamp
}
```

Field set mirrors today's Postgres shape at [backend/src/database/recommendation_queries.py:20-35](../backend/src/database/recommendation_queries.py#L20-L35) and the frontend type at [frontend/src/services/types.ts:456-469](../frontend/src/services/types.ts#L456-L469), with these differences:

- **Removed from public API** (kept in Firestore for internal sort): the raw `sentiment_score` float.
- **Replaced**: freeform `sentiment` string (`"bull"`/`"bear"`/`"neut"`) → 5-tier `sentiment_label` enum.
- **Added**: `schema_version: 3`.
- **Added internal**: `market` for multi-market namespace segregation. Public APIs may omit it unless a future UI needs market-specific display.
- **Removed**: the auto-increment `id` column (replaced by composite doc path `{episode_id}/tickers/{ticker}`).

### 4.2 Sentiment label enum

```
STRONG_BULLISH | BULLISH | NEUTRAL | BEARISH | STRONG_BEARISH
```

The raw `sentiment_score` is model-generated and its quantized value isn't meaningful to users. Spec **forbids** rendering the float on the UI. Public API responses omit it. Backend uses the float only for sort/order on `sentiment_label` ties.

**Score-to-label cutoffs** (implemented in the pipeline post-processing layer before Firestore write):

| sentiment_score | sentiment_label |
|---|---|
| ≥ 0.80 | `STRONG_BULLISH` |
| 0.60 – 0.79 | `BULLISH` |
| 0.40 – 0.59 | `NEUTRAL` |
| 0.20 – 0.39 | `BEARISH` |
| < 0.20 | `STRONG_BEARISH` |

### 4.3 Public API response shape — `TickerInsight[]`

The platform exposes these as `TickerInsight[]`:

```ts
type TickerInsight = {
  episode_id: string;
  podcaster?: string;
  podcast_launch_time: string;     // ISO 8601
  ticker: string;
  bluf_thesis: string;
  time_horizon: string;            // 短期 | 中期 | 長期
  sentiment_label:
    | 'STRONG_BULLISH'
    | 'BULLISH'
    | 'NEUTRAL'
    | 'BEARISH'
    | 'STRONG_BEARISH';
  reasons: Reason[];
  risks: Risk[];
  created_at: string;              // ISO 8601
};

type Reason = {
  title: string;
  category?: string;
  description: string;
  start_time: number;              // ms
  end_time: number;
  start_index: number;
  end_index: number;
};

type Risk = {
  title: string;
  severity?: 'HIGH' | 'MEDIUM' | 'LOW';
  description: string;
  start_time: number;              // ms
  end_time: number;
  start_index: number;
  end_index: number;
};
```

Notable differences from today's [frontend/src/services/types.ts:436-469](../frontend/src/services/types.ts#L436-L469): `id` removed, `sentiment_score` removed, `sentiment` (string) → `sentiment_label` (5-tier enum), `severity` typed as enum.

### 4.4 Public API endpoints

| Method | Path | Replaces | Response |
|--------|------|----------|----------|
| GET | `/api/ticker-insights/by-ticker/{ticker}` | `/api/recommendations/by-ticker/{ticker}` | `TickerInsight[]` |
| GET | `/api/ticker-insights/by-podcaster/{name}` | `/api/recommendations/by-podcaster/{name}` | `TickerInsight[]` |

Query params identical to existing endpoints: `start_date`, `end_date` (ISO `YYYY-MM-DD`; defaults to last 7 days), and for `by-podcaster` also `podcast_slug`. Caching unchanged (5-min CDN).

Old `/api/recommendations/*` paths remain as deprecation aliases for one release with a `Deprecation: true` header and a log line. Removed in the release after.

### 4.5 Backend rename status

- Current reader: `backend/src/services/insight_service.py`, `backend/src/routers/ticker_insights.py`, prefix `/api/ticker-insights`.
- Deprecated aliases: `backend/src/routers/recommendations.py` keeps `/api/recommendations/*` with deprecation headers for one release.
- Legacy Postgres cleanup: delete `backend/src/database/recommendation_queries.py`, `backend/src/database/recommendation_db.py`, and the old `ticker_recommendations` table once § 7 Phase B6 completes.

### 4.6 Frontend rename status

- Active service functions: `getInsightsByTicker`, `getInsightsByPodcaster`, `getTrendingTickers`.
- Active types: `TickerInsight`, `TickerTrending` (see § 5).
- Removed compatibility wrapper: `frontend/src/services/recommendationService.ts`.
- Consumers:
  - [frontend/src/components/financial/WeeklyBuzzWidget.tsx](../frontend/src/components/financial/WeeklyBuzzWidget.tsx)
  - [frontend/src/components/financial/TickerInsightCard.tsx](../frontend/src/components/financial/TickerInsightCard.tsx)
  - [frontend/src/pages/StockIndex.tsx](../frontend/src/pages/StockIndex.tsx)
  - [frontend/src/pages/StockDashboard.tsx](../frontend/src/pages/StockDashboard.tsx)
  - [frontend/src/components/redesign/HomeRail.tsx](../frontend/src/components/redesign/HomeRail.tsx)

---

## § 5. `trending_tickers/{ticker}` — Stock Index aggregate (NEW)

This replaces the on-the-fly Postgres aggregation that powers `/api/recommendations/buzz`. Agents refresh this collection hourly via a localized delta job: recent `ticker_insights/*/tickers/*` writes identify touched `(ticker, market)` pairs, then only those tickers are recomputed from their historical source rows. A full recompute mode remains available for backfills/audits.

### 5.1 Document schema

```jsonc
{
  "ticker": "NVDA",                          // canonical ticker token
  "market": "US",                            // internal namespace; TW | US today
  "schema_version": 3,

  // Rolling mention counts. Three windows so frontends can switch without re-aggregating.
  "count_30d": 7,
  "count_90d": 19,
  "count_all_time": 64,

  // Aggregated sentiment over the longest window with at least 1 mention.
  // sentiment_score is INTERNAL ONLY (see § 4.2).
  "sentiment_score": 0.72,                   // internal — 0.0–1.0, do not expose
  "sentiment_label": "STRONG_BULLISH",       // 5-tier enum (§ 4.2)

  // Drives "last mentioned" column on StockIndex.
  "last_mentioned": "2026-05-12T08:30:00Z",  // ISO 8601 UTC

  // Optional denormalized tail — lets UI show top contributors without a join.
  "top_podcasters": [
    { "name": "股癌", "count": 4 },
    { "name": "M觀點", "count": 2 }
  ],
  "top_episodes": [
    {
      "episode_id": "ep_abc123",
      "podcast_name": "股癌",
      "launch_time": "2026-05-12T08:30:00Z"
    }
  ],

  "computed_at": "2026-05-14T00:00:00Z"      // when this doc was last rewritten
}
```

Document ID rule:
- Normal case: the document ID is the canonical `ticker` token, preserving the existing `trending_tickers/{ticker}` path.
- US tickers are always written with the exact ticker token as the document ID.
- Non-US documents always use the deterministic fallback `{ticker}.{market}` (for example, `2330.TW`) to keep the single-string Firestore path namespace-safe. The document body still carries `ticker` and `market` separately.
- Aggregation must reject ticker tokens with unknown market metadata rather than committing ambiguous documents.

### 5.2 Public API endpoint

| Method | Path | Replaces | Response |
|--------|------|----------|----------|
| GET | `/api/ticker-insights/trending` | `/api/recommendations/buzz` | `TickerTrending[]` |

Query params:
- `days`: `30` (default) | `90` | `0` (= all-time). Selects which `count_*` field drives sorting and is returned.
- `limit`: 1–200 (default 100). **Note:** the existing `/buzz` endpoint caps at 100; spec raises the cap to 200 to address sparsity on StockIndex.

### 5.3 Response shape — `TickerTrending`

```ts
type TickerTrending = {
  ticker: string;
  count: number;                   // count_{days}d, or count_all_time when days=0
  sentiment_label:
    | 'STRONG_BULLISH'
    | 'BULLISH'
    | 'NEUTRAL'
    | 'BEARISH'
    | 'STRONG_BEARISH';
  last_mentioned: string;          // ISO 8601 UTC
};
```

`sentiment_score` is removed from the public response; `sentiment_label` is the user-facing enum. Frontend code consumes this as `TickerTrending`.

`top_podcasters` and `top_episodes` are stored in Firestore but NOT returned by the public API today. They unlock future UI surfaces (e.g. a hover card on Stock Index showing "mentioned by 股癌, M觀點") without re-spec'ing.

### 5.4 StockIndex page changes

- Default query becomes `?days=90&limit=200` (was `?days=30&limit=80`). Justification: production probes on 2026-05-13 returned 0 rows for every window — the page is empty. Moving the data to Firestore via § 5 unblocks it; the wider default reduces the chance of recurrence.
- The "sort by sentiment" segmented control sorts on the backend using the internal `sentiment_score`; the frontend never sees the number.

---

## § 6. Platform-owned paths (for completeness)

Agents have no obligation to fulfill these — listed so the doc is the full inventory of Firestore paths.

### 6.1 `users/{user_id}`

Schema at [backend/src/models/user.py:29-43](../backend/src/models/user.py#L29-L43). Fields:
`id`, `google_id`, `email`, `name`, `avatar`, `email_verified`, `created_at`, `updated_at`, `watchlist[]`, `podcast_subscriptions[]`, `episode_bookmarks[]`, `alerts[]`, `tag_subscriptions[]`, `notification_preferences{new_episodes, stock_mentions, price_alerts, daily_digest}`.

### 6.2 `users/{user_id}/notifications/{notification_id}`

Schema at [backend/src/models/notification.py:17-38](../backend/src/models/notification.py#L17-L38). Fields: `id`, `user_id`, `type` (`new_episode` | `stock_mention` | `price_alert`), `title`, `body`, `data{...}`, `is_read`, `created_at`.

### 6.3 Cross-team contract: notification triggers

The notification fan-out service ([backend/src/services/notification_service.py](../backend/src/services/notification_service.py)) is triggered by new episode writes. The contract:

- A document arriving at `episodes/{id}` with a never-before-seen `created_time` triggers `new_episode` notifications for every user with that `podcast_name` in `podcast_subscriptions`, and `stock_mention` notifications for every user whose `watchlist` overlaps `related_tickers`.
- **Therefore agents MUST NOT mutate `created_time` on existing episodes.** Doing so would re-fire notifications.
- Sector/theme-derived `resolved_tickers` are inferred exposure metadata only and MUST NOT trigger `stock_mention` notifications unless the ticker is also present in `related_tickers`.
- Retracted episodes should be marked with `retracted_at`; the episode doc remains in place so notification and index foreign keys do not break.
- Agents MAY update other fields freely (re-summarization, transcript corrections, ticker re-extraction).

---

## § 7. Migration plan

This is the rollout sequence. Each phase has agent-team and platform-team owners. **Dates left blank for the agents team to fill in during review.**

### Phase A — `trending_tickers` (unblocks Stock Index)

Highest priority. Stock Index is empty in production today because the Postgres `ticker_recommendations` DB pool is uninitialized (`/health` reports `pool_not_initialized` as of 2026-05-13). Moving this aggregate to Firestore fixes it.

| Step | Owner | Target | Notes |
|------|-------|--------|-------|
| A1. Agents wire up hourly delta job writing `trending_tickers/{ticker}` | pipelines | implemented | Default mode recomputes only touched tickers from recent `ticker_insights` writes; full mode remains for audits/backfills. |
| A2. Platform adds `/api/ticker-insights/trending` reading from Firestore, behind feature flag `TICKER_INSIGHTS_FROM_FIRESTORE` | platform | TBD | Old `/api/recommendations/buzz` keeps working. |
| A3. Frontend switches StockIndex/WeeklyBuzzWidget/HomeRail to new endpoint | platform | TBD | Type is `TickerTrending`. |
| A4. Flip feature flag in prod, observe for 48h | both | TBD | Rollback = flip flag off; old code path remains. |
| A5. Remove old `/api/recommendations/buzz` endpoint | platform | TBD | After 1 full release of green flag. |

### Phase B — `ticker_insights` (replaces per-episode Postgres recs)

| Step | Owner | Target | Notes |
|------|-------|--------|-------|
| B1. Agents dual-write (Postgres + Firestore) for new episodes | pipelines | implemented | Firestore write path uses `ticker_insights/{episode_id}/tickers/{ticker}` and `WriteBatch` grouped by episode. |
| B2. Agents backfill historical episodes to `ticker_insights/*` | pipelines | implemented | One-shot Phase B2 script uses standard Firestore `WriteBatch` chunks of 500 operations. Historical scale is low-thousands; no partition worker needed. |
| B3. Platform adds new endpoints under `/api/ticker-insights/*`, behind flag | platform | TBD | Reads from Firestore. |
| B4. Frontend renames type/service, switches consumers | platform | TBD | See § 4.6 list. |
| B5. Flip flag in prod, soak for 7 days | both | TBD | |
| B6. Drop Postgres `ticker_recommendations` table; delete `recommendation_queries.py` + `recommendation_db.py`; remove `/api/recommendations/*` aliases | platform | TBD | |

### Phase C — Episode shape cleanups

Rolling schedule; each cleanup is independent.

| Step | Owner | Target | Notes |
|------|-------|--------|-------|
| C1. Add `released_at_ms` to new episode writes; backfill historical | pipelines | partial | New write path implemented; historical feed-driven backfill still required. § 2.3 cleanup #1. |
| C2. Audit `*_url` / `*_public_url` pairs; produce drop list | both | TBD | § 2.3 cleanup #2. |
| C3. Normalize `spotify_release_date` to string format | pipelines | implemented | § 2.3 cleanup #5. |
| C4. Preserve `created_time` and platform `modified_*` fields on regeneration | pipelines | implemented | Existing episode updates use merge semantics excluding protected fields. |
| C5. Add `retracted_at` soft-delete marker | pipelines | implemented | Keeps episode docs and indices intact while signaling retraction. |

**Rollback triggers (any phase):** P0 incident, > 1% of episode reads returning 500s, sentiment label distribution shift > 30% from pre-flag baseline (model regression check).

---

## § 8. Verification checklist (platform side, ongoing)

For each phase, the platform team runs:

1. **Pre-flip baseline.** Capture row counts and sample shape from old endpoint (`curl .../api/recommendations/buzz?days=30`). Pin to spec doc.
2. **Post-flip parity.** Diff old vs new endpoint output on the same query. Allowed differences: field renames (per § 4.3, § 5.3), `sentiment_score` removal. No other differences allowed.
3. **UI smoke.** Load StockIndex, StockDashboard, WeeklyBuzzWidget on staging. Confirm non-empty rendering.
4. **Notification regression.** Re-process a known episode, confirm no duplicate notifications (would indicate `created_time` mutation).

---

## § 9. Out of scope (explicit)

These came up implicitly in the agents-team message ("we'll flag anything impossible"). Listed here to prevent confusion:

| Data | Source (NOT agents) | Code reference |
|------|---------------------|----------------|
| Live stock price, change, market cap | FinMind API (TW), Massive API (US) | [backend/src/services/stock_service.py](../backend/src/services/stock_service.py) |
| Chart OHLC data | Massive API + Postgres cache | Same |
| User watchlist, subscriptions, bookmarks, alerts, preferences | Platform writes on `users/{user_id}` | [backend/src/database/user_db.py](../backend/src/database/user_db.py) |
| Top Movers / sector heatmap | Currently mocked; future market data feed | [frontend/src/services/mocks/sectorData.ts](../frontend/src/services/mocks/sectorData.ts) |
| Notification delivery | Platform | [backend/src/services/notification_service.py](../backend/src/services/notification_service.py) |
| Authentication, JWT | Platform | [backend/src/services/auth_service.py](../backend/src/services/auth_service.py) |

---

## § 10. Accepted pipeline decisions

These decisions close the implementation questions that originally blocked the Firestore migration.

1. **Refresh cadence for `trending_tickers`: hourly delta.** The default job runs hourly without a full historical scan. It reads recent `ticker_insights` writes, derives touched `(ticker, market)` pairs, then recomputes only those tickers from their historical insight docs. Full recompute remains available for backfill/audit runs.
2. **Composite path for `ticker_insights`: confirmed.** The canonical path is `ticker_insights/{episode_id}/tickers/{ticker}`. Pipeline writers use Firestore `WriteBatch`, grouped by `episode_id`, and collection-group queries power aggregate readers.
3. **Backfill scope for Phase B2: standard batch job.** Historical `(episode, ticker)` scale is low-thousands. The Phase B2 script uses standard Firestore batched writes in chunks of 500 operations and does not require partition workers.
4. **Score-to-label cutoffs: fixed 5-tier thresholds.** The pipeline quantizes `sentiment_score` before write using § 4.2 exactly: `>=0.80`, `>=0.60`, `>=0.40`, `>=0.20`, else `STRONG_BEARISH`.
5. **Soft-delete signal: `retracted_at`.** Retracted episodes remain in `episodes/{episode_id}` with `retracted_at: int | null`; no separate retracted collection is introduced. This preserves index foreign keys.
6. **Multi-market namespace: internal `market` metadata.** `ticker_insights` and `trending_tickers` carry market metadata so TW/US symbols can be segregated while preserving existing string document IDs. Ambiguous overlaps without market metadata must fail validation before commit.
7. **Sector/theme exposures: episode metadata only.** Sector/theme-derived ticker baskets are written to `sector_exposures` and companion flat arrays on the episode document. They do not populate `related_tickers`, inverted ticker indices, ticker pages, watchlist notifications, or `ticker_insights`.
8. **Still open: `*_url` audit (§ 2.3 cleanup #2).** Which `*_public_url` fields are actually fetched by external consumers vs. backend-only remains an audit task.
