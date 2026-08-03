"""Postgres-backed drop-in for the content reads FirestoreService serves today.

The content pipeline mirrors every Firestore episode document verbatim into
VPS-local Postgres (`podcast_db`, schema ``firestore_mirror``): a few promoted
columns plus ``doc JSONB`` holding the whole Firestore document. The backend
already connects to that same database, so reading content from the mirror costs
nothing in GCP egress — which is the whole point (July 2026 Firestore bill).

This class exposes the SAME method names/signatures as
``FirestoreService`` for the subset of collections used by content reads, so it
can be swapped in at the construction seam without touching any call site
(``settings.content_reads_from_postgres``).

Mapped surface:
  episodes/{id}                         -> firestore_mirror.episodes
  tickers/{T}/episodes, tags/{S}/episodes -> derived from episodes.doc arrays
                                             (docs/firestore-contract.md § 3.2)
  ticker_insights/{ep}/tickers/{T}      -> firestore_mirror.ticker_insights
  trending_tickers/{T}                  -> firestore_mirror.trending_tickers

Anything not mapped raises NotImplementedError — there is deliberately NO silent
fallback to Firestore, so an unmapped read fails loudly instead of quietly
re-billing GCP. users/* and notifications stay on the real FirestoreService.
"""
from __future__ import annotations

import json
import logging
import re
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from src.config import settings
from src.database.postgres import get_session

logger = logging.getLogger(__name__)

SCHEMA = "firestore_mirror"
EPISODES = f"{SCHEMA}.episodes"
TICKER_INSIGHTS = f"{SCHEMA}.ticker_insights"
TRENDING_TICKERS = f"{SCHEMA}.trending_tickers"

# Firestore inverted index -> the episodes array it is derived from
# (docs/firestore-contract.md § 3.2: the index is exactly this array, fanned out).
INDEX_ARRAY_FIELD = {"tickers": "related_tickers", "tags": "tags"}

# Promoted (indexed) columns on firestore_mirror.episodes — preferred over doc->>
_EPISODE_COLUMNS = {
    "podcast_name": "podcast_name",
    "episode_number": "episode_number",
    "episode_title": "episode_title",
    "created_time": "created_time",
    "num_likes": "num_likes",
    "number_click": "number_click",
}

_FIELD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Firestore's DELETE_FIELD sentinel — write-through turns it into a JSONB key removal.
try:  # pragma: no cover - import shape depends on the firestore extra being installed
    from google.cloud.firestore import DELETE_FIELD as _DELETE_FIELD
except Exception:  # pragma: no cover
    _DELETE_FIELD = object()

# Normalized tag slug, in SQL. Mirrors src.tag_registry.normalize_tag_slug.
# ponytail: the 6-entry alias map in normalize_tag_slug (datacenters->datacenter etc.)
# is NOT applied here — an aliased spelling on an episode won't match the alias target.
# Upgrade path: export that dict from tag_registry and expand the parent id into all
# of its raw spellings before binding.
_TAG_SLUG_SQL = "regexp_replace(lower(t), '[^a-z0-9]', '', 'g')"


def _field(name: str) -> str:
    """Validate an identifier before it is interpolated into SQL."""
    if not _FIELD_RE.match(name or ""):
        raise NotImplementedError(
            f"Postgres mirror: unsupported field name {name!r}"
        )
    return name


def _pg_text_array(values: List[Any]) -> str:
    """Postgres ``text[]`` literal, bound as a plain string + CAST (driver-agnostic)."""
    return "{" + ",".join(json.dumps(str(v)) for v in values) + "}"


@contextmanager
def mirror_session() -> Iterator[Session]:
    """Backend's own SQLAlchemy session — the mirror lives in the same database."""
    db = next(get_session())
    try:
        yield db
    finally:
        db.close()


def _with_id(doc: Optional[dict], doc_id: str, **extra: Any) -> Dict[str, Any]:
    """FirestoreService injects the doc id as ``id``; keep that contract."""
    out = dict(doc or {})
    out["id"] = doc_id
    out.update(extra)
    return out


