# Backend documentation

Start with the [backend README](../README.md) for local development and the
[infrastructure runbook](../../docs/infra-runbook.md) for the current VPS,
PostgreSQL, Redis, secrets, and environment layout. The
[deploy flow](../../docs/workflows/deploy-flow.md) is the release procedure. The running
API's `/docs` page is the route and schema reference.

Most files here are dated implementation reports, experiments, or proposals.
Read their historical notes for context, but verify any command, endpoint, or
data source against the current code before using it. In particular:

| Topic | Current reference | Historical record |
|---|---|---|
| Local Redis | [Backend README](../README.md#local-development) | [Redis setup](infrastructure/redis-setup.md) |
| PostgreSQL on VPS | [Infrastructure runbook](../../docs/infra-runbook.md) | [Cloud SQL setup](infrastructure/gcp-cloud-sql-setup.md) |
| Content and media | [Content API note](features/content-api-gcs.md) | [Firestore indexes](infrastructure/firestore-indexes.md) |
| Google login | [`src/routers/auth.py`](../src/routers/auth.py) and [env reference](../../docs/infra-runbook.md) | [OAuth implementation](guides/google-oauth-implementation.md) |
| Container recovery | [Infrastructure runbook](../../docs/infra-runbook.md) | [2026-02 incident report](production-container-reliability.md) |

The `podcast_related_files/` scripts document the former Firebase ingestion
path. Podcast ingestion now belongs to `pipelines/`; these scripts are not part
of the active runtime.
