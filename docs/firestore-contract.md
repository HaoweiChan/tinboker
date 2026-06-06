# Firestore data contract

> **This is the authoritative cross-repo data contract between the tinboker-platform backend (reader) and the tinboker-agents pipeline (writer).** Edits here require coordination with the tinboker-agents team.
>
> **Status:** Draft for tinboker-agents team review. Authoritative once both teams sign off § 10.
> **Owners:** platform team (this doc), tinboker-agents (write contract).
> **Doc location:** `docs/firestore-contract.md` (moved from `openspecs/firestore-schema/spec.md`).
> **Document version:** see `schema_version: 2` in § Scope. Bump `schema_version` inline rather than forking the doc.

---

## Purpose

This spec is the **data contract between the tinboker-agents pipeline (writer) and the tinboker-platform backend (reader)** for everything that flows through Firestore.

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

**In scope (platform-owned, listed for completeness):**
- `users/{user_id}`
- `users/{user_id}/notifications/{notification_id}`

**Out of scope — agents are NOT on the hook for these:**
- Live market data: `price`, `change`, `changePercent`, `marketCap`, `volume`, `pe`, `dividendYield`, `chartData[]`. Source: FinMind (TW) and Massive API (US) via the backend's `stock_service`.
- User state: `watchlist`, `podcast_subscriptions`, `episode_bookmarks`, `alerts`, `tag_subscriptions`, `notification_preferences`. Platform-owned writes.
- Top Movers / sector heatmaps (currently mocked; see [qa-report-2026-05-09.md](./qa-report-2026-05-09.md) BUG-2). These come from market price feeds.

**Versioning:** every agent-written document carries a `schema_version: <int>` field. This doc defines `schema_version: 2`. Bumping the integer requires updating this spec.

**Terminology:** "the agents pipeline" = the tinboker-agents repo (separate from this one). "The platform" = this repo (`tinboker-platform`, frontend + backend).

---

## § 1. Ownership matrix

| Path | Writer | Reader(s) | Lifecycle | Section |
|------|--------|-----------|-----------|---------|
| `episodes/{episode_id}` | agents (full doc); platform (`modified_summary_*` only) | backend `podcast_service`; all episode-consuming UI | one doc/episode, mutable | § 2 |
| `tickers/{ticker}/episodes/*` | agents | backend `get_episodes_by_ticker` | append-only index | § 3 |
| `tags/{tag}/episodes/*` | agents | backend tag pages, `get_all_tags` | append-only index | § 3 |
| `ticker_insights/{episode_id}/tickers/{ticker}` | agents | backend `/api/ticker-insights/by-ticker/{ticker}`, `/by-podcaster/{name}`; `StockDashboard`, `TickerInsightCard` | one doc/(episode,ticker), mutable | § 4 |
| `trending_tickers/{ticker}` | agents (nightly job) | backend `/api/ticker-insights/trending`; `StockIndex`, `WeeklyBuzzWidget`, `HomeRail` | rolling, recomputed nightly | § 5 |
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
| `key_insights` | string[] | **required** (see warning) | 3–8 plain-text bullet takeaways, no markdown — the episode's precomputed "essence". Rendered on EpisodeDetail **and** as the primary content of `EpisodeCardV2` across all browsing pages (HomeFeed / Podcaster / Tag / Stock / Watchlist / Profile). Those list views deliberately do **not** hydrate `summary_content` (perf — transcripts are large), so `key_insights` is the only insight source available to cards. ⚠️ **Currently ~0% populated by the agents pipeline** (0/40 recent episodes, 2026-06); cards fall back to the plain teaser until this is backfilled. **Action: agents must populate `key_insights` on every episode.** |
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
| `ticker_recommendations_public_url` | string \| null | usually | JSON of per-ticker insights. Source for `ticker_insights/*` documents (§ 4). |

#### File pointers — public HTTPS URLs

Each `*_url` above has an optional `*_public_url` counterpart. Backend reads from `*_public_url` first when present. **See § 2.3 cleanup #2** — these are proposed for deprecation pending audit.

#### Inlined markdown content (cache layer)

