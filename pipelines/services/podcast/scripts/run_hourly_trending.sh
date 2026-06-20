#!/usr/bin/env bash
# Hourly trending ticker refresh: update only tickers touched by recent
# ticker_insights writes. This is what tinboker-trending-tickers.timer invokes.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PODCAST_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"        # services/podcast
REPO_ROOT="$(cd "$PODCAST_DIR/../.." && pwd)"      # repo root (uv workspace)
cd "$PODCAST_DIR"

if [ -z "${GOOGLE_APPLICATION_CREDENTIALS:-}" ] && [ -f "$PODCAST_DIR/gcp-service-account.json" ]; then
  export GOOGLE_APPLICATION_CREDENTIALS="$PODCAST_DIR/gcp-service-account.json"
fi

PY="$REPO_ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"

: "${TRENDING_LOOKBACK_HOURS:=1}"

exec "$PY" scripts/refresh_trending_tickers.py \
  --mode delta \
  --lookback-hours "$TRENDING_LOOKBACK_HOURS" \
  "$@"
