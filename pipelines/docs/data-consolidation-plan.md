# Data consolidation plan — move content stores onto the VPS

**Goal:** consolidate the website's data onto **one Postgres database + one blob
store on the Netcup VPS**, cutting GCP to near-zero. The webui is **not yet
published**, so this is the cheapest possible moment to do this — there are no
real users to break, no SLA, no dual-write phase needed.

**Status (2026-05-15):** in progress.
- ✅ graph-agent teardown (2026-05-13)
- ✅ Firestore → Postgres mirror (`podcast_db.firestore_mirror`, 2026-05-13)
- ✅ New Firestore exporters (`ticker_insights/`, `trending_tickers/`) shipped 2026-05-14 — pre-migration data shape correct; Postgres versions to be added in Phase D
- ✅ Cross-team data contract published to `contract/firestore-schema` on the wiki Postgres 2026-05-14 — will be deprecated by `contract/data-api` once HTTP API lands
- ✅ Phase A complete (2026-05-15): 20-show `podcasts_to_download.json`, legacy cron disabled, new nightly cron live. Fixed `[Errno 28] ENOSPC` bug — temp MP3s now cleaned up via `finally` block in `processor.py` after each episode; without this fix /tmp (3.9 GB tmpfs) filled up across 20-show runs. VPS validation gate pending one successful nightly run.
- ✅ Phase B complete (2026-05-15): `libs/shared/src/shared/db/` module added — 5 tables (`podcasts`, `episodes`, `tickers`, `ticker_insights`, `trending_tickers`), ABC+InMemory+Null+Postgres repositories, 20 unit tests. Migration applied to VPS `tinboker_wiki` DB; `list_recent(limit=5)` returns `[]`. No users table (platform repo owns users — Q4). Q5 NOTE: the 8 "bare slugs" (009150, 3548, 6324, 8035, elon, kem, openai, spcx) have 89 wiki_links referencing them — they are real entities, NOT noise. They need tickers.json enrichment, not deletion.
- ✅ Phase C complete (2026-05-15): `backfill_mirror_to_content_store.py` backfilled 901 episodes, 20 podcasts, 63+ tickers, 2,596 ticker_insight rows, 824 trending_ticker rows into `tinboker_wiki`. 69 episodes had no GCS ticker JSON (never fully processed — expected). Auto-registers unknown tickers (e.g. `MS`) that appear in insights but are missing from `tickers.json`.
- ✅ Phase D complete (2026-05-15): 11 new HTTP routes under `/api/podcast`, `/api/episodes`, `/api/ticker-insights`, `/api/tags` backed by Postgres. `services/podcast/src/routers/content.py` added; `list_all_tags()` added to repository layer. All routes smoke-tested on VPS; response times 5–56ms (p95 well under 200ms gate). Note: content tables are in `tinboker_wiki` (WIKI_DATABASE_URL), not `podcast_db`.
- ⏳ Phases E–F below — **not started**

**Owner for the next session:** read this doc top to bottom, then start at the
first incomplete phase. CLAUDE.md and `docs/spec-from-platform.md` are
prerequisite reading. SSH to the VPS works from this dev machine
(`ssh root@152.53.136.182`, key already configured); the wiki Postgres is only
reachable from on the VPS.

---

## Decisions already locked in (2026-05-14)

