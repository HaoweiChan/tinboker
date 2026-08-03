#!/usr/bin/env python3
"""Refresh ``trending_tickers/{ticker}`` from ``ticker_insights`` source.

Intended cadence: hourly via the background worker. Always a full recompute —
streams the whole ``ticker_insights`` collection group and rewrites every
``trending_tickers/{ticker}`` doc. See ``docs/firestore-contract.md`` § 5 for
the schema this writes.

Usage:
    uv run python services/podcast/scripts/refresh_trending_tickers.py
    uv run python services/podcast/scripts/refresh_trending_tickers.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVICE_ROOT))

from src.podcast.exporters import postgres_mirror  # noqa: E402
from src.podcast.exporters.trending_tickers import (  # noqa: E402
    aggregate_trending,
    fetch_all_insights,
    write_trending,
)
from src.service.upload_to_firebase import (
    FirebaseService,  # noqa: E402 (also bootstraps GSM secrets, incl. EPISODE_DATABASE_URL)
)


def _mirror_trending_to_postgres(docs: dict) -> None:
    """Best-effort dual-write into ``firestore_mirror.trending_tickers``: upsert every
    recomputed ticker doc, then prune rows whose ticker fell out of this full
    recompute. No-op without ``EPISODE_DATABASE_URL``. Firestore write (above) is
    untouched either way."""
    if not docs:
        return  # matches write_trending's own no-op guard — never prune on an empty set
    url = os.getenv("EPISODE_DATABASE_URL")
    if not url:
        return
    try:
        import psycopg
    except ImportError:
        print("  ⚠ psycopg not available — skipping Postgres trending_tickers mirror")
        return

    try:
        with psycopg.connect(url, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(postgres_mirror.DDL_TRENDING_TICKERS)
            n = postgres_mirror.upsert_trending_tickers(cur, docs)
            pruned = postgres_mirror.prune_trending_tickers(cur, list(docs.keys()))
        print(
            f"  ✓ Mirrored {n} trending_tickers docs to Postgres "
            f"({postgres_mirror.SCHEMA}.trending_tickers); pruned {pruned} stale"
        )
    except Exception as e:  # noqa: BLE001 — best-effort
        import traceback

        print(f"  ⚠ Postgres trending_tickers mirror failed (non-fatal): {e}")
        traceback.print_exc()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="don't write")
    ap.add_argument("--top-n", type=int, default=5, help="top_podcasters/top_episodes cap")
    args = ap.parse_args()

    fb = FirebaseService()
    now = datetime.now(timezone.utc)

    print("Streaming full ticker_insights collection group...")
    insights = fetch_all_insights(fb.db)
    print(f"  read {len(insights)} insight docs")

    docs = aggregate_trending(insights, top_n=args.top_n, now=now)
    print(f"  aggregated into {len(docs)} ticker rows")

    if args.dry_run:
        sample = list(docs.items())[:3]
        print("Sample (first 3):")
        print(json.dumps(dict(sample), ensure_ascii=False, indent=2, default=str))
        return 0

    written = write_trending(fb.db, docs)
    print(f"  wrote {written} trending_tickers docs")

    _mirror_trending_to_postgres(docs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
