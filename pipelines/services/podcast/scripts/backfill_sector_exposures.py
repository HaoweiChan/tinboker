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

# Populate os.environ from Secret Manager (GCS_BUCKET_NAME for the summary
# hydration below, FIRESTORE_DATABASE_ID, …) before any client is built.
from src.secrets_bootstrap import bootstrap  # noqa: E402

bootstrap()

from google.cloud import firestore  # noqa: E402
from shared.sectors import (  # noqa: E402
    current_exposure_ids,
    flatten_exposure_ids,
    flatten_unresolved_trend_ids,
    resolve_text,
)
from src.service.gcs_storage_service import GCSStorageService  # noqa: E402
from src.service.upload_to_firebase import FirebaseService  # noqa: E402


def has_dead_id(ep: dict[str, Any], current_ids: set[str]) -> bool:
    """True if the episode carries any exposure id absent from the current universe."""
    ids = ep.get("sector_exposure_ids") or [
        e.get("exposure_id") for e in (ep.get("sector_exposures") or [])
    ]
    return any(i and i not in current_ids for i in ids)


def hydrated_summary(ep: dict[str, Any], gcs: GCSStorageService | None) -> str:
    """The episode summary, hydrated from GCS when the inline field is empty.

    Published/consolidated episodes keep ``summary_content`` empty in Firestore and
    store the real text as a GCS blob at ``summary_url`` (the backend hydrates it at
    read time via ``episode_transformer._GCS_CONTENT_FIELDS``). The resolver needs
    that full text — without it the backfill sees only title/insights/tags and
    under-resolves, then OVERWRITES the richer existing exposures with a sparse set.
    """
    inline = str(ep.get("summary_content") or "").strip()
    if inline:
        return inline
    url = ep.get("summary_url")
    if gcs and isinstance(url, str) and url.startswith("gs://"):
        try:
            return gcs.download_text_by_gcs_url(url)
        except Exception:  # noqa: BLE001 — missing/unauthorized/moved blob → degrade
            return ""
    return ""


def episode_text(ep: dict[str, Any], gcs: GCSStorageService | None = None) -> str:
    """Best-effort text for the resolver from already-stored episode fields."""
    parts = [
        str(ep.get("episode_title") or ep.get("title") or ""),
        hydrated_summary(ep, gcs),
        " ".join(str(x) for x in (ep.get("key_insights") or [])),
        " ".join(str(x) for x in (ep.get("tags") or [])),
    ]
    return " \n".join(p for p in parts if p)


def build_update(
    ep: dict[str, Any],
    gcs: GCSStorageService | None = None,
    *,
    require_live_universe: bool = False,
) -> dict[str, Any] | None:
    """Return the sector-metadata merge update, or None when nothing resolved."""
    resolved = resolve_text(
        episode_text(ep, gcs),
        require_live_universe=require_live_universe,
    )
    exposures = resolved["sector_exposures"]
    unresolved = resolved["unresolved_market_trends"]
    if not exposures and not unresolved:
        return None
    # Safety: never overwrite an existing non-empty exposure set with nothing. If the
    # resolve produced no exposures (e.g. the summary blob was missing so only
    # title/tags were seen), leave the stored data alone rather than wiping it.
    if not exposures and (ep.get("sector_exposures") or ep.get("sector_exposure_ids")):
        return None
    flat = flatten_exposure_ids(exposures)
    return {
        "sector_exposures": exposures,
        "unresolved_market_trends": unresolved,
        **flat,
        "unresolved_market_trend_ids": flatten_unresolved_trend_ids(unresolved),
        # Unified namespace: purge the retired flat theme_ids index (folded into sector_ids).
        "theme_ids": firestore.DELETE_FIELD,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=50, help="most-recent episodes to scan")
    ap.add_argument("--episode-id", help="backfill a single episode id")
    ap.add_argument("--commit", action="store_true", help="write (default: dry-run)")
    ap.add_argument(
        "--stale-only",
        action="store_true",
        help="only touch episodes carrying a dead (dropped-from-universe) exposure id; "
        "skip those already on the current taxonomy (protects verified/fresh sets)",
    )
    ap.add_argument(
        "--require-live-universe",
        action="store_true",
        help="fail instead of using shared/sectors_seed_backup.py when /api/sectors/universe is unavailable",
    )
    args = ap.parse_args()

    fb = FirebaseService()
    col = fb.db.collection("episodes")
    current_ids = current_exposure_ids(require_live_universe=args.require_live_universe)

    # Best-effort GCS reader so we can hydrate summaries stored as blobs (empty
    # inline). If the bucket env is missing, degrade to inline-only text.
    try:
        gcs: GCSStorageService | None = GCSStorageService()
    except Exception as exc:  # noqa: BLE001
        print(f"Warning: GCS unavailable ({exc}); resolving over inline text only.")
        gcs = None

    if args.episode_id:
        snap = col.document(args.episode_id).get()
        snaps = [snap] if snap.exists else []
    else:
        snaps = list(
            col.order_by("created_time", direction="DESCENDING").limit(args.limit).stream()
        )

    scanned = 0
    skipped_current = 0
    hits: list[tuple[str, list[str]]] = []
    written = 0
    for snap in snaps:
        ep = snap.to_dict() or {}
        scanned += 1
        # Under --stale-only, leave episodes that are already on the current taxonomy
        # alone (no dead ids) — cheap check that also avoids a GCS summary fetch.
        if args.stale_only and not has_dead_id(ep, current_ids):
            skipped_current += 1
            continue
        update = build_update(ep, gcs, require_live_universe=args.require_live_universe)
        if not update:
            continue
        hits.append((snap.id, update["sector_exposure_ids"]))
        if args.commit:
            col.document(snap.id).set(update, merge=True)
            written += 1

    scope = " (stale-only)" if args.stale_only else ""
    print(f"Scanned {scanned} episodes{scope}; {len(hits)} to refresh.")
    if args.stale_only:
        print(f"Skipped {skipped_current} already on the current taxonomy.")
    for ep_id, ids in hits[:40]:
        print(f"  {ep_id}: {ids}")
    if args.commit:
        print(f"Committed sector metadata to {written} episodes.")
    else:
        print("(dry-run — pass --commit to write to Firestore)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