| Field | Type | Fulfilled | Notes |
|------|------|-----------|-------|
| `events_markdown_content` | string \| null | usually | Markdown with `(#time: MSEC)` chapter markers. Cached in Firestore so the frontend doesn't fetch GCS per page load. |
| `sentences_markdown_content` | string \| null | usually | Markdown with `(#time: MSEC)` clip markers. |
| `marp_markdown_content` | string \| null | sometimes | |
| `ticker_marp_markdown_content` | string \| null | sometimes | |
| `ticker_recommendations_content` | string \| null | usually | JSON-as-string. Superseded by `ticker_insights/*` collection (§ 4) post-migration. |

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

### 2.3 Proposed targeted cleanups

These are **proposals**; agents team should accept, push back, or counter-propose per item.

1. **Timestamp normalization — `released_at_ms` from the feed publish date.** Status: **platform consumer shipped** (backend `Episode.released_at_ms` + `episode_transformer._normalize_released_at_ms`; frontend `Episode.released_at_ms` preferred for display; the platform release recency filter reads it — see [docs/agents/podcast-domain.md](agents/podcast-domain.md) / `RELEASE_EPISODE_MAX_AGE_DAYS`). **Agents side is the blocker.** The field is already written but `_compute_released_at_ms` derives it from `spotify_release_date` → `created_time`, both of which are ingestion-time / null for Spotify-unmatched episodes (a Jan-published episode backfilled in May reads as May). The pipeline ALREADY fetches the true publish date — `api_data['datePublished']` (ISO-8601), parsed today by `orchestrator._parse_episode_date` but used only for the lookback window. **Required change (tinboker-agents):** wire `datePublished` into `released_at_ms` (and `created_time` when Spotify is absent) in `services/podcast/src/pipeline/utils.py::create_episode_object` + `models/podcast_models.py::_compute_released_at_ms`, then run a feed-driven backfill to correct historical docs (`datePublished` is returned for every episode by `fetch_episodes`, matched on `episode_number`/title — no Spotify dependency). **Do NOT mutate `created_time` on existing episodes** (§ 6.3) — only set `released_at_ms`. Until the backfill lands, the platform keeps `RELEASE_EPISODE_MAX_AGE_DAYS=0` (recency filter off). See the handoff: [docs/handoffs/released-at-ms-publish-date.md](handoffs/released-at-ms-publish-date.md).

2. **Audit the `*_url` / `*_public_url` pairs.** The Episode model defines both `gs://` and HTTPS variants for each artifact. Most of the time the backend hydrates content via `episode_transformer.py` from `*_content` directly. We propose:
   - Drop the `*_public_url` half of every pair where the backend can sign GCS URLs on demand.
   - Keep both only for fields the frontend fetches directly without backend mediation.
   - Action: a separate sub-doc auditing each pair's usage; merge with this spec or land alongside.

3. **`modified_*` is platform-only.** Agents pipeline must not overwrite `modified_summary_url`, `modified_summary_content`, `modified_by`, `modified_at` during regenerations. Spec requires agents to perform Firestore writes with `merge=True` *excluding* these fields. (Backend writes already use `merge=True` for adds and `DELETE_FIELD` for removals.)

4. **`*_content` fields are a cache, not a source.** Document that inlined markdown duplicates what `*_url` points to. Staleness rule: when agents regenerate the GCS file, they MUST also rewrite the matching `*_content` field in the same Firestore commit. Otherwise readers see drift.

5. **`spotify_release_date` typed as string.** Backend model declares `Optional[str]` but production data sometimes contains numbers (per frontend type `string | number | null`). Spec mandates string `YYYY-MM-DD`; agents normalize on write.

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
  "schema_version": 2,
  "episode_id": "ep_abc123",
  "podcaster": "股癌",
  "podcast_launch_time": "2026-05-12T08:30:00Z",   // ISO 8601 UTC
  "ticker": "NVDA",
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
- **Added**: `schema_version: 2`.
- **Removed**: the auto-increment `id` column (replaced by composite doc path `{episode_id}/tickers/{ticker}`).

### 4.2 Sentiment label enum

```
STRONG_BULLISH | BULLISH | NEUTRAL | BEARISH | STRONG_BEARISH
```

