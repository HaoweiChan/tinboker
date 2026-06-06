#!/bin/bash
# Create/upgrade the knowledge-wiki Postgres schema (idempotent — metadata.create_all).
#
# Resolves WIKI_DATABASE_URL from the environment; if it is not set, falls back to the
# podcast secrets bootstrap (Google Secret Manager). Run from anywhere in the repo.
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT/services/podcast"

exec uv run --project "$REPO_ROOT" python - <<'PY'
import os

if not os.environ.get("WIKI_DATABASE_URL"):
    try:
        from src.secrets_bootstrap import bootstrap
        bootstrap()
    except Exception as exc:  # noqa: BLE001 - best-effort convenience
        print(f"secrets bootstrap unavailable ({exc}); set WIKI_DATABASE_URL manually")

url = os.environ.get("WIKI_DATABASE_URL")
if not url:
    raise SystemExit("WIKI_DATABASE_URL is not set — cannot migrate the wiki schema")

import sqlalchemy as sa

from shared.wiki_builder.postgres_repo import PostgresWikiRepository

repo = PostgresWikiRepository(url)
repo.init_schema()

# Expression index on the JSONB 'date' field — makes date-range/ordering cheap for
# both news_article and episode pages. metadata.create_all does not add indexes to
# existing tables, so this ships as an idempotent CREATE INDEX IF NOT EXISTS.
with repo.engine.begin() as conn:
    conn.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_wiki_pages_date "
            "ON wiki_pages ((frontmatter->>'date'))"
        )
    )

print(f"wiki schema ready: {repo.health()}")
print("date expression index ready: ix_wiki_pages_date")
PY
