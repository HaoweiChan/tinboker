"""Retryable MP3 retirement across the mirror and wiki PostgreSQL databases.

Both databases must have the mp3_retention_guards migration installed before
this module changes anything. Table locks order ordinary writers against the
first tombstone in each database. A partial cross-database commit is safe to
retry: mirror episode markers retain the original URLs, and files remain until
both databases are clear for at least four hours.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import psycopg
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb
from scripts.mp3_retention_guards import _public_origin
from scripts.prune_mp3 import (
    PENDING,
    _expired,
    _legacy_basename,
    _old_wiki_date,
    _reference_path,
    _referenced_path,
    audit_cross_store,
    plan,
)
from src.service.gcs_storage_service import media_root, public_base
from src.service.mp3_retention_lock import mp3_media_lock, retired_marker_path

GRACE_MS = 4 * 60 * 60 * 1000


def _autocommit_ready(*connections: psycopg.Connection) -> None:
    if any(not conn.autocommit or conn.info.transaction_status != TransactionStatus.IDLE
           for conn in connections):
        raise RuntimeError("MP3 retirement requires idle autocommit connections")


def _key(path: Path) -> str:
    root = media_root().resolve()
    if path != path.resolve() or not path.is_relative_to(root):
        raise ValueError("MP3 path is outside the mounted media tree")
    parts = path.relative_to(root).parts
    if len(parts) < 4 or parts[-3] != "mp3" or path.suffix != ".mp3":
        raise ValueError("MP3 path does not have the expected layout")
    return path.relative_to(root).as_posix()


def _regular_file(path: Path) -> bool:
    root = media_root().resolve()
    if not path.is_relative_to(root):
        return False
    try:
        if not stat.S_ISREG(path.lstat().st_mode):
            return False
        for parent in path.parents:
            if parent == root:
                break
            if parent.is_symlink():
                return False
        return True
    except FileNotFoundError:
        return False


def _ready(conn: psycopg.Connection, tables: tuple[str, ...]) -> None:
    """Fail before mutation unless every installed table guard is active."""
    if conn.execute("SELECT to_regclass('mp3_retention.tombstones')").fetchone()[0] is None:
        raise RuntimeError("MP3 tombstone migration is not installed")
    origin = conn.execute(
        "SELECT public_scheme, public_authority, public_path "
        "FROM mp3_retention.config WHERE id = 1"
    ).fetchone()
    if origin is None or tuple(origin) != _public_origin():
        raise RuntimeError("MP3 retention media origin differs from installed guard")
    for table in tables:
        ok = conn.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_trigger WHERE tgrelid = %s::regclass "
            "AND tgname = 'guard_mp3_reference' AND tgenabled = 'O')",
            (table,),
        ).fetchone()[0]
        if not ok:
            raise RuntimeError("MP3 reference guard is not active")


def _lock_tables(mirror: psycopg.Connection, wiki: psycopg.Connection) -> None:
    mirror.execute("LOCK TABLE firestore_mirror.episodes IN SHARE ROW EXCLUSIVE MODE")
    wiki.execute("LOCK TABLE public.episodes, public.wiki_pages IN SHARE ROW EXCLUSIVE MODE")
    _ready(mirror, ("firestore_mirror.episodes",))
    _ready(wiki, ("public.episodes", "public.wiki_pages"))


def _verify_key(conn: psycopg.Connection, key: str) -> None:
    normalized = conn.execute(
        "SELECT mp3_retention.media_key(%s)", (f"{public_base()}/{key}",)
    ).fetchone()[0]
    if normalized != key:
        raise RuntimeError("MP3 path and installed guard disagree")


def _rows(mirror: psycopg.Connection, wiki: psycopg.Connection):
    episodes = mirror.execute(
        "SELECT episode_id, doc FROM firestore_mirror.episodes WHERE "
        "coalesce(doc->>'mp3_url', '') <> '' OR "
        "coalesce(doc->>'mp3_public_url', '') <> '' OR doc ? %s",
        (PENDING,),
    ).fetchall()
    content = wiki.execute(
        "SELECT id, mp3_url, released_at_ms FROM public.episodes "
        "WHERE coalesce(mp3_url, '') <> ''"
    ).fetchall()
    pages = wiki.execute(
        "SELECT id, frontmatter FROM public.wiki_pages "
        "WHERE coalesce(frontmatter #>> '{source_urls,mp3}', '') <> ''"
    ).fetchall()
    return episodes, content, pages


def _marker_rows(rows: list[tuple[str, dict]], key: str) -> list[tuple[str, dict]]:
    return [(episode_id, doc) for episode_id, doc in rows
            if isinstance(doc.get(PENDING), dict) and doc[PENDING].get("media_key") == key]


def _restored_rows(rows: list[tuple[str, dict]]) -> list[tuple[str, dict]]:
    restored = []
    for episode_id, doc in rows:
        marker = doc.get(PENDING)
        if isinstance(marker, dict) and not (doc.get("mp3_url") or doc.get("mp3_public_url")):
            doc = {**doc, "mp3_url": marker.get("mp3_url"),
                   "mp3_public_url": marker.get("mp3_public_url")}
        restored.append((episode_id, doc))
    return restored


def _eligible(path: Path, rows, content, pages, cutoff_ms: int) -> list[str] | None:
    candidates, _ = plan(_restored_rows(rows), cutoff_ms)
    matching = [(p, ids, size) for p, ids, size in candidates if p == path]
    if not matching:
        return None
    clear, _ = audit_cross_store(matching, content, pages, cutoff_ms)
    return clear[0][1] if clear else None


def _matching_references(path: Path, rows, content, pages) -> bool:
    """Finalization requires zero active references, including legacy aliases."""
    for _, doc in rows:
        for field in ("mp3_url", "mp3_public_url"):
            url = doc.get(field)
            if isinstance(url, str) and url and _may_reference(path, url):
                return True
    for _, url, _ in content:
        if isinstance(url, str) and _may_reference(path, url):
            return True
    for _, frontmatter in pages:
        urls = frontmatter.get("source_urls") or {}
        url = urls.get("mp3") if isinstance(urls, dict) else None
        if isinstance(url, str) and _may_reference(path, url):
            return True
    return False


def _may_reference(path: Path, url: str) -> bool:
    try:
        resolved = _reference_path(url)
    except ValueError:
        resolved = None
    return resolved == path or (resolved is None and _legacy_basename(url) == path.name)


def _now_ms(conn: psycopg.Connection) -> int:
    return conn.execute(
        "SELECT (extract(epoch from clock_timestamp()) * 1000)::bigint"
    ).fetchone()[0]


def _unlink_mp3(path: Path) -> None:
    path.unlink(missing_ok=True)
    parent_fd = os.open(path.parent, os.O_DIRECTORY)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def stage(path: Path, cutoff_ms: int, mirror: psycopg.Connection,
          wiki: psycopg.Connection, *, after_mirror_commit=None) -> bool:
    """Install both tombstones and clear URLs; return whether a path was staged."""
    _autocommit_ready(mirror, wiki)
    key = _key(path)
    with mp3_media_lock(media_root()):
        # The wiki transaction is outermost: mirror commits first. If the
        # process dies before wiki commit, its durable marker drives retry.
        with wiki.transaction():
            with mirror.transaction():
                _lock_tables(mirror, wiki)
                _verify_key(mirror, key)
                _verify_key(wiki, key)
                rows, content, pages = _rows(mirror, wiki)
                marked = _marker_rows(rows, key)
                if marked and all(type(doc[PENDING].get("ready_at_ms")) is int
                                  for _, doc in marked) and not _matching_references(
                                      path, rows, content, pages
                                  ):
                    return False
                ids = _eligible(path, rows, content, pages, cutoff_ms)
                if not ids or not _regular_file(path):
                    return False
                if retired_marker_path(media_root(), key).exists():
                    return False
                mirror.execute(
                    "INSERT INTO mp3_retention.tombstones (media_key) VALUES (%s) "
                    "ON CONFLICT DO NOTHING", (key,)
                )
                wiki.execute(
                    "INSERT INTO mp3_retention.tombstones (media_key) VALUES (%s) "
                    "ON CONFLICT DO NOTHING", (key,)
                )
                content_ids = [episode_id for episode_id, url, _ in content
                               if _may_reference(path, url)]
                page_ids = [page_id for page_id, frontmatter in pages
                            if isinstance(frontmatter.get("source_urls"), dict) and
                            isinstance(frontmatter["source_urls"].get("mp3"), str) and
                            _may_reference(path, frontmatter["source_urls"]["mp3"])]
                for episode_id, doc in rows:
                    if episode_id not in ids:
                        continue
                    old_marker = doc.get(PENDING) or {}
                    if not old_marker and _referenced_path(episode_id, doc) != path:
                        raise RuntimeError("MP3 reference changed during retirement")
                    marker = {
                        "media_key": key,
                        "mp3_url": old_marker.get("mp3_url", doc.get("mp3_url")),
                        "mp3_public_url": old_marker.get("mp3_public_url", doc.get("mp3_public_url")),
                        "staged_at_ms": old_marker.get("staged_at_ms", _now_ms(mirror)),
                        "content_ids": sorted(set(old_marker.get("content_ids", [])) | set(content_ids)),
                        "wiki_ids": sorted(set(old_marker.get("wiki_ids", [])) | set(page_ids)),
                    }
                    mirror.execute(
                        "UPDATE firestore_mirror.episodes SET doc = doc || %s "
                        "WHERE episode_id = %s",
                        (Jsonb({"mp3_url": "", "mp3_public_url": "", PENDING: marker}),
                         episode_id),
                    )
                for episode_id, url, _ in content:
                    if _may_reference(path, url):
                        wiki.execute("UPDATE public.episodes SET mp3_url = NULL WHERE id = %s",
                                     (episode_id,))
                for page_id, frontmatter in pages:
                    urls = frontmatter.get("source_urls") or {}
                    url = urls.get("mp3") if isinstance(urls, dict) else None
                    if isinstance(url, str) and _may_reference(path, url):
                        wiki.execute(
                            "UPDATE public.wiki_pages SET frontmatter = jsonb_set(" 
                            "frontmatter, '{source_urls}', (frontmatter->'source_urls') - 'mp3') "
                            "WHERE id = %s", (page_id,),
                        )
            if after_mirror_commit is not None:
                after_mirror_commit()
        # This clock is read only after both databases have committed. A crash
        # here leaves no ready time, so retry starts a fresh four-hour grace.
        with mirror.transaction():
            mirror.execute(
                "UPDATE firestore_mirror.episodes SET doc = jsonb_set(" 
                "doc, %s, to_jsonb(%s::bigint)) WHERE doc->%s->>'media_key' = %s",
                ([PENDING, "ready_at_ms"], _now_ms(mirror), PENDING, key),
            )
    return True


def finalize(path: Path, cutoff_ms: int, mirror: psycopg.Connection,
             wiki: psycopg.Connection, *, grace_ms: int = GRACE_MS) -> bool:
    """After grace, recheck every store under the writer lock and unlink once."""
    _autocommit_ready(mirror, wiki)
    key = _key(path)
    with mp3_media_lock(media_root()):
        with wiki.transaction(), mirror.transaction():
            _lock_tables(mirror, wiki)
            _verify_key(mirror, key)
            _verify_key(wiki, key)
            rows, content, pages = _rows(mirror, wiki)
            marked = _marker_rows(rows, key)
            if not marked:
                return False
            for episode_id, doc in marked:
                original = {**doc, "mp3_url": doc[PENDING].get("mp3_url"),
                            "mp3_public_url": doc[PENDING].get("mp3_public_url")}
                try:
                    if _referenced_path(episode_id, original) != path:
                        return False
                except ValueError:
                    return False
            if not all(_expired(doc, cutoff_ms) and
                       type(doc[PENDING].get("ready_at_ms")) is int and
                       _now_ms(mirror) - doc[PENDING]["ready_at_ms"] >= grace_ms
                       for _, doc in marked):
                return False
            content_ids = sorted({item for _, doc in marked
                                  for item in doc[PENDING].get("content_ids", [])})
            page_ids = sorted({item for _, doc in marked
                               for item in doc[PENDING].get("wiki_ids", [])})
            if content_ids:
                ages = wiki.execute(
                    "SELECT released_at_ms FROM public.episodes WHERE id = ANY(%s)",
                    (content_ids,),
                ).fetchall()
                if any(not _expired({"released_at_ms": age}, cutoff_ms) for (age,) in ages):
                    return False
            if page_ids:
                dates = wiki.execute(
                    "SELECT frontmatter FROM public.wiki_pages WHERE id = ANY(%s)",
                    (page_ids,),
                ).fetchall()
                if any(not _old_wiki_date(frontmatter, cutoff_ms) for (frontmatter,) in dates):
                    return False
            if any(_may_reference(path, url) for _, doc in marked
                   for url in (doc.get("mp3_url"), doc.get("mp3_public_url"))
                   if isinstance(url, str) and url):
                return False
            if _matching_references(path, rows, content, pages):
                return False
            for conn in (mirror, wiki):
                if not conn.execute(
                    "SELECT 1 FROM mp3_retention.tombstones WHERE media_key = %s",
                    (key,),
                ).fetchone():
                    return False
            if path.exists() and not _regular_file(path):
                return False
            # A durable filesystem marker closes the upload gap even for a
            # future local writer accidentally missing its DB URL.
            marker = retired_marker_path(media_root(), key)
            marker.parent.mkdir(parents=True, exist_ok=True)
            root_fd = os.open(media_root(), os.O_DIRECTORY)
            try:
                os.fsync(root_fd)
            finally:
                os.close(root_fd)
            if not marker.exists():
                with marker.open("xb") as f:
                    f.flush()
                    os.fsync(f.fileno())
            dir_fd = os.open(marker.parent, os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
            _unlink_mp3(path)
            mirror.execute(
                "UPDATE firestore_mirror.episodes SET doc = doc - %s "
                "WHERE doc->%s->>'media_key' = %s", (PENDING, PENDING, key),
            )
    return True


def apply_batch(mirror: psycopg.Connection, wiki: psycopg.Connection,
                cutoff_ms: int, batch_size: int) -> tuple[int, int, int, int]:
    """Finalize ready paths first, then stage up to the remaining batch size."""
    _autocommit_ready(mirror, wiki)
    for conn in (mirror, wiki):
        conn.execute("SET lock_timeout = '5s'")
        conn.execute("SET statement_timeout = '120s'")
    _ready(mirror, ("firestore_mirror.episodes",))
    _ready(wiki, ("public.episodes", "public.wiki_pages"))
    rows, content, pages = _rows(mirror, wiki)
    pending_paths: set[Path] = set()
    for episode_id, doc in rows:
        marker = doc.get(PENDING)
        if not isinstance(marker, dict):
            continue
        original = {**doc, "mp3_url": marker.get("mp3_url"),
                    "mp3_public_url": marker.get("mp3_public_url")}
        try:
            path = _referenced_path(episode_id, original)
        except ValueError:
            continue
        if path and marker.get("media_key") == _key(path):
            pending_paths.add(path)
    finished = staged = unresolved = 0
    for path in sorted(pending_paths):
        if finished + staged >= batch_size:
            break
        if finalize(path, cutoff_ms, mirror, wiki):
            finished += 1
        elif stage(path, cutoff_ms, mirror, wiki):
            staged += 1
        else:
            unresolved += 1
    if finished + staged < batch_size:
        candidates, _ = plan(rows, cutoff_ms)
        candidates, _ = audit_cross_store(candidates, content, pages, cutoff_ms)
        for path, _, _ in candidates:
            if finished + staged >= batch_size:
                break
            if path not in pending_paths and stage(path, cutoff_ms, mirror, wiki):
                staged += 1
    pending_rows = mirror.execute(
        "SELECT count(*) FROM firestore_mirror.episodes WHERE doc ? %s", (PENDING,)
    ).fetchone()[0]
    return staged, finished, pending_rows, unresolved