def patch_episode_doc(episode_id: str, updates: Dict[str, Any]) -> bool:
    """Apply a Firestore merge-patch to the mirrored episode doc.

    Runs write-through on every platform episode write REGARDLESS of the read
    flag, so the mirror is already fresh when reads are flipped over.
    ``DELETE_FIELD`` values become JSONB key removals. Returns False when there
    is no mirror to write to (SQLite dev) — callers treat failure as non-fatal.
    """
    if not settings.use_postgres:
        return False  # mirror only exists in podcast_db Postgres
    drop = [k for k, v in updates.items() if v is _DELETE_FIELD]
    patch = {k: v for k, v in updates.items() if v is not _DELETE_FIELD}
    sql = text(
        f"UPDATE {EPISODES} SET "
        "doc = (doc - CAST(:drop AS text[])) || CAST(:patch AS jsonb), "
        # related_tickers is promoted; patch_episode_fields can change it.
        "related_tickers = COALESCE(CAST(:patch AS jsonb) -> 'related_tickers', related_tickers) "
        "WHERE episode_id = :id"
    )
    params = {
        "drop": _pg_text_array(drop),
        "patch": json.dumps(patch, default=str),
        "id": episode_id,
    }
    with mirror_session() as db:
        db.execute(sql, params)
        db.commit()
    return True


