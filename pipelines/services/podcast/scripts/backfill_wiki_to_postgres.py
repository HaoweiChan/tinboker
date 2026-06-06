#!/usr/bin/env python3
"""One-time backfill: import a markdown ``wiki/`` directory into the Postgres wiki store.

Parses ``episodes|entities|topics|supply-chain/*.md`` (YAML frontmatter + body) and upserts
each as a ``WikiPage`` (which also (re)populates ``wiki_links``). Idempotent — safe to re-run,
and safe to run against several wiki dirs in turn (e.g. ``./wiki`` then ``./services/wiki``);
the latest write wins per ``(kind, slug)``.

Usage:
    uv run python services/podcast/scripts/backfill_wiki_to_postgres.py \
        --wiki-root ./wiki \
        --database-url postgresql+psycopg://user:pass@127.0.0.1:5432/tinboker_wiki [--dry-run]

If ``--database-url`` is omitted, ``WIKI_DATABASE_URL`` from the environment is used.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import yaml

# Make ``shared`` importable when run as a plain script (it is also pip-installed in the venv).
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "libs" / "shared" / "src"))

from shared.wiki_builder import WikiPage, page_to_markdown  # noqa: E402
from shared.wiki_builder.models import DIR_TO_KIND  # noqa: E402

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)
_DIRS = ("episodes", "entities", "topics", "supply-chain")


def _fmt_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))


def _parse(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text.strip()
    try:
        front = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        front = {}
    if not isinstance(front, dict):
        front = {}
    return front, m.group(2).strip()


def _title_for(kind: str, front: dict, slug: str) -> str:
    for key in ("title", "name", "entity"):
        val = front.get(key)
        if val:
            return str(val)
    return slug


def _page_from_file(path: Path, dir_name: str) -> WikiPage:
    kind = DIR_TO_KIND.get(dir_name, dir_name.replace("-", "_"))
    front, body = _parse(path)
    front.pop("type", None)  # ``type`` is represented by ``kind``
    slug = path.stem
    return WikiPage(
        kind=kind, slug=slug, title=_title_for(kind, front, slug), frontmatter=front, body=body
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wiki-root", default="./wiki", type=Path)
    ap.add_argument("--database-url", default=os.environ.get("WIKI_DATABASE_URL"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root: Path = args.wiki_root
    if not root.exists():
        print(f"wiki root not found: {root}", file=sys.stderr)
        return 2

    files: list[tuple[Path, str]] = []
    for d in _DIRS:
        for f in sorted((root / d).glob("*.md")):
            files.append((f, d))
    if not files:
        print(f"no markdown pages under {root}/{{{','.join(_DIRS)}}}")
        return 0

    if args.dry_run:
        counts: dict[str, int] = {}
        for f, d in files:
            page = _page_from_file(f, d)
            counts[page.kind] = counts.get(page.kind, 0) + 1
        print(f"[dry-run] {len(files)} pages: {_fmt_counts(counts)}")
        return 0

    if not args.database_url:
        print("no --database-url and WIKI_DATABASE_URL is not set", file=sys.stderr)
        return 2

    from shared.wiki_builder.postgres_repo import PostgresWikiRepository

    repo = PostgresWikiRepository(args.database_url)
    repo.init_schema()

    counts: dict[str, int] = {}
    mismatches = 0
    for f, d in files:
        page = _page_from_file(f, d)
        stored = repo.upsert_page(page)
        counts[page.kind] = counts.get(page.kind, 0) + 1
        # round-trip sanity check on a sample (cosmetic diffs are expected)
        if page.kind == "episode" and counts["episode"] % 10 == 1:
            rendered = page_to_markdown(stored)
            if page.title and page.title not in rendered:
                mismatches += 1
                print(f"  ⚠ round-trip: title missing in rendered {page.kind}/{page.slug}")

    total = sum(counts.values())
    print(f"backfilled {total} pages from {root}: {_fmt_counts(counts)}")
    n_links = len(repo.list_links())
    print(f"derived links: {n_links}")
    if mismatches:
        print(f"  ({mismatches} round-trip warnings — review above)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
