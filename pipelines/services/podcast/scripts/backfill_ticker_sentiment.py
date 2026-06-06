#!/usr/bin/env python3
"""Backfill `frontmatter.ticker_sentiment` onto existing wiki episode pages.

`ingest_episode` now writes a structured `ticker_sentiment` map ({canonical symbol -> bull|bear|
neut}) into each episode page's frontmatter — the `/api/wiki/stats/*` aggregates read it. Pages
created before that change still have the data only in the rendered "## Ticker Recommendations"
markdown table; this script parses that table and writes the map. Idempotent — re-run safely.

Usage:
    uv run python services/podcast/scripts/backfill_ticker_sentiment.py \
        --database-url postgresql+psycopg://user:pass@127.0.0.1:5432/tinboker_wiki [--dry-run]

If `--database-url` is omitted, `WIKI_DATABASE_URL` from the environment is used.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "libs" / "shared" / "src"))

from shared.tickers import canonical_symbol  # noqa: E402
from shared.wiki_builder import WikiPage  # noqa: E402
from shared.wiki_builder.records import normalize_sentiment  # noqa: E402

_HEADER = "## Ticker Recommendations"


def _parse_table(body: str) -> dict[str, str]:
    """Extract {canonical symbol -> sentiment} from the Ticker Recommendations table."""
    out: dict[str, str] = {}
    lines = body.splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == _HEADER)
    except StopIteration:
        return out
    for ln in lines[start + 1 :]:
        s = ln.strip()
        if s.startswith("#"):  # next section
            break
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        # header row / separator row / short rows
        if len(cells) < 2 or cells[0].lower() in {"ticker", ""} or set(cells[0]) <= set("-: "):
            continue
        sym, sent = cells[0], normalize_sentiment(cells[1])
        if sym and sent:
            out[canonical_symbol(sym)] = sent
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--database-url", default=os.environ.get("WIKI_DATABASE_URL"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.database_url:
        print("no --database-url and WIKI_DATABASE_URL is not set", file=sys.stderr)
        return 2

    from shared.wiki_builder.postgres_repo import PostgresWikiRepository

    repo = PostgresWikiRepository(args.database_url)
    updated, unchanged, no_table = 0, 0, 0
    for page in repo.list_pages(kind="episode", limit=1_000_000):
        parsed = _parse_table(page.body)
        if not parsed:
            no_table += 1
            continue
        if page.frontmatter.get("ticker_sentiment") == parsed:
            unchanged += 1
            continue
        updated += 1
        if args.dry_run:
            print(f"  {page.slug}: {parsed}")
            continue
        fm = dict(page.frontmatter)
        fm["ticker_sentiment"] = parsed
        repo.upsert_page(
            WikiPage(
                kind="episode", slug=page.slug, title=page.title, frontmatter=fm, body=page.body
            )
        )

    verb = "would update" if args.dry_run else "updated"
    print(f"{verb} {updated} pages; {unchanged} already current; {no_table} without a rec table")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
