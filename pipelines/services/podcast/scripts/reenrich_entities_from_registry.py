#!/usr/bin/env python3
"""Backfill ticker-registry metadata onto existing wiki entity pages.

`ingest_episode` already stamps new entity pages with the registry's display name / market /
sector / entity_type (see `shared.tickers` + `libs/shared/src/shared/data/tickers.json`). This
script applies the same enrichment to entity pages that were created before the registry existed
(or before `tickers.json` was expanded) — for every `kind='entity'` page whose slug resolves to a
known ticker, it updates `title`, `frontmatter.{name,entity_type,tickers,market,sector}`, and the
first `# ...` heading in the body, leaving the rest of the body (episode mentions, ticker history)
intact. Pages not in the registry are left untouched.

Idempotent — re-run it whenever you extend `tickers.json`.

Usage:
    uv run python services/podcast/scripts/reenrich_entities_from_registry.py \
        --database-url postgresql+psycopg://user:pass@127.0.0.1:5432/tinboker_wiki [--dry-run]

If `--database-url` is omitted, `WIKI_DATABASE_URL` from the environment is used.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "libs" / "shared" / "src"))

from shared.tickers import lookup_ticker  # noqa: E402
from shared.wiki_builder import WikiPage  # noqa: E402


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
    updated: list[str] = []
    skipped: list[str] = []
    for page in repo.list_pages(kind="entity", limit=1_000_000):
        info = lookup_ticker(page.slug)
        if not info:
            skipped.append(page.slug)
            continue
        if args.dry_run:
            updated.append(f"{page.slug} -> {info.name} [{info.market}/{info.sector}/{info.type}]")
            continue
        frontmatter = dict(page.frontmatter)
        frontmatter["name"] = info.name
        frontmatter["entity_type"] = info.type
        frontmatter["tickers"] = [info.symbol]
        if info.market:
            frontmatter["market"] = info.market
        if info.sector:
            frontmatter["sector"] = info.sector
        body = re.sub(r"^# .*$", f"# {info.name}", page.body, count=1, flags=re.MULTILINE)
        repo.upsert_page(
            WikiPage(
                kind="entity",
                slug=page.slug,
                title=info.name,
                frontmatter=frontmatter,
                body=body,
            )
        )
        updated.append(f"{page.slug} -> {info.name} [{info.market}/{info.sector}/{info.type}]")

    verb = "would update" if args.dry_run else "updated"
    print(f"{verb} {len(updated)} / {len(updated) + len(skipped)} entity pages:")
    for line in updated:
        print(f"  {line}")
    print(f"skipped {len(skipped)} (not in tickers.json): {sorted(skipped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
