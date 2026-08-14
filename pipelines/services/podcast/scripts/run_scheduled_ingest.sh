#!/usr/bin/env bash
# Scheduled ingest: pick up any episode the feeds have that we have not processed, run it
# through the full pipeline, and — when SYNDICATE_AUTOPUBLISH is set — let step 5f push
# the summary to 方格子 and Substack. This is what tinboker-podcast-ingest.timer invokes.
#
# --fill-limit is not optional here. Without it a repeat run reprocesses episodes that are
# already done, which means paying to transcribe the same audio again on every tick.
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

exec "$PY" main.py --config podcasts_tw.json --fill-limit "$@"
