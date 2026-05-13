# Data consolidation plan — move content stores onto the VPS

**Goal:** stop spreading the website's data across Firestore + two GCS buckets + (formerly) a
Cloud Run job, and consolidate onto **one Postgres database + one blob store on the Netcup VPS**,
cutting GCP to near-zero. This doc records the current state, the target state, the migration steps,
and the open questions that must be answered before parts of it are safe to execute.

> Status: graph-agent teardown — **done**. Firestore → Postgres mirror (Phase 1 step 1) — **done**
> (`podcast_db.firestore_mirror`, 2026-05-13). GCS migration and Firestore decommission — **not started**.

---

## 0. The actual production topology (discovered 2026-05-13 via SSH to the VPS)

Three things run on the Netcup VPS, plus Docker containers:

| Process | What it is | Reads | Writes |
|---|---|---|---|
| `podcast-api.service` (systemd, :8003) | **this monorepo** (`/root/tinboker-agents`, `services/podcast`) — `/api/wiki/*` + `/api/episodes` rerun routes | Postgres `tinboker_wiki` | Postgres `tinboker_wiki` (32 ep / 59 entity / 179 topic), GCS `graphfolio-articles` (1.3 GB, zh shows only) |
| cron 21:00 `Podcast-Downloader/scripts/run_cron.sh` | **separate repo** `github.com/Graphfolio/Podcast-Downloader` at `/root/mnt/Podcast-Downloader` (20-show `podcasts_to_download.json`, AssemblyAI/Deepgram, Dify) | — | Firestore `graphfolio-db` (849 episodes, all 20 shows), GCS `podcast-data-web` (34 GB), Postgres `podcast_db.ticker_recommendations` (2.4k rows) + `podcast_db.stock_translations` (99 rows) |
| Docker `tinboker-backend-{prod,dev,staging}` (:8000/:8002/:8001) | **the webui platform backend** (`ghcr.io/haoweichan/tinboker-backend`) + `tinboker-redis` | **Firestore `graphfolio-db`** (catalog + users) + Postgres `podcast_db` (recs/translations) + Redis. Media URLs point at `https://storage.googleapis.com/podcast-data-web/...` | Postgres `podcast_db`, Redis |
| Docker `marp-flask-service` (:5004) | Marp markdown → PPTX | — | — |

