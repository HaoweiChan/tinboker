#!/usr/bin/env python3
"""Phase E: rewrite gs:// URLs in the episodes table to VPS HTTPS paths.

Idempotent — safe to re-run. Episodes that already have VPS paths are skipped.

URL scheme:
    gs://podcast-data-web/<path>    -> https://podcast-api.tinboker.com/media/web/<path>
    gs://graphfolio-articles/<path> -> https://podcast-api.tinboker.com/media/articles/<path>

Columns updated (all *_url fields on the episodes table):
    mp3_url, transcript_url, summary_url, summary_image_url,
    events_markdown_url, sentences_markdown_url, marp_markdown_url,
    ticker_marp_markdown_url, ticker_recommendations_url

Usage:
    uv run python services/podcast/scripts/migrate_urls_gcs_to_vps.py --dry-run
    uv run python services/podcast/scripts/migrate_urls_gcs_to_vps.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "libs" / "shared" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

VPS_BASE = "https://podcast-api.tinboker.com/media"

_BUCKET_MAP = {
    "gs://podcast-data-web/": f"{VPS_BASE}/web/",
    "gs://graphfolio-articles/": f"{VPS_BASE}/articles/",
}

URL_COLUMNS = [
    "mp3_url",
    "transcript_url",
    "summary_url",
    "summary_image_url",
    "events_markdown_url",
    "sentences_markdown_url",
    "marp_markdown_url",
    "ticker_marp_markdown_url",
    "ticker_recommendations_url",
]


def _rewrite(url: str | None) -> str | None:
    if not url:
        return url
    for gs_prefix, vps_prefix in _BUCKET_MAP.items():
        if url.startswith(gs_prefix):
            return vps_prefix + url[len(gs_prefix):]
    return url  # already VPS URL or unknown — leave untouched


def main() -> int:
    try:
        from secrets_bootstrap import bootstrap  # type: ignore[import-untyped]
        bootstrap()
    except ImportError:
        pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="report counts but skip writes")
    ap.add_argument("--wiki-url", default=os.environ.get("WIKI_DATABASE_URL"))
    args = ap.parse_args()

    if not args.wiki_url:
        print("ERROR: WIKI_DATABASE_URL not set", file=sys.stderr)
        return 2

    import psycopg  # type: ignore[import-untyped]
    import psycopg.rows  # type: ignore[import-untyped]

    conn_url = args.wiki_url.replace("postgresql+psycopg://", "postgresql://", 1)
    conn = psycopg.connect(conn_url, row_factory=psycopg.rows.dict_row)

    # Fetch all episodes that still have gs:// URLs in any column
    gs_filter = " OR ".join(
        f"{col} LIKE 'gs://%'" for col in URL_COLUMNS
    )
    with conn.cursor() as cur:
        cur.execute(f"SELECT id, {', '.join(URL_COLUMNS)} FROM episodes WHERE {gs_filter}")
        rows = cur.fetchall()

    print(f"Episodes with gs:// URLs: {len(rows)}")
    if not rows:
        print("Nothing to migrate.")
        conn.close()
        return 0

    updated = 0
    skipped = 0
    for row in rows:
        ep_id = row["id"]
        updates: dict[str, str | None] = {}
        for col in URL_COLUMNS:
            old = row[col]
            new = _rewrite(old)
            if new != old:
                updates[col] = new

        if not updates:
            skipped += 1
            continue

        if args.dry_run:
            print(f"  [dry-run] {ep_id}: would update {list(updates.keys())}")
            updated += 1
            continue

        set_clause = ", ".join(f"{col} = %({col})s" for col in updates)
        params = {**updates, "id": ep_id}
        with conn.cursor() as cur:
            cur.execute(f"UPDATE episodes SET {set_clause} WHERE id = %(id)s", params)
        updated += 1

    if not args.dry_run:
        conn.commit()

    print(f"{'[dry-run] would update' if args.dry_run else 'Updated'} {updated} episodes, skipped {skipped}")

    # Spot-check
    if not args.dry_run and updated > 0:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, mp3_url FROM episodes WHERE mp3_url LIKE 'https://podcast-api%' LIMIT 3"
            )
            samples = cur.fetchall()
        print("\nSample updated rows:")
        for s in samples:
            print(f"  {s['id']}: {s['mp3_url']}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
