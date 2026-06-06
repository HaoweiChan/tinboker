#!/usr/bin/env bash
# News ingest run: RSS feeds → extract → enrich → shared wiki. This is what the
# tinboker-news.timer invokes (a systemd oneshot); run it from a checkout of
# this repo. Extra args are passed through to `python -m news`.
#
# Writes: Postgres tinboker_wiki — kind='news_article' pages plus append-only
#         enrichment of the shared entity/topic pages (/api/wiki).
#
# Secrets (WIKI_DATABASE_URL / OPENROUTER_API_KEY) are pulled from Google Secret
# Manager by shared.secrets.bootstrap(). That needs ADC, so
# GOOGLE_APPLICATION_CREDENTIALS must point at a service-account JSON — set it
# before calling this, or rely on the conventional podcast service-account path.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NEWS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"          # services/news
REPO_ROOT="$(cd "$NEWS_DIR/../.." && pwd)"        # repo root (uv workspace)
cd "$NEWS_DIR"

# ADC for Secret Manager: honour an existing GOOGLE_APPLICATION_CREDENTIALS, else
# the conventional service-account path the podcast deploy already populates.
SA_FILE="$REPO_ROOT/services/podcast/gcp-service-account.json"
if [ -z "${GOOGLE_APPLICATION_CREDENTIALS:-}" ] && [ -f "$SA_FILE" ]; then
  export GOOGLE_APPLICATION_CREDENTIALS="$SA_FILE"
fi

# Pull the followed-feeds list + curated ticker aliases from the platform admin
# (config plane). Override-friendly; unset it to fall back to the local feeds.json.
: "${TINBOKER_PLATFORM_API_URL:=https://api.tinboker.com}"
export TINBOKER_PLATFORM_API_URL

# Use the uv-managed workspace venv directly (systemd has a minimal PATH and no uv).
PY="$REPO_ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

exec "$PY" -m news "$@"
