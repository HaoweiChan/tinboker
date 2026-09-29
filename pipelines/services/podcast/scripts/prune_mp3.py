"""Prune expired podcast MP3s by episode publish date, dry-run by default.

Run on the media host with EPISODE_DATABASE_URL and MEDIA_STORAGE_ROOT set:
    uv run --package tinboker-podcast python services/podcast/scripts/prune_mp3.py

This command is read-only. --apply is intentionally disabled until deletion
can update every database reference, including wiki frontmatter, with a
retryable cleanup contract. --cross-store gives a conservative estimate after
checking the separate content/wiki database; it never changes data or media.

Only MP3s referenced by Postgres episode documents are eligible. Files with no
matching document, no valid release date, or a second recent/undated reference
are intentionally left for manual review.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

import psycopg
from shared.db import libpq_url
from src.service.gcs_storage_service import (
    media_root,
    path_for_media_url,
    public_base,
    split_media_url,
)

PENDING = "mp3_retention_pending"


def _reference_path(url: str) -> Path | None:
    """Resolve URL aliases only when looking for references that block pruning.

    Candidate eligibility remains strict in ``_referenced_path``. Fragments,
    escaped path characters, host case, and an explicit default HTTPS port must
    not hide a second reference to the same file.
    """
    parsed = urlsplit(url.replace("\\", "/"))
    path = unquote(parsed.path).replace("\\", "/")
    if parsed.scheme.lower() == "gs" and parsed.netloc:
        canonical = f"gs://{parsed.netloc}{path}"
    elif (parsed.scheme.lower() in ("http", "https") and
          unquote(parsed.hostname or "").lower().rstrip(".") == "storage.googleapis.com"):
        if parsed.port not in (None, 80, 443):
            return None
        canonical = f"https://storage.googleapis.com{path}"
    elif parsed.scheme.lower() in ("", "http", "https") and parsed.netloc:
        base = urlsplit(public_base())
        if unquote(parsed.hostname or "").lower().rstrip(".") != (base.hostname or "").rstrip("."):
            return None
        if parsed.port not in (None, 80, 443, base.port):
            return None
        if not path.startswith(base.path.rstrip("/") + "/"):
            return None
        canonical = public_base() + path[len(base.path.rstrip("/")):]
    else:
        return None
    return path_for_media_url(canonical)


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
    ambiguous_names: set[str] = set()
    for episode_id, doc in rows:
        for key in ("mp3_url", "mp3_public_url"):
            url = doc.get(key)
            if not isinstance(url, str) or not url:
                continue
            try:
                path = _reference_path(url)
            except ValueError:
                path = None
            if path is None:
                ambiguous_names.add(_legacy_basename(url))
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
        if path.name not in ambiguous_names and all(
            eligible and _expired(doc, cutoff_ms) for _, doc, eligible in refs
        ):
            candidates.append((path, [episode_id for episode_id, _, _ in refs], path.stat().st_size))
    return sorted(candidates, key=lambda row: str(row[0])), missing


def pending_report(rows: list[tuple[str, dict]]) -> list[tuple[Path, int]]:
    """Count staged files separately so a preview includes audio still on disk."""
    paths = set()
    for episode_id, doc in rows:
        marker = doc.get(PENDING)
        if not isinstance(marker, dict) or type(marker.get("staged_at_ms")) is not int:
            continue
        original = {**doc, "mp3_url": marker.get("mp3_url"),
                    "mp3_public_url": marker.get("mp3_public_url")}
        try:
            path = _referenced_path(episode_id, original)
        except ValueError:
            continue
        if path and path.is_file():
            paths.add(path)
    return sorted(((path, path.stat().st_size) for path in paths), key=lambda row: str(row[0]))


def _old_wiki_date(frontmatter: dict, cutoff_ms: int) -> bool:
    """A recent/unknown wiki date is a veto, never proof of episode age."""
    raw = frontmatter.get("date")
    try:
        published = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return False
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    published_ms = int(published.timestamp() * 1000)
    return 946684800000 <= published_ms < cutoff_ms


def _legacy_basename(url: str) -> str:
    """Unmapped legacy URLs with a matching filename block a candidate."""
    cleaned = url.replace("\\", "/")
    try:
        path = urlsplit(cleaned).path
    except ValueError:
        path = cleaned.split("?", 1)[0].split("#", 1)[0]
    return Path(unquote(path)).name


def audit_cross_store(
    candidates: list[tuple[Path, list[str], int]],
    content_rows: list[tuple[str, str, int | None]],
    wiki_rows: list[tuple[int, dict]],
    cutoff_ms: int,
) -> tuple[list[tuple[Path, list[str], int]], dict[str, int]]:
    """Conservative potential batch after checking every known live MP3 store."""
    content_refs: dict[Path, list[tuple[str, int | None]]] = defaultdict(list)
    wiki_refs: dict[Path, list[dict]] = defaultdict(list)
    ambiguous_names: set[str] = set()
    for episode_id, url, released_at_ms in content_rows:
        try:
            path = _reference_path(url)
        except ValueError:
            path = None
        if path:
            content_refs[path].append((episode_id, released_at_ms))
        else:
            ambiguous_names.add(_legacy_basename(url))
    for _, frontmatter in wiki_rows:
        url = (frontmatter.get("source_urls") or {}).get("mp3")
        if not isinstance(url, str):
            continue
        try:
            path = _reference_path(url)
        except ValueError:
            path = None
        if path:
            wiki_refs[path].append(frontmatter)
        else:
            ambiguous_names.add(_legacy_basename(url))

    eligible = []
    blocked = defaultdict(int)
    for path, ids, size in candidates:
        if path.name in ambiguous_names:
            blocked["ambiguous_legacy_url"] += 1
        elif any(eid not in ids or not _expired({"released_at_ms": age}, cutoff_ms)
                 for eid, age in content_refs[path]):
            blocked["shared_or_dated_content"] += 1
        elif any(not _old_wiki_date(frontmatter, cutoff_ms) for frontmatter in wiki_refs[path]):
            blocked["recent_or_undated_wiki"] += 1
        else:
            eligible.append((path, ids, size))
    return eligible, dict(blocked)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=int(os.getenv("PODCAST_MP3_RETENTION_DAYS", "90")))
    parser.add_argument("--apply", action="store_true", help="reserved; destructive cleanup is not enabled")
    parser.add_argument("--cross-store", action="store_true", help="audit content and wiki references")
    parser.add_argument("--batch-size", type=int, default=25, help="maximum preview paths to print")
    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days must be a positive integer")
    if args.apply:
        parser.error("--apply is disabled until shared references and wiki links can be updated safely")
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")
    if not os.getenv("MEDIA_STORAGE_ROOT"):
        parser.error("MEDIA_STORAGE_ROOT must explicitly point at the mounted media tree")

    from src.secrets_bootstrap import bootstrap

    bootstrap()
    url = os.getenv("EPISODE_DATABASE_URL")
    if not url:
        parser.error("EPISODE_DATABASE_URL is required")
    wiki_url = os.getenv("WIKI_DATABASE_URL")
    if args.cross_store and not wiki_url:
        parser.error("WIKI_DATABASE_URL is required for --cross-store")
    if not media_root().is_dir():
        parser.error("media root is not mounted")

    cutoff_ms = int((datetime.now(timezone.utc) - timedelta(days=args.days)).timestamp() * 1000)
    try:
        with psycopg.connect(libpq_url(url)) as conn:
            with conn.cursor() as cur:
                rows = cur.execute(
                    "SELECT episode_id, doc FROM firestore_mirror.episodes "
                    "WHERE coalesce(doc->>'mp3_url', '') <> '' "
                    "OR coalesce(doc->>'mp3_public_url', '') <> '' "
                    f"OR doc ? '{PENDING}'"
                ).fetchall()
            candidates, missing = plan(rows, cutoff_ms)
            pending = pending_report(rows)
            print(f"DRY RUN: {len(candidates)} files, "
                  f"{sum(size for _, _, size in candidates):,} bytes; "
                  f"{len(pending)} staged files, {sum(size for _, size in pending):,} staged bytes; "
                  f"{missing} missing referenced paths; {len(rows)} episode rows scanned")
            if args.cross_store:
                with psycopg.connect(libpq_url(wiki_url)) as wiki:
                    content_rows = wiki.execute(
                        "SELECT id, mp3_url, released_at_ms FROM public.episodes "
                        "WHERE coalesce(mp3_url, '') <> ''"
                    ).fetchall()
                    wiki_rows = wiki.execute(
                        "SELECT id, frontmatter FROM public.wiki_pages "
                        "WHERE coalesce(frontmatter #>> '{source_urls,mp3}', '') <> ''"
                    ).fetchall()
                candidates, blocked = audit_cross_store(
                    candidates, content_rows, wiki_rows, cutoff_ms
                )
                print(f"CROSS-STORE DRY RUN: {len(candidates)} potential files, "
                      f"{sum(size for _, _, size in candidates):,} potential bytes; "
                      f"blocked={blocked}; previewing first {args.batch_size}")
                candidates = candidates[:args.batch_size]
            for path, ids, size in candidates:
                print(f"candidate: {path} ({size:,} bytes, {len(ids)} episode rows)")
    except Exception:
        # Connection and query errors can contain a credential-bearing DSN.
        print("MP3 retention preview failed; inspect database and media availability", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