The raw `sentiment_score` is model-generated and its quantized value isn't meaningful to users. Spec **forbids** rendering the float on the UI. Public API responses omit it. Backend uses the float only for sort/order on `sentiment_label` ties.

**Proposed score-to-label cutoffs** (agents own the final boundaries; bring counter-proposals if these don't fit your model):

| sentiment_score | sentiment_label |
|---|---|
| ≥ 0.80 | `STRONG_BULLISH` |
| 0.60 – 0.79 | `BULLISH` |
| 0.40 – 0.59 | `NEUTRAL` |
| 0.20 – 0.39 | `BEARISH` |
| < 0.20 | `STRONG_BEARISH` |

### 4.3 Public API response shape — `TickerInsight[]`

The platform exposes these as `TickerInsight[]` (rename of `TickerRecommendation[]`):

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

### 4.5 Backend rename impact

- `backend/src/services/recommendation_service.py` → `backend/src/services/insight_service.py`. Implementation switches from Postgres to Firestore reads.
- `backend/src/routers/recommendations.py` → `backend/src/routers/ticker_insights.py`. New prefix `/api/ticker-insights`.
- `backend/src/database/recommendation_queries.py` → deleted once the Postgres `ticker_recommendations` table is dropped (see § 7).
- `backend/src/database/recommendation_db.py` → deleted with the queries module.

### 4.6 Frontend rename impact

- `frontend/src/services/recommendationService.ts` → `frontend/src/services/insightService.ts`.
- Type `TickerRecommendation` → `TickerInsight`; `TickerBuzz` → `TickerTrending` (see § 5).
- Function renames: `getRecommendationsByTicker` → `getInsightsByTicker`; `getRecommendationsByPodcaster` → `getInsightsByPodcaster`; `getMostDiscussedTickers` → `getTrendingTickers`.
- Consumers to update:
  - [frontend/src/components/financial/WeeklyBuzzWidget.tsx](../frontend/src/components/financial/WeeklyBuzzWidget.tsx)
  - [frontend/src/components/financial/TickerInsightCard.tsx](../frontend/src/components/financial/TickerInsightCard.tsx)
  - [frontend/src/pages/StockIndex.tsx](../frontend/src/pages/StockIndex.tsx)
  - [frontend/src/pages/StockDashboard.tsx](../frontend/src/pages/StockDashboard.tsx)
  - [frontend/src/components/redesign/HomeRail.tsx](../frontend/src/components/redesign/HomeRail.tsx)

---

## § 5. `trending_tickers/{ticker}` — Stock Index aggregate (NEW)

This replaces the on-the-fly Postgres aggregation that powers `/api/recommendations/buzz`. Agents recompute this collection nightly.

### 5.1 Document schema

```jsonc
{
  "ticker": "NVDA",                          // doc id, mirrored in field for convenience
  "schema_version": 2,

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

**Breaking change vs today's `TickerBuzz`** at [frontend/src/services/types.ts:471-476](../frontend/src/services/types.ts#L471-L476): `sentiment_score: number` removed; `sentiment_label` enum added. Rename `TickerBuzz` → `TickerTrending` in the same migration.

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
- Agents MAY update other fields freely (re-summarization, transcript corrections, ticker re-extraction).

---

## § 7. Migration plan

This is the rollout sequence. Each phase has agent-team and platform-team owners. **Dates left blank for the agents team to fill in during review.**

### Phase A — `trending_tickers` (unblocks Stock Index)

Highest priority. Stock Index is empty in production today because the Postgres `ticker_recommendations` DB pool is uninitialized (`/health` reports `pool_not_initialized` as of 2026-05-13). Moving this aggregate to Firestore fixes it.

| Step | Owner | Target | Notes |
|------|-------|--------|-------|
| A1. Agents wire up nightly job writing `trending_tickers/{ticker}` | tinboker-agents | TBD | Backfill from existing wiki/GCS data first. |
| A2. Platform adds `/api/ticker-insights/trending` reading from Firestore, behind feature flag `TICKER_INSIGHTS_FROM_FIRESTORE` | platform | TBD | Old `/api/recommendations/buzz` keeps working. |
| A3. Frontend switches StockIndex/WeeklyBuzzWidget/HomeRail to new endpoint | platform | TBD | Type rename `TickerBuzz` → `TickerTrending`. |
| A4. Flip feature flag in prod, observe for 48h | both | TBD | Rollback = flip flag off; old code path remains. |
| A5. Remove old `/api/recommendations/buzz` endpoint | platform | TBD | After 1 full release of green flag. |

### Phase B — `ticker_insights` (replaces per-episode Postgres recs)

| Step | Owner | Target | Notes |
|------|-------|--------|-------|
| B1. Agents dual-write (Postgres + Firestore) for new episodes | tinboker-agents | TBD | Ensures parity during cutover. |
| B2. Agents backfill historical episodes to `ticker_insights/*` | tinboker-agents | TBD | One-shot job; size estimate needed (§ 10 Q3). |
| B3. Platform adds new endpoints under `/api/ticker-insights/*`, behind flag | platform | TBD | Reads from Firestore. |
| B4. Frontend renames type/service, switches consumers | platform | TBD | See § 4.6 list. |
| B5. Flip flag in prod, soak for 7 days | both | TBD | |
| B6. Drop Postgres `ticker_recommendations` table; delete `recommendation_queries.py` + `recommendation_db.py`; remove `/api/recommendations/*` aliases | platform | TBD | |

### Phase C — Episode shape cleanups

Rolling schedule; each cleanup is independent.

| Step | Owner | Target | Notes |
|------|-------|--------|-------|
| C1. Add `released_at_ms` to new episode writes; backfill historical | tinboker-agents | TBD | § 2.3 cleanup #1. |
| C2. Audit `*_url` / `*_public_url` pairs; produce drop list | both | TBD | § 2.3 cleanup #2. |
| C3. Normalize `spotify_release_date` to string format | tinboker-agents | TBD | § 2.3 cleanup #5. |

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
| Top Movers / sector heatmap | Currently mocked ([qa-report-2026-05-09.md](./qa-report-2026-05-09.md) BUG-2); future market data feed | [frontend/src/services/mocks/sectorData.ts](../frontend/src/services/mocks/sectorData.ts) |
| Notification delivery | Platform | [backend/src/services/notification_service.py](../backend/src/services/notification_service.py) |
| Authentication, JWT | Platform | [backend/src/services/auth_service.py](../backend/src/services/auth_service.py) |

---

## § 10. Open questions for the agents team

These are the issues we know the agents team needs to weigh in on. Reply inline in this section during review.

1. **Refresh cadence for `trending_tickers`.** Nightly is the default; can you afford hourly without write-cost concerns? StockIndex on prod would feel more "alive" with hourly recomputes.
2. **Composite path for `ticker_insights`.** Spec proposes `ticker_insights/{episode_id}/tickers/{ticker}`. Acceptable, or do you prefer flat `ticker_insights/{auto_id}` with `episode_id` + `ticker` as indexed fields? Flat is simpler to backfill; composite gives natural collection-group queries.
3. **Backfill scope for Phase B2.** How many `(episode, ticker)` pairs exist historically? Is the backfill safe to run in a single job, or does it need chunking?
4. **Score-to-label cutoffs.** § 4.2 proposes fixed thresholds. Does your model produce calibrated probabilities, or should the cutoffs be derived from observed score distributions?
5. **Soft-delete signal.** How should agents mark a previously-published episode as retracted? No current mechanism. Options: `retracted_at` timestamp field, or move to `episodes_retracted/{id}` collection?
6. **`*_url` audit (§ 2.3 cleanup #2).** Which `*_public_url` fields are actually fetched by external consumers vs. backend-only? If only backend, the GCS `gs://` URL is enough.
7. **Schema version bump policy.** This doc is `schema_version: 2`. What's the agents-side migration cost of bumping to v3 in the future (e.g. for cleanup #1's `released_at_ms`)?
8. **Sentiment confidence.** Today there's a single score per insight. Would agents support emitting a confidence band (e.g. `sentiment_confidence: HIGH | MEDIUM | LOW`) alongside `sentiment_label`, or is that out of model scope?