These are fixed unless the new session has strong evidence to revisit. Don't
re-litigate them without a real reason.

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Absorb the legacy `Podcast-Downloader` repo into this monorepo.** Single pipeline going forward. | The legacy repo is the Dify-era artifact; this repo's `content_builder` already does everything it does, with better prompts and structured outputs. Two pipelines means two failure modes, two bugs to fix, two backfills. |
| D2 | **HTTP API is the new contract, not Firestore-shaped JSON.** Publish `contract/data-api` on the wiki; deprecate `contract/firestore-schema`. | The platform team should call our podcast API over HTTP. The store underneath (Firestore today, Postgres tomorrow) is an implementation detail they shouldn't depend on. |
| D3 | **Pre-launch migration, no dual-write phase.** Direct flip from Firestore to Postgres once the new HTTP API is ready and verified. | There are no users to break. Dual-write is a post-launch concern; doing it pre-launch wastes 2-3 weeks. |
| D4 | **Single Postgres database `tinboker` on the VPS (rename of `tinboker_wiki`).** Wiki tables + new episodes/podcasts/shows/tickers/users tables live in the same DB. | Joins between wiki entities and episodes are natural; two DBs would force application-level joins. Existing `podcast_db` becomes redundant once mirror + recs tables move over. |
| D5 | **No coordination message to the platform team is being sent by the agents team.** The user handles platform-side communication directly. | Per session note 2026-05-14. The new session should not send Slack / email / PRs to the platform repo. Build the alternative; let the user broker the cutover. |
| D6 | **Self-hosted Postgres on the VPS is acceptable for launch.** Managed PG (Cloud SQL / Neon / Supabase) can be considered later if HA/PITR becomes a need. | Cost wins outweigh the durability gap for a pre-launch product. Nightly `pg_dump` + offsite restic restic is enough at this stage. |

---

## Open questions still requiring answers

These block specific phases (see the phase table for which). The new session
must surface these as `AskUserQuestion` calls before doing the work that
depends on them.

| Q | Question | Blocks | Notes |
|---|----------|--------|-------|
| Q1 | Does the live webui read GCS directly (`https://storage.googleapis.com/podcast-data-web/...`) or via the platform backend? | Phase E | **ANSWERED 2026-05-15:** Platform backend proxies all media. Frontend only sees hydrated JSON from api.tinboker.com. GCS URLs are backend-internal. Audio plays via Spotify embed, not mp3_url. Cutover is backend-only — no frontend lockstep required. |
| Q2 | VPS disk + bandwidth headroom. Netcup plan + monthly egress allowance? | Phase E | **ANSWERED 2026-05-15:** VPS 1000 G12 has unlimited monthly traffic (throttle only if 24h avg > 2TB — irrelevant at our scale). 205 GB free on root partition. No blocker. |
| Q3 | Backup target — Backblaze B2, Hetzner Storage Box, or keep one GCS bucket as restic target? | Phase F | Whatever's chosen, the backup must be tested with an actual restore. |
| Q4 | Move `users` collection (5 docs) to VPS Postgres as interim, or hand it to the platform repo immediately? | Phase C | Trivial either way. CLAUDE.md says users belong to the platform — natural to push it there. |
| Q5 | Are the 8 bare entity slugs (`009150, 3548, 6324, 8035, elon, kem, openai, spcx`) real tickers we should enrich, or noise to drop? | Phase B (cleanup) | These appeared in the wiki without `tickers.json` entries. Inspect and decide. |
| Q6 | Is there an outage window we can use, or are pre-launch deploys assumed disruption-free? | Phase F | Determines whether cutover needs a maintenance banner or can happen silently. |

---

## Current production topology (verified 2026-05-13 via SSH)

Three processes on the Netcup VPS (`152.53.136.182`), plus Docker containers:

| Process | What | Reads | Writes |
|---|---|---|---|
| `podcast-api.service` (systemd, :8003) | **this monorepo** (`/root/tinboker-agents`, `services/podcast`) — `/api/wiki/*` + `/api/episodes/*` | Postgres `tinboker_wiki`, GCS `graphfolio-articles` | Postgres `tinboker_wiki` (32 ep / 59 entity / 179 topic), GCS `graphfolio-articles` (1.3 GB, zh shows only), Firestore `graphfolio-db` (`ticker_insights/`, `trending_tickers/` collections as of 2026-05-14) |
| cron 21:00 `Podcast-Downloader/scripts/run_cron.sh` | **legacy repo** `github.com/Graphfolio/Podcast-Downloader` at `/root/mnt/Podcast-Downloader` (20-show config, AssemblyAI/Deepgram, Dify) | — | Firestore `graphfolio-db` (849 episodes, all 20 shows), GCS `podcast-data-web` (34 GB), Postgres `podcast_db.ticker_recommendations` (2.4k rows) + `podcast_db.stock_translations` (99 rows) |
| Docker `tinboker-backend-{prod,dev,staging}` (:8000/:8002/:8001) | **webui platform backend** (`ghcr.io/haoweichan/tinboker-backend`) + `tinboker-redis` | Firestore `graphfolio-db` (catalog + users) + Postgres `podcast_db` (recs/translations) + Redis. Media URLs point at `https://storage.googleapis.com/podcast-data-web/...` | Postgres `podcast_db`, Redis |
| Docker `marp-flask-service` (:5004) | Marp markdown → PPTX | — | — |

