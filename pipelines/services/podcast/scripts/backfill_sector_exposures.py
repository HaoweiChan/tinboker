#!/usr/bin/env python3
"""Backfill sector/theme exposures onto existing episode docs.

Runs the deterministic offline resolver over each episode's already-stored text
(title + summary + key_insights + tags) and writes ``sector_exposures`` plus the
flat companion id arrays back to ``episodes/{id}``.

This is additive and idempotent: it only sets the sector/theme metadata fields
and NEVER touches ``related_tickers``, ``ticker_insights``, ``created_time``, or
the platform-owned ``modified_*`` fields. Sector-derived ``resolved_tickers`` are
inferred exposure metadata only — they do not enter ticker indices or trigger
notifications (see docs/firestore-contract.md § 2.1.1 / § 6).

Usage:
    uv run python services/podcast/scripts/backfill_sector_exposures.py --limit 50
    uv run python services/podcast/scripts/backfill_sector_exposures.py --limit 200 --commit
    uv run python services/podcast/scripts/backfill_sector_exposures.py --episode-id <id> --commit
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVICE_ROOT))

from shared.sectors import (  # noqa: E402
    flatten_exposure_ids,
    flatten_unresolved_trend_ids,
    resolve_text,
)
from src.service.upload_to_firebase import FirebaseService  # noqa: E402


def episode_text(ep: dict[str, Any]) -> str:
    """Best-effort text for the resolver from already-stored episode fields."""
    parts = [
        str(ep.get("episode_title") or ep.get("title") or ""),
        str(ep.get("summary_content") or ""),
        " ".join(str(x) for x in (ep.get("key_insights") or [])),
        " ".join(str(x) for x in (ep.get("tags") or [])),
    ]
    return " \n".join(p for p in parts if p)


def build_update(ep: dict[str, Any]) -> dict[str, Any] | None:
    """Return the sector-metadata merge update, or None when nothing resolved."""
    resolved = resolve_text(episode_text(ep))
    exposures = resolved["sector_exposures"]
    unresolved = resolved["unresolved_market_trends"]
    if not exposures and not unresolved:
        return None
    flat = flatten_exposure_ids(exposures)
    return {
        "sector_exposures": exposures,
        "unresolved_market_trends": unresolved,
        **flat,
        "unresolved_market_trend_ids": flatten_unresolved_trend_ids(unresolved),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=50, help="most-recent episodes to scan")
    ap.add_argument("--episode-id", help="backfill a single episode id")
    ap.add_argument("--commit", action="store_true", help="write (default: dry-run)")
    args = ap.parse_args()

    fb = FirebaseService()
    col = fb.db.collection("episodes")

    if args.episode_id:
        snap = col.document(args.episode_id).get()
        snaps = [snap] if snap.exists else []
    else:
        snaps = list(
            col.order_by("created_time", direction="DESCENDING").limit(args.limit).stream()
        )

    scanned = 0
    hits: list[tuple[str, list[str]]] = []
    written = 0
    for snap in snaps:
        ep = snap.to_dict() or {}
        scanned += 1
        update = build_update(ep)
        if not update:
            continue
        hits.append((snap.id, update["sector_exposure_ids"]))
        if args.commit:
            col.document(snap.id).set(update, merge=True)
            written += 1

    print(f"Scanned {scanned} episodes; {len(hits)} matched a sector/theme exposure.")
    for ep_id, ids in hits[:40]:
        print(f"  {ep_id}: {ids}")
    if args.commit:
        print(f"Committed sector metadata to {written} episodes.")
    else:
        print("(dry-run — pass --commit to write to Firestore)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
