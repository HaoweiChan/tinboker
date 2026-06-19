#!/usr/bin/env python3
"""Refresh ``trending_tickers/{ticker}`` from ``ticker_insights`` source.

Intended cadence: hourly via the background worker. The default delta mode reads
only the recent window to discover touched tickers, then recomputes historical
aggregates for those tickers only. Use ``--mode full`` for Phase B backfills or
audits. See ``docs/firestore-contract.md`` § 5 for the schema this writes.

Usage:
    uv run python services/podcast/scripts/refresh_trending_tickers.py
    uv run python services/podcast/scripts/refresh_trending_tickers.py --lookback-hours 1
    uv run python services/podcast/scripts/refresh_trending_tickers.py --mode full
    uv run python services/podcast/scripts/refresh_trending_tickers.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVICE_ROOT))

from src.podcast.exporters.trending_tickers import (  # noqa: E402
    aggregate_trending,
    delete_orphaned_bare_docs,
    fetch_all_insights,
    fetch_insights_for_ticker_markets,
    fetch_recent_insights,
    touched_ticker_markets,
    write_trending,
)
from src.service.upload_to_firebase import FirebaseService  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="don't write")
    ap.add_argument("--top-n", type=int, default=5, help="top_podcasters/top_episodes cap")
    ap.add_argument(
        "--mode",
        choices=("delta", "full"),
        default="delta",
        help="delta recomputes only tickers touched in the recent window",
    )
    ap.add_argument(
        "--lookback-hours",
        type=float,
        default=1.0,
        help="recent window used by delta mode",
    )
    args = ap.parse_args()

    fb = FirebaseService()
    now = datetime.now(timezone.utc)

    if args.mode == "full":
        print("Streaming full ticker_insights collection group...")
        insights = fetch_all_insights(fb.db)
        print(f"  read {len(insights)} insight docs")
    else:
        since = now - timedelta(hours=args.lookback_hours)
        print(f"Streaming recent ticker_insights since {since.isoformat()}...")
        recent = fetch_recent_insights(fb.db, since)
        touched = touched_ticker_markets(recent)
        print(f"  read {len(recent)} recent docs; touched {len(touched)} ticker/market pairs")
        if not touched:
            print("  no touched tickers; nothing to refresh")
            return 0
        insights = fetch_insights_for_ticker_markets(fb.db, touched)
        print(f"  read {len(insights)} historical docs for touched tickers")

    docs = aggregate_trending(insights, top_n=args.top_n, now=now)
    print(f"  aggregated into {len(docs)} ticker rows")

    if args.dry_run:
        sample = list(docs.items())[:3]
        print("Sample (first 3):")
        print(json.dumps(dict(sample), ensure_ascii=False, indent=2, default=str))
        return 0

    written = write_trending(fb.db, docs)
    print(f"  wrote {written} trending_tickers docs")

    # Prune legacy bare-token docs that the {ticker}.{market} scheme (PR #229)
    # left behind, so the same ticker can't double-list on the platform.
    removed = delete_orphaned_bare_docs(fb.db, docs)
    if removed:
        print(f"  removed {removed} orphaned bare-token docs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