**Postgres databases (`127.0.0.1:5432`):**
- `tinboker_wiki` (this repo) — wiki pages + links
- `podcast_db` — Podcast-Downloader ticker recs + translations + `firestore_mirror` schema added 2026-05-13
- `graphfolio` (legacy) — one `stock_translations` table

Disk: 251 GB, 16% used. Plenty of headroom for the data side; Q2 is about
bandwidth, not disk.

### The core mess (current state)

There are **two podcast pipelines writing to two GCS buckets**:
- "Big" pipeline (legacy Podcast-Downloader): 849 episodes, all 20 shows, writes to Firestore + `gs://podcast-data-web`. This is what the live webui reads.
- "Small" pipeline (this repo): 32 episodes, 3 zh shows only, writes to `tinboker_wiki` + `gs://graphfolio-articles`. This is our future content API, not yet wired in.

**They are not synced.** That's why our wiki feed shows 32 episodes while
Firestore has 849. The first migration phase eliminates this duplication.

### What's in `gs://podcast-data-web`

Owner was originally listed as "UNKNOWN" — answer: it's the legacy
`Podcast-Downloader` cron on this same VPS, writing into the bucket. So D1
(absorb the legacy repo) implicitly resolves Q1's writer mystery — once
absorbed, this repo becomes the sole writer.

---

## Target state

```
                 ┌─────────────────────────── Netcup VPS ───────────────────────────┐
   Spotify RSS → │  podcast pipeline → Postgres `tinboker`  (one DB, all content)    │
   (one pipeline)│                       ├ episodes / podcasts / shows                │
                 │                       ├ wiki_pages / wiki_links (entities, topics) │
                 │                       ├ tickers (registry)                         │
                 │                       ├ ticker_insights / trending_tickers (NEW)   │
                 │                       └ users (interim, or hand to platform repo)  │
                 │                     ↘ /var/lib/tinboker/media/  (mp3, transcripts, │
                 │                        summaries, marp, infographics)              │
                 │                     ← served by Caddy / podcast API               │
                 │  podcast API (:8003) reads Postgres + serves /media/...            │
                 │     – exposes `contract/data-api` shape over HTTP                  │
                 │  nightly: pg_dump + restic → offsite cold backup                   │
                 └───────────────────────────────────────────────────────────────────┘
   GCP retained: Secret Manager (or migrate secrets to sops on the VPS),
   Gemini API. Firestore, both GCS buckets, Cloud Run → deleted.
```

---

## Phased migration plan

Each phase is sized for one focused session (1-3 days each). Validation gates
between phases must be green before starting the next.

### Phase A — Absorb the legacy `Podcast-Downloader` pipeline (~1 session)

