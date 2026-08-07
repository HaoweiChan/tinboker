#!/usr/bin/env python3
"""Refresh ``trending_tickers/{ticker}`` from the ``ticker_insights`` source.

Intended cadence: hourly via the background worker. Always a full recompute —
reads every ``firestore_mirror.ticker_insights`` row and rewrites every
``firestore_mirror.trending_tickers`` row. See ``docs/firestore-contract.md``
§ 5 for the doc schema and § 11.5 for why both ends are Postgres now (P4: the
Firestore read source and write target are both gone).

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
from src.podcast.exporters.trending_tickers import aggregate_trending  # noqa: E402
from src.secrets_bootstrap import bootstrap  # noqa: E402


def _connect():
    import psycopg

    url = os.getenv("EPISODE_DATABASE_URL")
    if not url:
        raise RuntimeError("EPISODE_DATABASE_URL is not set — cannot refresh trending.")
    return psycopg.connect(url, autocommit=True)


def _read_all_insights() -> list[dict]:
    """Every ``firestore_mirror.ticker_insights`` doc — the § 4 shape
    ``aggregate_trending`` expects, same as the old Firestore collection-group
    stream returned."""
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(postgres_mirror.DDL_TICKER_INSIGHTS)
        cur.execute(f'SELECT doc FROM "{postgres_mirror.SCHEMA}".ticker_insights')
        return [row[0] for row in cur.fetchall() if row[0]]


def _write_trending_to_postgres(docs: dict) -> None:
    """Upsert every recomputed ticker doc, then prune rows whose ticker fell out
    of this full recompute. Sole write since P4 — raises on failure so the hourly
    timer surfaces a red unit instead of silently serving a frozen table."""
    if not docs:
        return  # never prune on an empty recompute — that would wipe the table
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(postgres_mirror.DDL_TRENDING_TICKERS)
        n = postgres_mirror.upsert_trending_tickers(cur, docs)
        pruned = postgres_mirror.prune_trending_tickers(cur, list(docs.keys()))
    print(
        f"  wrote {n} trending_tickers docs "
        f"({postgres_mirror.SCHEMA}.trending_tickers); pruned {pruned} stale"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="don't write")
    ap.add_argument("--top-n", type=int, default=5, help="top_podcasters/top_episodes cap")
    args = ap.parse_args()

    bootstrap()  # populates EPISODE_DATABASE_URL from GSM
    now = datetime.now(timezone.utc)

    print("Reading firestore_mirror.ticker_insights...")
    insights = _read_all_insights()
    print(f"  read {len(insights)} insight docs")

    docs = aggregate_trending(insights, top_n=args.top_n, now=now)
    print(f"  aggregated into {len(docs)} ticker rows")

    if args.dry_run:
        sample = list(docs.items())[:3]
        print("Sample (first 3):")
        print(json.dumps(dict(sample), ensure_ascii=False, indent=2, default=str))
        return 0

    _write_trending_to_postgres(docs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
