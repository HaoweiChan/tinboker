#!/usr/bin/env python3
"""Recompute ``trending_tickers/{ticker}`` from ``ticker_insights`` source.

Intended cadence: nightly (cron / systemd timer). Idempotent — re-running just
overwrites each doc with a fresh aggregate. See ``docs/spec-from-platform.md``
§ 5 for the schema this writes.

Usage:
    uv run python services/podcast/scripts/refresh_trending_tickers.py
    uv run python services/podcast/scripts/refresh_trending_tickers.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVICE_ROOT))

from src.podcast.exporters.trending_tickers import (  # noqa: E402
    aggregate_trending,
    fetch_all_insights,
    write_trending,
)
from src.service.upload_to_firebase import FirebaseService  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="don't write")
    ap.add_argument("--top-n", type=int, default=5, help="top_podcasters/top_episodes cap")
    args = ap.parse_args()

    fb = FirebaseService()
    print("Streaming ticker_insights collection group...")
    insights = fetch_all_insights(fb.db)
    print(f"  read {len(insights)} insight docs")

    docs = aggregate_trending(insights, top_n=args.top_n)
    print(f"  aggregated into {len(docs)} ticker rows")

    if args.dry_run:
        sample = list(docs.items())[:3]
        print("Sample (first 3):")
        print(json.dumps(dict(sample), ensure_ascii=False, indent=2, default=str))
        return 0

    written = write_trending(fb.db, docs)
    print(f"  wrote {written} trending_tickers docs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
