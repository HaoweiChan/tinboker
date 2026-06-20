#!/usr/bin/env python3
"""Purge orphan ticker_insights — docs whose episode no longer exists.

Repeated/old pipeline runs left ticker_insights docs under episode_ids that have
NO matching document in the ``episodes`` collection. They are dated by their
ingestion time (``podcast_launch_time == created_at``), carry a small rotating
set of generic theses, and have no resolvable episode — so /picks shows e.g.
"近期連續點名 27 次" for a podcaster that only published a few episodes.

The discriminator is principled (not thesis-pattern matching): an insight whose
``episode_id`` is not a real episode is junk. This fixes EVERY channel at once.

DRY-RUN BY DEFAULT: prints the blast radius and deletes nothing. ``--apply`` deletes.

Usage:
    uv run python services/podcast/scripts/purge_orphan_insights.py
    uv run python services/podcast/scripts/purge_orphan_insights.py --podcast "Gooaye 股癌"
    uv run python services/podcast/scripts/purge_orphan_insights.py --apply
"""

from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVICE_ROOT))
sys.path.insert(0, str(_SERVICE_ROOT / "src"))

try:
    from src.secrets_bootstrap import bootstrap  # noqa: E402

    bootstrap()
except Exception as _e:  # noqa: BLE001
    print(f"  (secrets_bootstrap skipped: {_e})")

from src.service.upload_to_firebase import FirebaseService  # noqa: E402

INSIGHTS_SUBCOLLECTION = "tickers"
EPISODES_COLLECTION = "episodes"
SUPPORTED_SCHEMA = {2, 3}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="delete orphan docs (default: dry-run)")
    ap.add_argument("--podcast", help="only this podcaster (uses the tickers.podcaster index)")
    args = ap.parse_args()
    dry = not args.apply

    fb = FirebaseService()

    # Real episode ids — fetch ids only (no field payloads) for speed.
    print("loading episode ids …")
    episode_ids = {doc.id for doc in fb.db.collection(EPISODES_COLLECTION).select([]).stream()}
    print(f"  {len(episode_ids)} real episodes")

    query = fb.db.collection_group(INSIGHTS_SUBCOLLECTION)
    if args.podcast:
        query = query.where("podcaster", "==", args.podcast)

    scanned = 0
    orphans: list = []
    orphan_by_pod: collections.Counter = collections.Counter()
    kept_by_pod: collections.Counter = collections.Counter()
    samples: list = []
    for doc in query.stream():
        d = doc.to_dict() or {}
        if d.get("schema_version") not in SUPPORTED_SCHEMA:
            continue
        scanned += 1
        eid = d.get("episode_id")
        pod = d.get("podcaster") or "?"
        if eid not in episode_ids:
            orphans.append(doc.reference)
            orphan_by_pod[pod] += 1
            if len(samples) < 10:
                samples.append((pod, d.get("ticker"), eid, (d.get("podcast_launch_time") or "")[:10]))
        else:
            kept_by_pod[pod] += 1

    print(f"\nscanned schema-{sorted(SUPPORTED_SCHEMA)} insights: {scanned}")
    print(f"ORPHAN (episode missing): {len(orphans)}")
    print("orphans by podcaster:", dict(orphan_by_pod.most_common(20)))
    print("kept (real episode)   :", dict(kept_by_pod.most_common(20)))
    print("\norphan samples (podcaster, ticker, episode_id, launch_date):")
    for s in samples:
        print("   ", s)

    if dry:
        print("\nDRY-RUN — nothing deleted. Re-run with --apply to delete.")
        return 0

    deleted = 0
    batch = fb.db.batch()
    pending = 0
    for ref in orphans:
        batch.delete(ref)
        pending += 1
        if pending >= 450:  # stay under the 500-op batch limit
            batch.commit()
            deleted += pending
            print(f"  …deleted {deleted}")
            batch = fb.db.batch()
            pending = 0
    if pending:
        batch.commit()
        deleted += pending
    print(f"\ndeleted {deleted} orphan docs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
