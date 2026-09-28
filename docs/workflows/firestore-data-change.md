# Shared content data change workflow

Use this workflow for fields shared by `pipelines/` (writer), `backend/` (reader), and `frontend/` (consumer). The filename is historical: Firestore is decommissioned. **Verified 2026-09-27:** the current storage is VPS Postgres `podcast_db`; content tables retain the `firestore_mirror` schema name. See the current-state section of the [data contract](../firestore-contract.md#current-state-2026-09-27).

## Before changing a shared field

1. Read the [data contract](../firestore-contract.md), especially the current-state section and the relevant episode, insight, or trending field definition. Treat §§1–10 as the historical Firestore-era shape and migration record; preserve compatible JSON shapes where they are still used.
2. Identify the owner. `pipelines/` writes episode, podcast, ticker-insight, and trending content. `backend/` owns user and notification tables and the platform's `modified_*` episode fields.
3. Change the writer, backend model/transformer, and frontend type or Zod schema together. Update the contract when the shared JSON shape changes. Coordinate with both tiers before changing a pipeline-owned field.
4. Check existing stored rows and regeneration behavior. The pipeline's [`_merge_onto_stored`](../../pipelines/services/podcast/src/pipeline/steps/postgres_episode.py) preserves keys and `created_time`; a new writer field may require a backfill.
5. Verify a representative write and read path, including validation in the frontend when it consumes the field.

## Adding an episode field

- Update the pipeline writer in [`postgres_episode.py`](../../pipelines/services/podcast/src/pipeline/steps/postgres_episode.py) or the producing step, and the §2 field contract.
- Update [`backend/src/models/podcast.py`](../../backend/src/models/podcast.py) and [`episode_transformer.py`](../../backend/src/services/episode_transformer.py).
- Update [`frontend/src/services/types.ts`](../../frontend/src/services/types.ts) and any relevant schema in [`frontend/src/validation/schemas.ts`](../../frontend/src/validation/schemas.ts).
- Update the contract's per-surface consumption table if a UI begins using the field.

Do not rewrite `created_time` on re-ingest. `first_seen_at` is the database's ingestion timestamp used by notification fan-out; it is set by the DB on first insert and never updated on conflict. See [`postgres_episode.py`](../../pipelines/services/podcast/src/pipeline/steps/postgres_episode.py) and the [notification producer](../../backend/src/services/notification_producer.py).

## Reading existing content

Use an existing backend endpoint or the shared [`content_read_service()`](../../backend/src/services/postgres_mirror_service.py) path for episode and insight content. Add a Postgres query to that service when its interface lacks the needed operation, then expose it through the backend API. Do not create a new Firestore client or direct frontend database read. Use the cache pattern in [`backend/AGENTS.md`](../../backend/AGENTS.md) for public endpoints.

For platform-owned SQL data, use the relevant `backend/src/database/` model and service. For media, use the VPS disk storage helpers and stable `/media` URLs described in [§11.7](../firestore-contract.md#117-media-storage-p5-write-side).

## Historical migrations

The original Firestore Phase A/B steps in the contract's §7 and reverse migration in §11 explain past decisions. They are **not active rollout instructions**. The active state is Postgres for content and users, and VPS disk for artifacts. The old `graphfolio-articles` path segment is a disk directory name, not a GCS bucket.

## Cross-references

- [Data contract](../firestore-contract.md)
- [Podcast domain](../agents/podcast-domain.md)
- [Stock data domain](../agents/stock-data.md)
- [Backend conventions](../../backend/AGENTS.md)
