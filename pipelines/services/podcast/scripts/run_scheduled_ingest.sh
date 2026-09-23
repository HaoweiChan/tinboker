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

# Taiwanese shows first, then the English roster. Two runs, not one config: a feed or
# transcription failure on one side must not stop the other, and the TW run is the one
# the product depends on.
"$PY" main.py --config podcasts_tw.json --fill-limit "$@"

# The English roster is gated on the release config actually serving English, because
# every episode it picks up costs a transcription whose output nothing reads.
# Measured 2026-09-21: 3,243 English episodes have transcripts, 238 of them (7%) were
# ever summarised, and none are published — release_podcast_languages defaults to
# ["zh-TW"] and production sets no override, so /api/episodes/recent returns TW shows
# only. That is roughly $224 of Groq at whisper-large-v3 rates ($0.111/audio-hour) spent
# on content the catalogue cannot show. The comment this replaces said the English shows
# "are ingested and summarised ... but stay unpublished", which was half right: they are
# ingested, mostly not summarised, and never published.
#
# Set RELEASE_PODCAST_LANGUAGES to include "en" — or to "" — and this run comes back on
# its own. Empty is deliberate, not a typo: backend config documents an empty list as "no
# language restriction (show every followed show)", so an empty value serves English too.
# Hence ${VAR-default} and not ${VAR:-default}; the colon form would collapse the
# no-restriction case into the zh-TW default and keep skipping a roster we do publish.
RELEASE_LANGS="${RELEASE_PODCAST_LANGUAGES-zh-TW}"
if [ -z "$RELEASE_LANGS" ] || case ",$RELEASE_LANGS," in *,en,*) true ;; *) false ;; esac; then
  "$PY" main.py --config podcasts_en.json --fill-limit "$@"
else
  echo "  ⤷ skipping podcasts_en.json — RELEASE_PODCAST_LANGUAGES=$RELEASE_LANGS does not serve English"
fi