class PostgresMirrorService:
    """Content reads served from ``firestore_mirror`` instead of Firestore."""

    # ── episodes ─────────────────────────────────────────────────────

    def get_document(self, collection: str, doc_id: str) -> Optional[Dict]:
        if collection != "episodes":
            raise NotImplementedError(
                f"Postgres mirror: get_document('{collection}') is not mirrored"
            )
        sql = text(f"SELECT doc FROM {EPISODES} WHERE episode_id = :id")
        with mirror_session() as db:
            row = db.execute(sql, {"id": doc_id}).first()
        return _with_id(row[0], doc_id) if row else None

    def get_documents_batch(self, collection: str, doc_ids: List[str]) -> List[Dict]:
        if collection != "episodes":
            raise NotImplementedError(
                f"Postgres mirror: get_documents_batch('{collection}') is not mirrored"
            )
        if not doc_ids:
            return []
        sql = text(
            f"SELECT episode_id, doc FROM {EPISODES} "
            "WHERE episode_id = ANY(CAST(:ids AS text[]))"
        )
        with mirror_session() as db:
            rows = db.execute(sql, {"ids": _pg_text_array(doc_ids)}).fetchall()
        found = {r[0]: _with_id(r[1], r[0]) for r in rows}
        # Preserve the caller's id order (ticker/tag pages page straight off it).
        return [found[i] for i in doc_ids if i in found]

    def query_collection(
        self,
        collection: str,
        filters: Optional[List[tuple]] = None,
        order_by: Optional[str] = None,
        direction: Optional[str] = "DESCENDING",
        limit: Optional[int] = None,
    ) -> List[Dict]:
        if collection != "episodes":
            raise NotImplementedError(
                f"Postgres mirror: query_collection('{collection}') is not mirrored"
            )
        where, params = self._episode_where(filters)
        sql = f"SELECT episode_id, doc FROM {EPISODES}{where}"
        sql += self._order_clause(order_by, direction)
        if limit:
            sql += " LIMIT :limit"
            params["limit"] = int(limit)
        with mirror_session() as db:
            rows = db.execute(text(sql), params).fetchall()
        return [_with_id(r[1], r[0]) for r in rows]

    def get_all_documents(self, collection: str) -> List[Dict]:
        if collection == "episodes":
            return self.query_collection("episodes")
        if collection == "trending_tickers":
            sql = text(f"SELECT ticker, doc FROM {TRENDING_TICKERS}")
            with mirror_session() as db:
                rows = db.execute(sql).fetchall()
            return [_with_id(r[1], r[0]) for r in rows]
        raise NotImplementedError(
            f"Postgres mirror: get_all_documents('{collection}') is not mirrored"
        )

    def stream_documents_projected(self, collection: str, fields: List[str]) -> List[Dict]:
        """Full-collection scan returning only ``fields`` from each doc."""
        if collection != "episodes":
            raise NotImplementedError(
                f"Postgres mirror: stream_documents_projected('{collection}') is not mirrored"
            )
        for f in fields:
            _field(f)
        sql = text(
            "SELECT e.episode_id, COALESCE("
            "(SELECT jsonb_object_agg(k, e.doc -> k) "
            "FROM unnest(CAST(:fields AS text[])) AS k "
            "WHERE jsonb_exists(e.doc, k)), '{}'::jsonb) "
            f"FROM {EPISODES} e"
        )
        with mirror_session() as db:
            rows = db.execute(sql, {"fields": _pg_text_array(fields)}).fetchall()
        return [_with_id(r[1], r[0]) for r in rows]

    # ── tags/{slug}/episodes and tickers/{T}/episodes (derived indices) ──

    def get_subcollection_documents(
        self,
        collection: str,
        parent_doc_id: str,
        subcollection: str,
        order_by: Optional[str] = None,
        direction: Optional[str] = "DESCENDING",
        limit: Optional[int] = None,
    ) -> List[Dict]:
        pred = self._index_predicate(collection, subcollection)
        if order_by not in (None, "created_time"):
            raise NotImplementedError(
                f"Postgres mirror: index order_by={order_by!r} is not supported"
            )
        sql = (
            "SELECT episode_id, (EXTRACT(EPOCH FROM created_time) * 1000)::bigint "
            f"FROM {EPISODES} WHERE {pred}"
        )
        params: Dict[str, Any] = {"parent": parent_doc_id}
        if order_by:
            asc = "ASC" if direction == "ASCENDING" else "DESC"
            sql += f" ORDER BY created_time {asc} NULLS LAST"
        if limit:
            sql += " LIMIT :limit"
            params["limit"] = int(limit)
        with mirror_session() as db:
            rows = db.execute(text(sql), params).fetchall()
        return [{"episode_id": r[0], "created_time": r[1]} for r in rows]

    def count_subcollection_documents(
        self, collection: str, parent_doc_id: str, subcollection: str
    ) -> int:
        pred = self._index_predicate(collection, subcollection)
        sql = text(f"SELECT count(*) FROM {EPISODES} WHERE {pred}")
        with mirror_session() as db:
            return int(db.execute(sql, {"parent": parent_doc_id}).scalar() or 0)

    def get_all_parent_documents(self, collection: str) -> List[str]:
        """Every tag slug (resp. ticker) any mirrored episode references."""
        if collection not in INDEX_ARRAY_FIELD:
            raise NotImplementedError(
                f"Postgres mirror: get_all_parent_documents('{collection}') is not mirrored"
            )
        arr = INDEX_ARRAY_FIELD[collection]
        value = _TAG_SLUG_SQL if collection == "tags" else "upper(t)"
        sql = text(
            f"SELECT DISTINCT {value} FROM {EPISODES}, "
            f"jsonb_array_elements_text(doc -> '{arr}') AS t"
        )
        with mirror_session() as db:
            return [r[0] for r in db.execute(sql).fetchall() if r[0]]

    # ── ticker_insights collection group ──────────────────────────────

    def query_collection_group(
        self,
        collection_id: str,
        filters: Optional[List[tuple]] = None,
        order_by: Optional[str] = None,
        direction: Optional[str] = "DESCENDING",
        limit: Optional[int] = None,
    ) -> List[Dict]:
        if collection_id != "tickers":
            raise NotImplementedError(
                f"Postgres mirror: query_collection_group('{collection_id}') is not mirrored"
            )
        where: List[str] = []
        params: Dict[str, Any] = {}
        for i, (field, op, value) in enumerate(filters or []):
            key = f"f{i}"
            col = "ticker" if _field(field) == "ticker" else f"doc->>'{field}'"
            if op == "==":
                where.append(f"{col} = :{key}")
                params[key] = str(value)
            elif op == "in":
                where.append(f"{col} = ANY(CAST(:{key} AS text[]))")
                params[key] = _pg_text_array(list(value or []))
            else:
                raise NotImplementedError(
                    f"Postgres mirror: ticker_insights filter operator {op!r} is not supported"
                )
        sql = f"SELECT episode_id, ticker, doc FROM {TICKER_INSIGHTS}"
        if where:
            sql += " WHERE " + " AND ".join(where)
        if order_by:
            asc = "ASC" if direction == "ASCENDING" else "DESC"
            sql += f" ORDER BY doc->>'{_field(order_by)}' {asc} NULLS LAST"
        if limit:
            sql += " LIMIT :limit"
            params["limit"] = int(limit)
        with mirror_session() as db:
            rows = db.execute(text(sql), params).fetchall()
        return [_with_id(r[2], r[1], _parent_id=r[0]) for r in rows]

    # ── writes: never served from the mirror ─────────────────────────

    def set_document(self, collection: str, doc_id: str, data: Dict, merge: bool = False) -> bool:
        raise NotImplementedError(
            "Postgres mirror is read-only — writes must go to FirestoreService "
            "(PodcastService._fs_write) with patch_episode_doc() write-through"
        )

    def delete_document(self, collection: str, doc_id: str) -> bool:
        raise NotImplementedError("Postgres mirror is read-only")

    def count_collection(self, collection: str) -> int:
        raise NotImplementedError(
            f"Postgres mirror: count_collection('{collection}') is not mirrored"
        )

    # ── SQL builders ─────────────────────────────────────────────────

    def _index_predicate(self, collection: str, subcollection: str) -> str:
        """WHERE fragment for `<collection>/{parent}/episodes` membership."""
        if subcollection != "episodes" or collection not in INDEX_ARRAY_FIELD:
            raise NotImplementedError(
                f"Postgres mirror: '{collection}/*/{subcollection}' is not mirrored"
            )
        if collection == "tags":
            # Episode tags are stored in their raw spelling; the Firestore parent id is
            # the normalized slug — normalize both sides.
            return (
                "EXISTS (SELECT 1 FROM jsonb_array_elements_text(doc -> 'tags') AS t "
                f"WHERE {_TAG_SLUG_SQL} = :parent)"
            )
        return "jsonb_exists(doc -> 'related_tickers', :parent)"

    def _episode_where(
        self, filters: Optional[List[tuple]]
    ) -> Tuple[str, Dict[str, Any]]:
        where: List[str] = []
        params: Dict[str, Any] = {}
        for i, (field, op, value) in enumerate(filters or []):
            key = f"f{i}"
            name = _field(field)
            col = _EPISODE_COLUMNS.get(name, f"doc->>'{name}'")
            if op == "==":
                where.append(f"{col} = :{key}")
                params[key] = str(value)
            elif op == "in":
                where.append(f"{col} = ANY(CAST(:{key} AS text[]))")
                params[key] = _pg_text_array(list(value or []))
            elif op == "array-contains":
                where.append(f"jsonb_exists(doc -> '{name}', :{key})")
                params[key] = str(value)
            else:
                raise NotImplementedError(
                    f"Postgres mirror: episode filter operator {op!r} is not supported"
                )
        return (" WHERE " + " AND ".join(where)) if where else "", params

    def _order_clause(self, order_by: Optional[str], direction: Optional[str]) -> str:
        if not order_by:
            return ""
        name = _field(order_by)
        col = _EPISODE_COLUMNS.get(name, f"doc->>'{name}'")
        asc = "ASC" if direction == "ASCENDING" else "DESC"
        return f" ORDER BY {col} {asc} NULLS LAST"


def content_read_service():
    """The service content reads go through.

    Postgres mirror when ``CONTENT_READS_FROM_POSTGRES`` is on, Firestore
    otherwise. users/* and notifications never come through here.
    """
    if settings.content_reads_from_postgres:
        return PostgresMirrorService()
    from src.services.firestore_service import FirestoreService

    return FirestoreService()
