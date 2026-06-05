# Handoff: make `released_at_ms` the true publish time (tinboker-agents)

**Owner:** tinboker-agents · **Requested by:** platform (zh-TW launch) · **Date:** 2026-06-05
**Contract:** [firestore-contract.md](../firestore-contract.md) § 2.1 / § 2.3 cleanup #1, C1.

## Why (the platform is blocked on this)

The zh-TW launch needs to **hide episodes published more than ~1 month ago**. There is
no reliable publish date in the read path today:

- `spotify_release_date` is **null for 100%** of sampled zh-TW episodes.
- `created_time` is **ingestion time, not publish time**. Evidence (dev, 2026-06-05):
  `財經一路發` episode titles span Jan–Jun 2026, but their `created_time` clusters on
  the **late-May backfill run** (2026-05-23/24/25). So a `created_time >= now-30d` filter
  lets ~4 months of old episodes through, then drops the whole batch off a cliff in ~2 weeks.

The platform side is already done (see below). The remaining work is to populate a
**reliable** `released_at_ms` and backfill history.

## Root cause (in tinboker-agents)

`released_at_ms` already exists but is computed from the wrong source:

- `services/podcast/src/models/podcast_models.py::_compute_released_at_ms` (≈ lines 71–91)
  derives it as: explicit override → `spotify_release_date` (UTC midnight) → `created_time`.
- `created_time` itself: `services/podcast/src/pipeline/utils.py::create_episode_object`
  (≈ lines 178–184) uses the Spotify release datetime when matched, else
  **`datetime.now()`** (ingestion time).
- The **true publish date is already fetched** — the podcasttomp3 API returns
  `datePublished` (ISO-8601) in `episode_data.api_data`. It is parsed today by
  `services/podcast/src/podcast/orchestrator.py::_parse_episode_date` (≈ lines 446–462)
  but used **only** for the lookback window in `_select_recent_episodes` — never written.

So the data needed is in hand; it just isn't wired into the timestamp.

## Required change

1. **Carry the feed publish date into the episode.** In `create_episode_object`
   (`utils.py`), read `episode_data.api_data.get('datePublished')`, parse it (reuse
   `_parse_episode_date`), and use it as the **primary** source for `released_at_ms`
   (and for `created_time` only when there is no existing stored value AND no Spotify
   match — never overwrite an existing `created_time`, see §6.3).
2. **Reorder `_compute_released_at_ms`** (`podcast_models.py`) preference to:
   explicit `released_at_ms` → **feed `datePublished` (ms)** → `spotify_release_date` →
   `created_time`. Output Unix **milliseconds** int.
3. **Backfill historical docs.** Add a feed-driven backfill (model it on the existing
   `services/podcast/scripts/backfill_*.py`): for each followed show, re-fetch the feed
   (`fetch_episodes` returns `datePublished` for **every** episode), match existing
   Firestore docs by `episode_number`/title, and set `released_at_ms` only. **Do not touch
   `created_time`** (mutating it re-fires `new_episode` notifications — §6.3). No Spotify
   dependency.

## Platform side — already shipped (no action needed there)

- Backend `Episode.released_at_ms` + `episode_transformer._normalize_released_at_ms`
  (normalizes int/datetime/ISO; **never** falls back to `now()` — missing stays `None`).
- Frontend `Episode.released_at_ms`, preferred for display in `episodeAdapter.ts` /
  `EpisodeDetail.tsx`.
- Release recency filter in `backend/src/services/podcast.py` reads `released_at_ms`
  (falls back to `created_time`), gated by `RELEASE_EPISODE_MAX_AGE_DAYS` (default `0` = off).

## Activation (after the backfill lands)

1. Spot-check: for a sample of episodes, `released_at_ms` matches the title/feed date
   (not the backfill-run date).
2. Set `RELEASE_EPISODE_MAX_AGE_DAYS=30` on the platform backend (env var) and restart.
3. Verify the feed/channel pages show only last-30-day episodes; confirm no
   notification storm (would indicate `created_time` was mutated).

## Verification of the data problem (reproduce)

```bash
# Newest episodes: created_time clusters on the backfill day, titles say otherwise.
curl -s "https://dev-api.tinboker.com/api/podcast/$(python3 -c "import urllib.parse;print(urllib.parse.quote('財經一路發'))")/episodes?limit=200" \
  | python3 -c "import sys,json,datetime,collections,re; d=json.load(sys.stdin); eps=d['episodes']; \
print('created_time days:', collections.Counter(datetime.datetime.fromtimestamp((e['created_time'] or 0)/1000).strftime('%Y-%m-%d') for e in eps).most_common(3)); \
print('title-date months:', collections.Counter((m.group(0)[:7]) for e in eps if (m:=re.search(r'20\\d\\d[.\\-/]\\d{1,2}', e.get('episode_title') or ''))))"
```
