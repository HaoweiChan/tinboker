#!/usr/bin/env python3
"""Purge templated "watchlist roundup" ticker_insights docs.

Some episodes (long watchlist roundups) produced placeholder theses — a fixed
sentence with the company name swapped in ("X 具備良好的成長動能…", "X 當前面臨的
產業環境具有挑戰…"). They carry no real analysis and pollute /picks. They're
identified by the SAME ``is_boilerplate_thesis`` marker set the exporter now uses
to drop them going forward, so this only removes already-written orphans.

DRY-RUN BY DEFAULT: prints matches and deletes nothing. Pass ``--apply`` to delete.

Usage:
    uv run python services/podcast/scripts/purge_templated_insights.py --podcast "財經一路發"
    uv run python services/podcast/scripts/purge_templated_insights.py --podcast "財經一路發" --apply
    uv run python services/podcast/scripts/purge_templated_insights.py            # all podcasters (dry-run)
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

from src.podcast.exporters.ticker_insights import is_boilerplate_thesis  # noqa: E402
from src.service.upload_to_firebase import FirebaseService  # noqa: E402

INSIGHTS_SUBCOLLECTION = "tickers"
SUPPORTED_SCHEMA = {2, 3}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="delete matched docs (default: dry-run)")
    ap.add_argument("--podcast", help="only this podcaster (uses the tickers.podcaster index)")
    args = ap.parse_args()
    dry = not args.apply

    fb = FirebaseService()
    query = fb.db.collection_group(INSIGHTS_SUBCOLLECTION)
    if args.podcast:
        query = query.where("podcaster", "==", args.podcast)

    matched = []
    by_pod: collections.Counter = collections.Counter()
    kept_examples: list = []
    samples: list = []
    for doc in query.stream():
        d = doc.to_dict() or {}
        if d.get("schema_version") not in SUPPORTED_SCHEMA:
            continue
        if is_boilerplate_thesis(d.get("bluf_thesis")):
            matched.append(doc.reference)
            by_pod[d.get("podcaster") or "?"] += 1
            if len(samples) < 8:
                samples.append((d.get("podcaster"), d.get("ticker"), (d.get("bluf_thesis") or "")[:48]))
        elif len(kept_examples) < 5:
            kept_examples.append((d.get("ticker"), (d.get("bluf_thesis") or "")[:48]))

    print(f"\nmatched {len(matched)} templated insight docs")
    print("by podcaster:", dict(by_pod.most_common(15)))
    print("\nwould DELETE (samples):")
    for s in samples:
        print("   ", s)
    print("\nwould KEEP (real-thesis samples, for contrast):")
    for k in kept_examples:
        print("   ", k)

    if dry:
        print("\nDRY-RUN — nothing deleted. Re-run with --apply to delete.")
        return 0

    deleted = 0
    for ref in matched:
        try:
            ref.delete()
            deleted += 1
        except Exception as e:  # noqa: BLE001
            print(f"  delete failed for {ref.path}: {e}")
    print(f"\ndeleted {deleted} docs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
