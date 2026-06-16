#!/usr/bin/env python3
"""Backfill ``ticker_insights/{episode_id}/tickers/{ticker}`` from GCS JSON.

For each Firestore episode with a ``ticker_insights_url`` (GCS gs://),
this script:
  1. Downloads the cached ticker JSON the pipeline already wrote at processing
     time.
  2. Translates it through the same exporter the live pipeline uses
     (`build_episode_insight_docs` — same spec output, same 5-tier label
     derivation, same Chinese horizon mapping).
  3. Writes the per-ticker docs into Firestore.

Idempotent: re-running overwrites each doc with a fresh build. Reads any GCS
bucket directly via ``google.cloud.storage`` so legacy episodes that live in
``podcast-data-web`` (alongside the ones in ``graphfolio-articles``) are
covered too.

Usage:
    uv run python services/podcast/scripts/backfill_ticker_insights.py --dry-run
    uv run python services/podcast/scripts/backfill_ticker_insights.py --limit 10
    uv run python services/podcast/scripts/backfill_ticker_insights.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVICE_ROOT))

from src.podcast.exporters.ticker_insights import (  # noqa: E402
    build_episode_insight_docs,
    write_episode_insights,
)
from src.service.upload_to_firebase import FirebaseService  # noqa: E402


def _read_gcs_json(gs_url: str) -> dict | list | None:
    if not gs_url or not gs_url.startswith("gs://"):
        return None
    bucket, _, path = gs_url[5:].partition("/")
    from google.cloud import storage

    blob = storage.Client().bucket(bucket).blob(path)
    raw = blob.download_as_text(encoding="utf-8")
    return json.loads(raw)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="don't write to Firestore")
    ap.add_argument("--limit", type=int, help="process at most N episodes")
    ap.add_argument("--podcast", help="only re-export episodes whose podcast_name matches this exactly")
    args = ap.parse_args()

    fb = FirebaseService()
    print("Streaming episodes from Firestore...")
    episodes = fb.get_all_episodes(order_by="created_time", descending=True)
    targets = [
        ep
        for ep in episodes
        if ep.get("ticker_insights_url") or ep.get("ticker_recommendations_url")
    ]
    if args.podcast:
        targets = [ep for ep in targets if ep.get("podcast_name") == args.podcast]
        print(f"  scoped to podcast '{args.podcast}'")
    if args.limit:
        targets = targets[: args.limit]
    print(f"  {len(targets)} episodes have ticker_insights_url")

    total_written = 0
    skipped: list[str] = []
    for i, ep in enumerate(targets, 1):
        ep_id = ep.get("id")
        if not ep_id:
            skipped.append("<no-id>")
            continue
        try:
            raw_payload = _read_gcs_json(ep.get("ticker_insights_url") or ep["ticker_recommendations_url"])
        except Exception as e:
            print(f"  [{i}/{len(targets)}] {ep_id}: gcs read failed ({e})")
            skipped.append(ep_id)
            continue

        docs = build_episode_insight_docs(
            raw_payload=raw_payload,
            episode_id=ep_id,
            podcaster=ep.get("podcast_name") or "",
            # Prefer the feed-derived true publish date; _iso_utc now coerces the
            # epoch-ms ints, so we no longer fall through to the backfill run date.
            podcast_launch_time=(
                ep.get("released_at_ms")
                or ep.get("spotify_release_date")
                or ep.get("created_time")
            ),
        )
        if not docs:
            skipped.append(ep_id)
            continue
        if args.dry_run:
            print(f"  [{i}/{len(targets)}] {ep_id}: would write {len(docs)} tickers")
            total_written += len(docs)
            continue
        try:
            written = write_episode_insights(fb.db, episode_id=ep_id, docs=docs)
            total_written += written
            print(f"  [{i}/{len(targets)}] {ep_id}: wrote {written}")
        except Exception as e:
            print(f"  [{i}/{len(targets)}] {ep_id}: write failed ({e})")
            skipped.append(ep_id)

    print(f"\n{'(dry-run) ' if args.dry_run else ''}{total_written} ticker docs across {len(targets) - len(skipped)} episodes")
    if skipped:
        print(f"skipped {len(skipped)} episodes: {skipped[:10]}{'...' if len(skipped) > 10 else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
