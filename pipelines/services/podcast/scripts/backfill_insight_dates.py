#!/usr/bin/env python3
"""Correct ticker_insights ``podcast_launch_time`` to the episode's true publish date.

Many insights were stamped with their INGESTION time (``podcast_launch_time ==
created_time``) instead of the episode's real release date. When a podcaster's
back-catalogue is ingested over a few weeks, every episode's picks collapse into
the same fortnight on /picks (e.g. Gooaye AAPL "近期連續點名 27 次") even though the
episodes really span months/years.

The episode docs already carry the truth in ``released_at_ms`` (epoch ms). This
script joins each insight to its episode and rewrites ``podcast_launch_time`` to
that date. No re-extraction, no LLM — a pure date repair.

DRY-RUN BY DEFAULT: prints before→after samples and counts; ``--apply`` writes.

Usage:
    uv run python services/podcast/scripts/backfill_insight_dates.py --podcast "Gooaye 股癌"
    uv run python services/podcast/scripts/backfill_insight_dates.py --apply
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

from src.podcast.exporters.ticker_insights import _iso_utc  # noqa: E402
from src.service.upload_to_firebase import FirebaseService  # noqa: E402

INSIGHTS_SUBCOLLECTION = "tickers"
EPISODES_COLLECTION = "episodes"
SUPPORTED_SCHEMA = {2, 3}


def true_publish(ep: dict) -> str | None:
    """Episode's real publish date as ISO-UTC, preferring released_at_ms."""
    for key in ("released_at_ms", "spotify_release_date"):
        v = ep.get(key)
        if v not in (None, "", 0):
            try:
                return _iso_utc(v)
            except Exception:  # noqa: BLE001
                continue
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write corrected dates (default: dry-run)")
    ap.add_argument("--podcast", help="only this podcaster (uses the tickers.podcaster index)")
    args = ap.parse_args()
    dry = not args.apply

    fb = FirebaseService()

    print("loading episode publish dates …")
    pub: dict[str, str] = {}
    for doc in fb.db.collection(EPISODES_COLLECTION).stream():
        d = doc.to_dict() or {}
        iso = true_publish(d)
        if iso:
            pub[doc.id] = iso
    print(f"  {len(pub)} episodes with a publish date")

    query = fb.db.collection_group(INSIGHTS_SUBCOLLECTION)
    if args.podcast:
        query = query.where("podcaster", "==", args.podcast)

    scanned = fixable = no_episode = already_ok = 0
    fix_by_pod: collections.Counter = collections.Counter()
    samples: list = []
    to_fix: list = []
    for doc in query.stream():
        d = doc.to_dict() or {}
        if d.get("schema_version") not in SUPPORTED_SCHEMA:
            continue
        scanned += 1
        correct = pub.get(d.get("episode_id"))
        if not correct:
            no_episode += 1
            continue
        current = d.get("podcast_launch_time")
        if current == correct:
            already_ok += 1
            continue
        fixable += 1
        fix_by_pod[d.get("podcaster") or "?"] += 1
        to_fix.append((doc.reference, correct))
        if len(samples) < 12:
            samples.append((d.get("podcaster"), d.get("ticker"), str(current)[:10], correct[:10]))

    print(f"\nscanned={scanned} already_correct={already_ok} no_episode_date={no_episode} TO_FIX={fixable}")
    print("to-fix by podcaster:", dict(fix_by_pod.most_common(20)))
    print("\nsamples (podcaster, ticker, current_date → corrected_date):")
    for s in samples:
        print(f"    {s[0]} {s[1]}: {s[2]} → {s[3]}")

    if dry:
        print("\nDRY-RUN — nothing written. Re-run with --apply to correct dates.")
        return 0

    written = 0
    batch = fb.db.batch()
    pending = 0
    for ref, correct in to_fix:
        batch.update(ref, {"podcast_launch_time": correct})
        pending += 1
        if pending >= 450:
            batch.commit()
            written += pending
            print(f"  …updated {written}")
            batch = fb.db.batch()
            pending = 0
    if pending:
        batch.commit()
        written += pending
    print(f"\nupdated {written} insight dates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