**Inputs:** `/root/mnt/Podcast-Downloader/podcasts_to_download.json` on the VPS
(20 shows + the legacy cron's `scripts/run_cron.sh`). Verify via
`ssh root@152.53.136.182 'cat /root/mnt/Podcast-Downloader/podcasts_to_download.json'`.

**Deliverables:**
1. `services/podcast/podcasts_to_download.json` updated to include all 20 shows
   (the 3 zh shows already here + 17 from the legacy repo). Confirm every show
   has a usable `spotify_show_link` and reasonable `limit`.
2. Verify this repo's pipeline can handle the 17 English shows end-to-end:
   - Whisper STT in English (Groq's `whisper-large-v3` supports it; the existing `per-podcast transcript_option` mechanism lets you set different services per show if needed).
   - `content_builder` language handling — `determine_language(podcast_name)` in `services/podcast/src/pipeline/utils.py`. Test one English episode through the full pipeline locally before committing.
3. Disable the legacy cron on the VPS: comment out the `21:00` entry in `crontab -e` for root. The legacy repo files stay on disk for one week so Phase B's validation can diff against them; delete after Phase C validation passes.
4. Add a new cron / systemd timer that runs `python services/podcast/main.py` for all 20 shows nightly. Reuse the existing `services/podcast/scripts/run_nightly.sh` pattern.
5. Verify a one-night soak: nightly run completes for all 20 shows, no regressions on the 3 zh shows, the 17 new shows generate episodes in `tinboker_wiki`.

**Validation gate before Phase B:** the new cron has run successfully for one night; new episodes appear in `tinboker_wiki`; the legacy cron is disabled but the legacy repo files are still on disk for rollback.

**Watch out for:**
- The Spotify 403 blocker (see `.claude/plans/here-s-the-verdict-from-recursive-frost.md`) — new episodes will have empty Spotify fields until upstream auth is fixed. Independent of this migration.
- AssemblyAI/Deepgram cost on the legacy pipeline disappears, but Groq quota usage doubles. Check the rate limits before the first 20-show nightly run.

### Phase B — Add the consolidated Postgres schema (~1 session)

**Goal:** add tables to (the renamed) `tinboker` database so all data can live
in one place. No data migration yet — just schema + repositories.

**Deliverables:**
1. Rename Postgres database `tinboker_wiki` → `tinboker`. Update `WIKI_DATABASE_URL` in Google Secret Manager; update the systemd unit if it has the DB name hardcoded.
2. Add tables in a new migration file (`libs/shared/src/shared/wiki_builder/migrations/` is the pattern — extend it or add `libs/shared/src/shared/db/migrations/`):
   - `podcasts` (name PK, spotify_show_link, description, thumbnail_url, language)
   - `shows` (derived: episode_count, avg_len, blurb — can be a view rather than a table)
   - `episodes` (id PK, slug, podcast_name FK, episode_number, episode_title, spotify_release_date, released_at_ms, duration_ms, summary_url, transcript_url, mp3_url, summary_image_url, … all the Firestore fields the spec lists, plus `related_tickers TEXT[]`, `tags TEXT[]`, `num_likes`, `number_click`, `created_time`)
   - `tickers` (symbol PK + canonical/name/market/sector — fold in `libs/shared/src/shared/data/tickers.json`)
   - `users` (id PK, google_id, email, …) — only if Q4 resolves to "keep here interim"
   - `ticker_insights` (episode_id FK, ticker FK, schema_version, bluf_thesis, time_horizon, sentiment_label, sentiment_score, reasons JSONB, risks JSONB, podcaster, podcast_launch_time, created_at) — primary key (episode_id, ticker)
   - `trending_tickers` (ticker PK, schema_version, count_30d, count_90d, count_all_time, sentiment_label, sentiment_score, last_mentioned, top_podcasters JSONB, top_episodes JSONB, computed_at)
   - Foreign keys: `episodes.podcast_name → podcasts.name`; `ticker_insights.episode_id → episodes.id`; etc.
   - Indexes: `episodes(created_time DESC)`, `episodes USING GIN (related_tickers)`, `episodes USING GIN (tags)`, `ticker_insights(ticker)`, `trending_tickers(last_mentioned DESC)`.
3. Mirror the `WikiRepository` pattern: add `EpisodeRepository`, `PodcastRepository`, `TickerInsightRepository`, `TrendingTickerRepository` in `libs/shared/src/shared/db/`. Each repo: in-memory + Postgres implementations, factory selector.
4. Unit tests for each repository (mirror `libs/shared/tests/test_wiki_repository.py` style — start with in-memory, verify shape, then Postgres if test infra allows).

**Validation gate before Phase C:** migration applies cleanly on a scratch DB; repo unit tests pass; running `EpisodeRepository().list_recent(limit=5)` returns `[]` (empty but no error).

**Critical conventions:**
- Don't reuse the wiki layer's `ticker_recommendations` parameter name for new code — follow the renaming we did this session (TickerInsight). The wiki layer keeps its legacy name for backwards compat with stored Postgres bodies.
- Use the same schema_version (`2`) the platform spec uses. Stamp it in `ticker_insights.schema_version` and `trending_tickers.schema_version`.

### Phase C — Backfill from Firestore mirror to the new tables (~1 session)

**Goal:** move all 849 episodes + their tickers/tags/podcasts into the new
Postgres tables. After this, Postgres has the same content as Firestore.

**Deliverables:**
1. `services/podcast/scripts/backfill_firestore_to_postgres.py` — reads from
   `podcast_db.firestore_mirror.*` (mirror already exists from Phase 1 step 1)
   and upserts into the new `tinboker.*` tables. Idempotent. Round-trip check
   row counts.
2. Re-run `services/podcast/scripts/dump_firestore_to_postgres.py` first to
   refresh the mirror with anything written since 2026-05-13.
3. Backfill in order: `podcasts` → `tickers` (registry) → `episodes` (FKs into
   podcasts) → `ticker_insights` (FK into episodes; pull from each episode's
   `ticker_recommendations_content` GCS JSON via the existing exporter
   `services/podcast/src/podcast/exporters/ticker_insights.py`'s
   `build_episode_insight_docs` — same logic, different writer) → `trending_tickers` (call the same `aggregate_trending` we use for the Firestore path, but write to Postgres).
4. Reuse: `services/podcast/scripts/backfill_ticker_insights.py` already exists for the Firestore version; clone its GCS-reading logic for the Postgres path.
5. Verify counts: `SELECT COUNT(*) FROM episodes` == 849; `SELECT COUNT(*) FROM podcasts` == 20; etc.
6. Spot-check 5 episodes: same title, same created_time, same related_tickers in both Firestore and Postgres.

**Validation gate before Phase D:** Postgres has every episode Firestore has; counts match; spot-checks identical; ticker_insights backfilled for episodes that have `ticker_recommendations_url`; trending_tickers populated.

### Phase D — HTTP API + new contract (~2 sessions)

**Goal:** expose the data the platform team currently reads from Firestore as
HTTP routes on the podcast API, backed by Postgres. Publish the new contract.

**Deliverables:**
1. New routes (or extend existing routers) under `services/podcast/src/routers/`:
   - `GET /api/podcast` — list all podcasts with episode counts
   - `GET /api/podcast/{name}` — single podcast metadata
   - `GET /api/podcast/{name}/episodes?limit=&offset=&include_content=`
   - `GET /api/episodes/recent?limit=&include_content=`
   - `GET /api/episodes/by-ticker/{ticker}?limit=`
   - `GET /api/episodes/by-tag/{tag}?limit=`
   - `GET /api/episodes/{id}` — full detail (includes ticker_insights inline)
   - `GET /api/ticker-insights/by-ticker/{ticker}?start_date=&end_date=`
   - `GET /api/ticker-insights/by-podcaster/{name}?start_date=&end_date=`
   - `GET /api/ticker-insights/trending?days=30&limit=100`
   - `GET /api/tags` — all tags with counts
2. Each route returns JSON matching the platform's existing Pydantic models
   (see `tinboker-platform/backend/src/models/podcast.py` for shapes). The
   shape is the contract; the platform team doesn't change a line.
3. Cache: 5-min CDN headers on read-only aggregate endpoints
   (`trending`, `tags`). Etag/Last-Modified where natural.
4. **Write the storage-agnostic contract.** Replace `docs/spec-from-platform.md`
   with an HTTP-API-shaped version (same fields, but framed as "the response
   shape of `GET /api/episodes/{id}`" rather than "the Firestore doc at
   `episodes/{episode_id}`"). Publish to the wiki at `contract/data-api`:
   ```bash
   uv run python services/podcast/scripts/publish_contract.py \
     --slug data-api \
     --file docs/spec-from-platform.md \
     --title "Agents ↔ platform HTTP API contract"
   ```
5. Delete the now-superseded `contract/firestore-schema` from the wiki
   (the script doesn't support delete yet; do it via the Postgres delete in
   the same way `publish_contract.py` upserts — or add `--delete` to the
   script).
6. **Stop writing to Firestore from the pipeline.** Modify
   `services/podcast/src/pipeline/steps/firestore.py` to be a no-op when a
   new flag (`SKIP_FIRESTORE=1` or similar) is set. Default it to skip in the
   new VPS deployment. Postgres tables become the only writer.
7. The exporters (`ticker_insights.py`, `trending_tickers.py`) currently
   write to Firestore — add Postgres write paths. Pure functions
   (`build_episode_insight_docs`, `aggregate_trending`) stay shared.

**Validation gate before Phase E:** `curl` each new HTTP route against
production Postgres, response shape matches the contract, response time
< 200ms p95.

**Watch out for:**
- Pagination — the platform's spec calls for `?limit=&offset=`. SQL LIMIT/OFFSET is fine at this scale; revisit if it gets slow.
- `include_content` semantics — the spec section § 2.3 #4 says inlined `*_content` fields are a cache. Decide whether `include_content=false` strips them at the API or just skips a separate GCS fetch.
- `modified_summary_*` writes — these come from the platform backend. The HTTP API doesn't write these today; if the platform wants to keep editing summaries, we need a `PUT /api/episodes/{id}/summary` route. Confirm with the user before adding.

### Phase E — GCS → VPS blob store (~1-2 sessions, gated on Q1+Q2)

**Prerequisites:** Q1 and Q2 resolved. Don't start until both are answered.

**Deliverables:**
1. `gsutil -m rsync -r gs://graphfolio-articles /var/lib/tinboker/media/articles/`
   and `gs://podcast-data-web /var/lib/tinboker/media/web/`. Verify checksums and counts.
2. Caddy config: serve `/media/*` from `/var/lib/tinboker/media/`. Add range-request support for MP3 streaming (Caddy does this natively for static files; the test is whether iOS Safari can seek a streamed MP3).
3. Repoint the pipeline: replace `libs/shared/src/shared/gcs.py` writes with local-filesystem writes, store relative paths in the new `episodes.media_paths` JSONB column (or whatever shape the API exposes). The platform team should never see `gs://` URLs again.
4. Migrate existing DB rows: `UPDATE episodes SET mp3_url = REPLACE(mp3_url, 'gs://podcast-data-web/', '/media/web/') …` for each `*_url` column. Mirror for the platform-served public URLs.
5. Cutover: freeze the pipeline for ~30 min, final `rsync` delta, flip Caddy config, smoke-test 3 episode media plays end-to-end, then `gsutil rm -r` the buckets after Phase F's backup job is verified.

**Validation gate before Phase F:** all 7k+ media objects readable via the new URLs; no 404s on a sample of 50 random episodes; MP3 streaming with seek works on iOS Safari + Chrome.

### Phase F — Decommission GCP, set up backups (~1 session)

**Deliverables:**
1. Nightly cron: `pg_dump tinboker | zstd | restic backup --stdin` to the chosen backup target (Q3). Test a restore on a scratch VPS or Docker container.
2. `restic backup /var/lib/tinboker/media` nightly to the same target. Retention: 7 daily + 4 weekly + 12 monthly.
3. Delete Firestore: `gcloud firestore databases delete graphfolio-db` (after a final `dump_firestore_to_postgres.py` to refresh the mirror as a snapshot).
4. Delete both GCS buckets, the two near-empty staging buckets, the empty `gcr.io` Artifact Registry repo (those last two are noted in § 5 of this doc as carry-overs from the graph-agent teardown).
5. Disable unused GCP APIs in `gcloud services list --enabled`. Keep Secret Manager (or migrate secrets to sops-on-VPS and delete it too).
6. Update CLAUDE.md, README.md, AGENTS.md to remove Firestore/GCS references. Update [docs/MIGRATION.md](MIGRATION.md) with the new VPS-only deployment flow.

**Validation gate before considering migration "done":** all of the above complete; one full week of nightly cron passes without errors; restic restore tested; GCP billing shows < $5/month (Gemini API + Secret Manager only).

---

## What's already in place — don't duplicate

When picking up this plan, **read these first** so you don't recreate work:

| Artifact | Path | Purpose |
|---|---|---|
| Firestore mirror script | `services/podcast/scripts/dump_firestore_to_postgres.py` | Pulls Firestore into `podcast_db.firestore_mirror.*` tables. Rerun before Phase C to refresh. |
| Wiki repository pattern | `libs/shared/src/shared/wiki_builder/` | The `WikiRepository` + Postgres impl is the template for new `EpisodeRepository` etc. |
| Existing Firestore writer | `services/podcast/src/service/upload_to_firebase.py` | The `FirebaseService` class is what gets replaced by Postgres equivalents. Note: also writes the new `ticker_insights/` and `trending_tickers/` subcollections via `db` attribute. |
| Ticker-insights exporter | `services/podcast/src/podcast/exporters/ticker_insights.py` | Pure translation logic (Firestore-doc shape ← LLM output). Reuse for the Postgres path; only the writer changes. |
| Trending aggregator | `services/podcast/src/podcast/exporters/trending_tickers.py` | Same — pure aggregation, new writer. |
| Ticker-insights backfill | `services/podcast/scripts/backfill_ticker_insights.py` | Reads GCS JSON, writes to Firestore today. Clone for Postgres. |
| Nightly trending refresh | `services/podcast/scripts/refresh_trending_tickers.py` | Reads Firestore collection group, writes to Firestore. Clone for Postgres. |
| Cross-team contract | wiki `contract/firestore-schema` (deprecate); future `contract/data-api` | Spec lives in `docs/spec-from-platform.md`; published via `scripts/publish_contract.py`. |
| Wiki backfill helper | `services/podcast/scripts/backfill_wiki_to_postgres.py` | Earlier infra; check whether it's still needed after Phase C. |

---

## graph-agent teardown — DONE (2026-05-13)

Kept for context. The Cloud Run `graph-agent` service was confirmed dead (0 HTTP
invocations in 30 days, no scheduler/cron, no consumer of its `kg_store.json`
output) and removed:
- ✅ `gcloud run services delete graph-agent --region us-central1`
- ✅ Deleted all `gcr.io/gen-lang-client-0901363254/graph-agent` image digests
- ⏳ **Left for the user** — delete the now-empty staging buckets `gs://gen-lang-client-0901363254_cloudbuild` (1.7 MB) and `gs://run-sources-gen-lang-client-0901363254-us-central1` (2.1 MB), and the empty `gcr.io` Artifact Registry repo (`gcloud artifacts repositories delete gcr.io --location us`). These are part of Phase F's cleanup.
- ⏳ `services/knowledge_graph/` code module + `scheduled-graph-update.yaml` workflow: removal pending — that directory has ~27 files with uncommitted Neo4j→JSON-store refactor changes parked on `archive/knowledge-graph-refactor`. Confirm those are disposable before `git rm -r`.

---

## How to pick this up cold

If you're a new session reading this:
1. Read **CLAUDE.md** (project rules + VPS access info).
2. Read **`docs/spec-from-platform.md`** (platform-authored data spec; the
   shape your HTTP API needs to honor).
3. Read **this doc** top to bottom.
4. SSH into the VPS once to orient: `ssh root@152.53.136.182 'systemctl status podcast-api; psql tinboker_wiki -c "SELECT kind, COUNT(*) FROM wiki_pages GROUP BY kind"; ls /var/lib'`.
5. Resolve any blocking open questions for the phase you're starting (table § "Open questions still requiring answers"). Use `AskUserQuestion`.
6. Confirm validation gates from the previous phase before starting yours.
7. Track progress in this doc — update the status line at the top, and add a
   `### Phase X — done (date, summary)` block after each phase completes.

When in doubt, the user's preference is **simpler over clever, working
artifacts over paperwork, end-to-end tested in production before declaring
done**. They want this migration to be invisible to anyone who eventually
launches the webui.
