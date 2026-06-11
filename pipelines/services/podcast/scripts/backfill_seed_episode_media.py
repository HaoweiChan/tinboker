#!/usr/bin/env python3
"""
Backfill GCS media (MP3 / transcript / summary) for seeded ep_* episodes.

The original seed_new_podcasts.py upload wrote episode docs with
``mp3_url: null`` / ``transcript_url: null`` / ``summary_url: null`` and never
uploaded anything to GCS — and their Spotify fields are null too, so the
platform player (signed-URL MP3 stream, PR #120) had nothing to play.

For each episode id this script:
  1. loads the seed JSON from seed_data/<ep_id>.json (episode_url, transcript,
     sentences — recover them from git if missing locally),
  2. downloads the MP3 from the original feed URL when it isn't on disk,
  3. uploads MP3 + transcript JSON + summary markdown to GCS,
  4. merge-updates the Firestore episode doc with the resulting URL fields.

The summary uploaded to GCS is the doc's current ``summary_content`` (it may
have been regenerated after seeding), falling back to the seed JSON's copy.

Usage:
    python scripts/backfill_seed_episode_media.py                 # all seed_data/ep_*.json
    python scripts/backfill_seed_episode_media.py ep_324f18c4 ... # explicit ids
    python scripts/backfill_seed_episode_media.py --dry-run
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from seed_new_podcasts import (  # noqa: E402  (bootstraps secrets)
    SEED_DIR,
    log,
    upload_episode_media,
)
from src.service.firestore_service import FirestoreService  # noqa: E402
from src.service.gcs_storage_service import GCSStorageService  # noqa: E402

URL_FIELDS = (
    "mp3_url", "mp3_public_url",
    "transcript_url", "transcript_public_url",
    "summary_url", "summary_public_url",
)


def backfill_episode(
    ep_id: str, fs: FirestoreService, gcs: GCSStorageService, dry_run: bool
) -> bool:
    seed_file = SEED_DIR / f"{ep_id}.json"
    if not seed_file.exists():
        log(f"  SKIP {ep_id}: no seed JSON at {seed_file}")
        return False
    with open(seed_file, encoding="utf-8") as f:
        data = json.load(f)

    doc = fs.get_document("episodes", ep_id)
    if not doc:
        log(f"  SKIP {ep_id}: episode doc not found in Firestore")
        return False

    missing = [k for k in ("mp3_url", "transcript_url", "summary_url") if not doc.get(k)]
    if not missing:
        log(f"  SKIP {ep_id}: all media URLs already set")
        return True
    log(f"  {ep_id} | {doc.get('episode_title', '')[:50]} | missing: {', '.join(missing)}")

    if dry_run:
        log("    [dry-run] would upload media and patch the doc")
        return True

    media_urls = upload_episode_media(gcs, data, summary_content=doc.get("summary_content"))
    if not media_urls.get("mp3_url"):
        log("    WARNING: MP3 upload failed — episode stays unplayable")
    update = {k: v for k, v in media_urls.items() if v}
    if not update:
        log("    Nothing uploaded; doc left unchanged")
        return False

    fs.set_document("episodes", ep_id, update, merge=True)
    log(f"    Patched doc with: {', '.join(sorted(update))}")
    return bool(media_urls.get("mp3_url"))


def main():
    ap = argparse.ArgumentParser(description="Backfill GCS media for seeded ep_* episodes")
    ap.add_argument("episode_ids", nargs="*", help="episode ids (default: every seed_data/ep_*.json)")
    ap.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    args = ap.parse_args()

    ids = args.episode_ids or sorted(p.stem for p in SEED_DIR.glob("ep_*.json"))
    if not ids:
        log(f"No episode ids given and no seed JSONs in {SEED_DIR}")
        sys.exit(1)

    fs = FirestoreService()
    gcs = GCSStorageService()

    ok = 0
    for ep_id in ids:
        if backfill_episode(ep_id, fs, gcs, args.dry_run):
            ok += 1
    log(f"\nDone: {ok}/{len(ids)} episodes have playable media")
    sys.exit(0 if ok == len(ids) else 2)


if __name__ == "__main__":
    main()
