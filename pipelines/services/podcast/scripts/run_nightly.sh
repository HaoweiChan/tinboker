#!/usr/bin/env bash
# Nightly podcast pipeline run: download → transcribe → summarize → upload, plus the wiki-ingest
# and Postgres-episode-mirror steps. This is what the VPS cron invokes (see docs/MIGRATION.md);
# run it from a checkout of this repo. Extra args are passed through to main.py.
#
# Writes: GCS (GCS_BUCKET_NAME, default graphfolio-articles), Firestore graphfolio-db,
#         Postgres tinboker_wiki (/api/wiki), Postgres podcast_db.firestore_mirror.episodes.
#
# Secrets (GOOGLE_API_KEY / WIKI_DATABASE_URL / EPISODE_DATABASE_URL / OPENROUTER_API_KEY / ...)
# are pulled from Google Secret Manager by secrets_bootstrap.py. That needs ADC, so
# GOOGLE_APPLICATION_CREDENTIALS must point at a service-account JSON — set it before calling
# this, or drop the file at services/podcast/gcp-service-account.json and it'll be picked up.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PODCAST_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"        # services/podcast
REPO_ROOT="$(cd "$PODCAST_DIR/../.." && pwd)"      # repo root (uv workspace)
cd "$PODCAST_DIR"

# ADC for Secret Manager: honour an existing GOOGLE_APPLICATION_CREDENTIALS, else the conventional path.
if [ -z "${GOOGLE_APPLICATION_CREDENTIALS:-}" ] && [ -f "$PODCAST_DIR/gcp-service-account.json" ]; then
  export GOOGLE_APPLICATION_CREDENTIALS="$PODCAST_DIR/gcp-service-account.json"
fi

# content_builder LLM model overrides — cost optimisation (code defaults are gemini-2.5-flash).
# extractor + ticker_extractor: structured extraction at temp 0.1 → Flash-Lite is plenty (~6x cheaper output).
# writer + marp_writer (quality-critical zh prose) stay on gemini-2.5-flash unless overridden here/in the env.
# To trial OpenRouter for the writer (needs the OPENROUTER_API_KEY secret):
#   export WRITER_MODEL=openrouter:deepseek/deepseek-chat
: "${EXTRACTOR_MODEL:=gemini-2.5-flash-lite}"
: "${TICKER_EXTRACTOR_MODEL:=gemini-2.5-flash-lite}"
export EXTRACTOR_MODEL TICKER_EXTRACTOR_MODEL

# Pull the followed-shows list from the platform admin (config plane).
# Override-friendly; unset it to fall back to the local podcasts_*.json.
: "${TINBOKER_PLATFORM_API_URL:=https://api.tinboker.com}"
export TINBOKER_PLATFORM_API_URL

# Use the uv-managed workspace venv directly (cron has a minimal PATH and no uv).
PY="$REPO_ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

# Step 1: podcast pipeline (download → transcribe → summarize → upload → wiki → Postgres mirror)
"$PY" main.py --config podcasts_tw.json --fill-limit "$@"

# Step 2: recompute trending_tickers/{ticker} aggregate from ticker_insights
echo "--- refresh_trending_tickers ---"
"$PY" scripts/refresh_trending_tickers.py
