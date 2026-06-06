#!/usr/bin/env python3
"""Publish a data-contract markdown file into the wiki Postgres as
``contract/<slug>``.

This is the canonical home for cross-team contracts (Firestore schema,
trending feed shape, etc.). Storing them in the same Postgres the rest of the
wiki uses gives both repos a single live URL to fetch:

    GET <podcast-api>/api/wiki/pages/contract/<slug>
    GET <podcast-api>/api/wiki/pages/contract/<slug>.md

Edits flow through the same upsert path the rest of the wiki uses, so writes
remain idempotent and the existing read endpoints serve the result without
any extra route.

Usage:
    uv run python services/podcast/scripts/publish_contract.py \\
        --slug firestore-schema \\
        --file docs/spec-from-platform.md \\
        --title "firestore-schema Specification"

Per the spec's own versioning rule (§ Scope: "the folder is intentionally
unversioned — bump schema_version inline"), the slug stays stable; only the
``schema_version`` integer in the body and frontmatter changes.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "libs" / "shared" / "src"))

from shared.secrets import bootstrap  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--slug", required=True, help="slug under the contract kind")
    ap.add_argument("--file", required=True, type=Path, help="markdown body to publish")
    ap.add_argument("--title", default="", help="display title for the page")
    ap.add_argument(
        "--database-url",
        default=None,
        help="Postgres URL (defaults to WIKI_DATABASE_URL after secrets bootstrap)",
    )
    ap.add_argument(
        "--source",
        default="",
        help="optional source attribution string stored in frontmatter (e.g. file path)",
    )
    args = ap.parse_args()

    # Pull WIKI_DATABASE_URL (and friends) from Google Secret Manager so the
    # script works the same way in dev as it does on the VPS.
    bootstrap()
    database_url = args.database_url or os.environ.get("WIKI_DATABASE_URL")

    if not database_url:
        print("error: no --database-url and WIKI_DATABASE_URL is not set", file=sys.stderr)
        return 2
    if not args.file.exists():
        print(f"error: file not found: {args.file}", file=sys.stderr)
        return 2

    body = args.file.read_text(encoding="utf-8")

    from shared.wiki_builder import WikiPage  # noqa: E402
    from shared.wiki_builder.postgres_repo import PostgresWikiRepository  # noqa: E402

    frontmatter: dict = {}
    if args.source:
        frontmatter["source"] = args.source

    page = WikiPage(
        kind="contract",
        slug=args.slug,
        title=args.title or args.slug,
        frontmatter=frontmatter,
        body=body,
    )
    repo = PostgresWikiRepository(database_url)
    written = repo.upsert_page(page)
    print(f"Published contract/{args.slug} ({len(body):,} bytes)")
    print(f"  updated_at={written.updated_at}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
