"""Prune expired podcast MP3s by episode publish date, dry-run by default.

Run on the media host with EPISODE_DATABASE_URL and MEDIA_STORAGE_ROOT set:
    uv run --package tinboker-podcast python services/podcast/scripts/prune_mp3.py

This command is read-only. --apply is intentionally disabled until deletion
can update every database reference, including wiki frontmatter, with a
retryable cleanup contract. A report also avoids racing active media writes.

Only MP3s referenced by Postgres episode documents are eligible. Files with no
matching document, no valid release date, or a second recent/undated reference
are intentionally left for manual review.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
from shared.db import libpq_url
from src.service.gcs_storage_service import media_root, path_for_media_url, split_media_url


def _referenced_path(episode_id: str, doc: dict) -> Path | None:
    """Accept only the known MP3 layout, bound to this document's show and ID."""
    urls = [doc.get(key) for key in ("mp3_url", "mp3_public_url") if doc.get(key)]
    if not urls or any(not isinstance(url, str) for url in urls):
        return None
    parsed = split_media_url(urls[0])
    if not parsed:
        return None
    _, blob = parsed
    parts = Path(blob).parts
    name = doc.get("podcast_name")
    if (
        not isinstance(name, str)
        or len(parts) < 3
        or parts[-3] != "mp3"
        or parts[-2] != hashlib.sha256(name.encode()).hexdigest()[:12]
        or parts[-1] != f"{episode_id}.mp3"
    ):
        return None
    path = path_for_media_url(urls[0])
    # Refuse symlinked trees and any non-canonical spelling of a path.
    if path != media_root().resolve() / parsed[0] / blob:
        return None
    if any(path_for_media_url(url) != path for url in urls[1:]):
        return None
    return path


def _expired(doc: dict, cutoff_ms: int) -> bool:
    value = doc.get("released_at_ms")
    return type(value) is int and 946684800000 <= value < cutoff_ms


def plan(rows: list[tuple[str, dict]], cutoff_ms: int) -> tuple[list[tuple[Path, list[str], int]], int]:
    """Return existing candidates and the number of missing referenced paths."""
    references: dict[Path, list[tuple[str, dict, bool]]] = defaultdict(list)
    for episode_id, doc in rows:
        for key in ("mp3_url", "mp3_public_url"):
            url = doc.get(key)
            try:
                path = path_for_media_url(url) if isinstance(url, str) else None
            except ValueError:
                continue
            try:
                eligible = path is not None and _referenced_path(episode_id, doc) == path
            except ValueError:
                eligible = False
            if path and not any(id_ == episode_id for id_, _, _ in references[path]):
                references[path].append((episode_id, doc, eligible))

    candidates = []
    missing = 0
    for path, refs in references.items():
        if not path.is_file():
            missing += 1
            continue
        if all(eligible and _expired(doc, cutoff_ms) for _, doc, eligible in refs):
            candidates.append((path, [episode_id for episode_id, _, _ in refs], path.stat().st_size))
    return sorted(candidates, key=lambda row: str(row[0])), missing


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=int(os.getenv("PODCAST_MP3_RETENTION_DAYS", "90")))
    parser.add_argument("--apply", action="store_true", help="reserved; destructive cleanup is not enabled")
    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days must be a positive integer")
    if args.apply:
        parser.error("--apply is disabled until shared references and wiki links can be updated safely")
    if not os.getenv("MEDIA_STORAGE_ROOT"):
        parser.error("MEDIA_STORAGE_ROOT must explicitly point at the mounted media tree")

    from src.secrets_bootstrap import bootstrap

    bootstrap()
    url = os.getenv("EPISODE_DATABASE_URL")
    if not url:
        parser.error("EPISODE_DATABASE_URL is required")
    if not media_root().is_dir():
        parser.error("media root is not mounted")

    cutoff_ms = int((datetime.now(timezone.utc) - timedelta(days=args.days)).timestamp() * 1000)
    with psycopg.connect(libpq_url(url)) as conn:
        with conn.cursor() as cur:
            rows = cur.execute(
                "SELECT episode_id, doc FROM firestore_mirror.episodes "
                "WHERE coalesce(doc->>'mp3_url', '') <> '' "
                "OR coalesce(doc->>'mp3_public_url', '') <> ''"
            ).fetchall()
        candidates, missing = plan(rows, cutoff_ms)
        print(f"DRY RUN: {len(candidates)} files, "
              f"{sum(size for _, _, size in candidates):,} bytes; "
              f"{missing} missing referenced paths; {len(rows)} episode rows scanned")
        for path, ids, size in candidates:
            print(f"candidate: {path} ({size:,} bytes, {len(ids)} episode rows)")


if __name__ == "__main__":
    main()