Postgres (host, `127.0.0.1:5432`) databases: `tinboker_wiki` (this repo), `podcast_db` (Podcast-Downloader + platform backend; also now `firestore_mirror` schema), `graphfolio` (legacy, one `stock_translations` table). Disk: 251 GB, 16% used. *(Note: the platform backend's PG connection currently points at host `docker-db_postgres-1` which doesn't resolve — its `recommendation_db` is "pool_not_initialized"/degraded; it's running on Firestore + Redis only. Worth fixing on the platform side.)*

**So:** the **live webui reads Firestore `graphfolio-db` + `podcast_db`, and serves media straight
from `gs://podcast-data-web`**. It does **not** touch `tinboker_wiki` or `graphfolio-articles` —
those are this repo's *future* content API, not yet wired into the webui. There are two podcast
pipelines (this repo's `services/podcast` → `graphfolio-articles`/`tinboker_wiki`; the old
`Podcast-Downloader` → `podcast-data-web`/Firestore/`podcast_db`) and they are not synced.

### Done so far (Phase 1, step 1)

`services/podcast/scripts/dump_firestore_to_postgres.py` mirrors all of Firestore `graphfolio-db`
into **`podcast_db.firestore_mirror`** (`episodes` 849, `podcasts` 20, `tags` 1436, `tickers` 1080,
`users` 5) — each table = promoted/indexed columns + a `doc` JSONB with the full document. It's
idempotent (`ON CONFLICT`) and doesn't touch Firestore. Re-run any time; consider a nightly cron
until the platform backend is repointed off Firestore.

---

## 1. Current state (as observed 2026-05-13)

| Store | Where | Contents | Who writes it |
|---|---|---|---|
| Firestore `graphfolio-db` | GCP `us-central1`, native mode | `episodes` **849** (catalog + all GCS URLs + `num_likes`/`number_click`/`related_tickers`/`created_time`), `podcasts` **20** (name, spotify link, thumbnails), `tags` **1436** (id-only docs), `tickers` **1080** (id-only docs), `users` **5** (accounts, `podcast_subscriptions`, `episode_bookmarks`, google_id) | The live podcast pipeline (see "who writes podcast-data-web" below) + the legacy webui for `users` |
| GCS `graphfolio-articles` | GCP | `mp3/ transcripts/ summaries/ sentences/ marp/ ticker_marp/ ticker_recommendations/ events/ images/ articles/ blog/` — **1.3 GB / ~1.9k objects**, only the 3 zh shows (Gooaye, 游庭皓, 財報狗), last write 2026‑05‑10 | This monorepo's `services/podcast` (`GCS_BUCKET_NAME=graphfolio-articles`, `podcasts_to_download.json`) + `services/knowledge_graph` (now removed) |
| GCS `podcast-data-web` | GCP | Same layout under `podcasts/` — **34.2 GB / ~7k objects**, all 20 shows incl. the English ones, **actively written** (424 objects in May 2026, latest 2026‑05‑11) | **UNKNOWN — see open question #1.** Not referenced anywhere in this repo. Most likely an older/separate `Podcast-Downloader` deployment (Render? a VPS cron?) writing to Firestore + this bucket. |
| Postgres `tinboker_wiki` | Netcup VPS `127.0.0.1:5432`, behind `/api/wiki` | `wiki_pages`: **32 episode** + **59 entity** (51 zh-enriched, 8 bare) + **179 topic** pages; `wiki_links` | This monorepo's `services/podcast` wiki-ingest step (the `graphfolio-articles` pipeline only) |
| ~~KG `kg_store.json` on Cloud Run `graph-agent`~~ | ~~GCP~~ | **removed** — see teardown log below | — |

**The core mess:** there are effectively **two podcast pipelines** writing to **two GCS buckets** —
the "big" one (`podcast-data-web` + Firestore, 849 episodes, all shows) which is what the live
webui most likely reads, and the "small" one (`graphfolio-articles` + Postgres wiki, 32 episodes,
zh shows only) which is the one this monorepo + the `/api/wiki` content API is built on. They are
not synced. That's why slice A's feed shows 32 episodes while Firestore has 849.

---

## 2. Target state

```
                 ┌─────────────────────────── Netcup VPS ───────────────────────────┐
   Spotify RSS → │  podcast pipeline → Postgres `tinboker`  (one DB, all content)    │
   (one pipeline)│                       ├ episodes / podcasts / shows                │
                 │                       ├ wiki_pages / wiki_links (entities, topics) │
                 │                       ├ tickers (registry)                         │
                 │                       └ users  (interim, until platform repo owns) │
                 │                     ↘ /var/lib/tinboker/media/  (mp3, transcripts, │
                 │                        summaries, marp, infographics)              │
                 │                     ← served by Caddy / podcast API               │
                 │  podcast API (:8003) reads Postgres + serves /media/...            │
                 │  nightly: pg_dump + restic → offsite cold backup                   │
                 └───────────────────────────────────────────────────────────────────┘
   GCP retained: Secret Manager (or move to sops on the VPS), Gemini API. Everything else → deleted.
```

One relational DB for content (the joins/aggregations the webui needs are natural SQL), GCS's role
(blob store) moves to a VPS directory served over HTTP, and a real backup job replaces GCS's
durability. The wiki schema (`docs/wiki-schema.md`) stays; new tables (`episodes`, `podcasts`,
`shows`, `tickers`, `users`) join it in the same database.

---

## 3. Open questions (must answer before executing the GCS part)

1. **Who writes `gs://podcast-data-web` (34 GB, still active)?** Not in this repo. Candidates:
   an old `Podcast-Downloader` repo deployed on Render/Railway/Fly; a cron on the VPS; the webui
   platform repo. **Find it** (check the other repos' deploy configs, `gcloud logging` on the
   bucket with data-access audit logs enabled, or just look at what the running cron on the VPS
   does — needs SSH access, which the current key doesn't grant). Until then: **do not move or
   delete this bucket** — and decide whether *that* pipeline or this monorepo's pipeline becomes
   "the" pipeline.
2. **Does the webui read GCS directly (`https://storage.googleapis.com/podcast-data-web/...`) or
   via the podcast API?** If direct, the URL scheme changes on migration and the platform repo
   must update in lockstep. The episode `*_public_url` fields in Firestore suggest direct access.
3. **VPS capacity & bandwidth.** Need ~40 GB free disk + the monthly egress allowance to serve
   ~34 GB of mp3s. Which Netcup plan is it? (Couldn't check — SSH key denied.)
4. **Backup target.** A single VPS disk has no redundancy. Options: keep one GCS bucket purely as
   a cold backup target (`restic`/`rclone` nightly); or Backblaze B2 / Hetzner Storage Box.
5. **`users` collection** — CLAUDE.md says accounts belong to the platform repo. Migrate it to VPS
   Postgres as an interim, or hand it to the platform repo now? (5 docs — trivial either way.)
6. **Is self-hosted Postgres on the VPS acceptable long-term** for the data the website depends on
   (no managed HA/PITR), or should it be a managed PG (Cloud SQL / Neon / Supabase / Hetzner)?
   The *shape* (one relational store + blob dir) is right regardless of host.

---

## 4. Migration steps

### Phase 0 — prerequisites
- Get SSH access to the VPS; confirm disk/bandwidth headroom; identify & document the
  `podcast-data-web` writer (open question #1). Decide which pipeline is canonical.
- Decide host for Postgres (stay on VPS bare-metal vs managed) and the backup target.

### Phase 1 — Firestore → Postgres (low risk, do first; consolidates the DB)
1. Schema: add tables in the same `tinboker_wiki` DB (rename DB → `tinboker`): `podcasts`,
   `shows` (derived: episode_count, avg_len, blurb), `episodes` (slug, podcast, number, title,
   date, duration, summary, media URLs/paths, likes, clicks, related_tickers[]), `tickers`
   (the registry — fold in `libs/shared/src/shared/data/tickers.json`), `users`. Add FKs to
   `wiki_pages` where useful (episode slug ↔ `wiki_pages('episode', slug)`).
2. Writer: a `dump_firestore_to_postgres.py` one-shot — read each collection, upsert into the
   new tables. Idempotent (`ON CONFLICT`). Round-trip-check counts.
3. Repoint `services/podcast`: replace `src/service/upload_to_firebase.py` (`FirebaseService`)
   reads/writes with a Postgres repository (mirror the `WikiRepository` pattern). Keep a thin
   compat shim during transition. Update `/api/podcast/*` routes (and add the missing
   `GET /api/podcast/shows` while here).
4. Verify `/api/wiki/episodes` and `/api/podcast/*` against Postgres; then stop writing to
   Firestore; later `gcloud firestore databases delete graphfolio-db` (after a final export).

### Phase 2 — backfill the wiki from the full catalog (independent of host)
- Run the wiki-ingest step over all 849 episodes (currently only 32 are ingested), or decide the
  wiki is intentionally zh-only and document that. Run `backfill_ticker_sentiment.py` and
  `reenrich_entities_from_registry.py` against prod. Cover the 8 bare entity slugs
  (`009150, 3548, 6324, 8035, elon, kem, openai, spcx`) in `tickers.json` or mark them noise.

### Phase 3 — GCS → VPS blob store (medium risk; gated on open questions #1–#4)
1. `gsutil -m rsync -r gs://graphfolio-articles gs://<temp>` → VPS `/var/lib/tinboker/media/articles/`
   and (once the writer is sorted) `gs://podcast-data-web` → `/var/lib/tinboker/media/web/`.
2. Caddy: serve `/media/*` from that dir (or a small FastAPI static mount with range support for
   mp3 streaming). Decide public URL scheme (`https://podcast-api.tinboker.com/media/...`).
3. Repoint `libs/shared/src/shared/gcs.py` + every `*_public_url` / `gs://` reference to write
   files to the local dir and store relative paths. Migrate existing DB rows' URLs.
4. Cutover: freeze the pipeline, final `rsync`, flip config, smoke-test media playback, then
   `gsutil rm -r` the buckets (after the backup job below is proven).
5. Backup: cron `pg_dump | zstd` + `restic backup /var/lib/tinboker/media` → chosen offsite target,
   nightly, with retention; test a restore.

### Phase 4 — decommission GCP
- Delete Firestore DB, both GCS buckets, the two near-empty staging buckets, the empty `gcr.io`
  Artifact Registry repo. Keep Secret Manager (or migrate secrets to sops-on-VPS and delete it too).
  Disable unused APIs. Net GCP spend → ≈ Gemini API usage only.

---

## 5. graph-agent teardown — DONE (2026-05-13)

The Cloud Run `graph-agent` service was confirmed dead (0 HTTP invocations in 30 days, no
scheduler/cron, no consumer of its `kg_store.json` output) and removed:
- ✅ `gcloud run services delete graph-agent --region us-central1`
- ✅ Deleted all `gcr.io/gen-lang-client-0901363254/graph-agent` image digests (incl. old build layers)
- ⏳ **Left for the user** (a permission guard blocked the bot): delete the now ~empty staging
  buckets `gs://gen-lang-client-0901363254_cloudbuild` (1.7 MB) and
  `gs://run-sources-gen-lang-client-0901363254-us-central1` (2.1 MB), and the now-empty `gcr.io`
  Artifact Registry repo (`gcloud artifacts repositories delete gcr.io --location us`).
- The `services/knowledge_graph/` code module + `scheduled-graph-update.yaml` workflow:
  removal pending — that directory currently has ~27 files with **uncommitted** Neo4j→JSON-store
  refactor changes; confirm those are disposable before `git rm -r`.

**Realistic savings:** Cloud Run was already $0 (scales to zero); the images were ~3.8 GB of
Artifact Registry storage (~$0.40/mo). The teardown is mostly hygiene + removing the risk of an
accidental run. The actual GCP line item worth chasing is the **34 GB `podcast-data-web` bucket**
(~$0.70/mo) and, more importantly, the architectural simplification above.
