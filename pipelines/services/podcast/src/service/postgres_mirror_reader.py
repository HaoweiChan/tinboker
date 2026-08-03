"""Read-only access to the ``firestore_mirror`` Postgres schema (P2 read-flip).

Phase P1 (merged) made ``firestore_mirror.episodes``/``.podcasts`` a live,
dual-written copy of the Firestore documents pipelines reads (see
``docs/firestore-contract.md`` § 11). Phase P2 repoints every pipeline READ
onto this mirror so Phase P4 can stop Firestore writes entirely without
breaking anything here. Firestore WRITES are untouched — this module is
reads only.

Connects with ``EPISODE_DATABASE_URL`` (populated by ``secrets_bootstrap``,
same as the write-side mirror in ``podcast.exporters.postgres_mirror``).
Fails loudly with a clear exception when it's unset — no silent Firestore
fallback, per the P2 design contract.

Each function opens its own short-lived connection, matching the per-call
style already used by the live write-side mirror
(``pipeline.steps.postgres_episode.mirror_episode_to_postgres``) — these
reads run once per episode/request, not in a hot loop, so a connection pool
is unneeded complexity.
"""

from __future__ import annotations

import os
import re
from typing import Any, Optional

from src.podcast.exporters.postgres_mirror import SCHEMA as _SCHEMA

# Same sanitizing FirebaseService.upsert_podcast_show applies before using a
# podcast name as the Firestore ``podcasts/{doc_id}`` document id — the mirror's
# ``podcasts.podcast_name`` primary key is that same sanitized doc id, not the
# raw show name.
_UNSAFE_DOC_ID_CHARS = re.compile(r"[/]")


def _podcast_doc_id(podcast_name: str) -> str:
    return _UNSAFE_DOC_ID_CHARS.sub("_", podcast_name)


def _url() -> str:
    url = os.getenv("EPISODE_DATABASE_URL")
    if not url:
        raise RuntimeError(
            "EPISODE_DATABASE_URL is not set — cannot read firestore_mirror. "
            "This read path was repointed off Firestore in P2; check secrets_bootstrap."
        )
    return url


def _connect():
    import psycopg

    return psycopg.connect(_url(), autocommit=True)


def _row_to_dict(pk: str, doc: dict[str, Any]) -> dict[str, Any]:
    """Same shape Firestore callers got: ``doc.to_dict()`` plus the injected
    document id under ``id`` (see ``FirebaseService``/``FirestoreService``)."""
    data = dict(doc or {})
    data["id"] = pk
    return data


# --- episodes ----------------------------------------------------------------


def get_episode_by_id(episode_id: str) -> Optional[dict[str, Any]]:
    with _connect() as conn, conn.cursor() as cur:
        row = cur.execute(
            f'SELECT episode_id, doc FROM "{_SCHEMA}".episodes WHERE episode_id = %s',
            (episode_id,),
        ).fetchone()
    return _row_to_dict(*row) if row else None


def get_episode_by_fields(
    podcast_name: str, episode_title: str, episode_number: Optional[int] = None
) -> Optional[dict[str, Any]]:
    sql = f'SELECT episode_id, doc FROM "{_SCHEMA}".episodes WHERE podcast_name = %s AND episode_title = %s'
    params: list[Any] = [podcast_name, episode_title]
    if episode_number is not None:
        sql += " AND episode_number = %s"
        params.append(episode_number)
    sql += " LIMIT 1"
    with _connect() as conn, conn.cursor() as cur:
        row = cur.execute(sql, params).fetchone()
    return _row_to_dict(*row) if row else None


def get_episode_by_title_and_number(
    episode_title: str, episode_number: Optional[int] = None
) -> Optional[dict[str, Any]]:
    sql = f'SELECT episode_id, doc FROM "{_SCHEMA}".episodes WHERE episode_title = %s'
    params: list[Any] = [episode_title]
    if episode_number is not None:
        sql += " AND episode_number = %s"
        params.append(episode_number)
    sql += " LIMIT 1"
    with _connect() as conn, conn.cursor() as cur:
        row = cur.execute(sql, params).fetchone()
    return _row_to_dict(*row) if row else None


def episode_exists(
    podcast_name: str, episode_title: str, episode_number: Optional[int] = None
) -> bool:
    return get_episode_by_fields(podcast_name, episode_title, episode_number) is not None


def _order_and_limit_sql(order_by: str, descending: bool, limit: Optional[int]) -> tuple[str, list[Any]]:
    if order_by != "created_time":
        # Every caller (live + scripts) always orders by created_time — the only
        # promoted/indexed column any of them sort on. Fail loud rather than
        # silently ignoring an order_by nothing here supports.
        raise ValueError(f"unsupported order_by={order_by!r} for mirror-backed episode reads")
    sql = f" ORDER BY created_time {'DESC' if descending else 'ASC'}"
    params: list[Any] = []
    if limit:
        sql += " LIMIT %s"
        params.append(limit)
    return sql, params


def get_all_episodes(
    *, order_by: str = "created_time", descending: bool = True, limit: Optional[int] = None
) -> list[dict[str, Any]]:
    tail, tail_params = _order_and_limit_sql(order_by, descending, limit)
    sql = f'SELECT episode_id, doc FROM "{_SCHEMA}".episodes' + tail
    with _connect() as conn, conn.cursor() as cur:
        rows = cur.execute(sql, tail_params).fetchall()
    return [_row_to_dict(eid, doc) for eid, doc in rows]


def get_podcast_episodes(
    podcast_name: str,
    *,
    limit: Optional[int] = None,
    order_by: str = "created_time",
    descending: bool = True,
) -> list[dict[str, Any]]:
    tail, tail_params = _order_and_limit_sql(order_by, descending, limit)
    sql = f'SELECT episode_id, doc FROM "{_SCHEMA}".episodes WHERE podcast_name = %s' + tail
    with _connect() as conn, conn.cursor() as cur:
        rows = cur.execute(sql, [podcast_name, *tail_params]).fetchall()
    return [_row_to_dict(eid, doc) for eid, doc in rows]


def query_episodes(
    *,
    podcast_name: Optional[str] = None,
    order_by: str = "created_time",
    descending: bool = True,
    limit: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Narrow translation of the two query shapes
    ``podcast.regen.orchestrator.find_candidates`` actually issues via
    ``FirestoreService.query_collection`` (an optional ``podcast_name ==``
    filter + order/limit) — not a general Firestore-query-to-SQL translator."""
    if podcast_name is not None:
        return get_podcast_episodes(podcast_name, limit=limit, order_by=order_by, descending=descending)
    return get_all_episodes(order_by=order_by, descending=descending, limit=limit)


def get_existing_episode_titles(podcast_name: str) -> set[str]:
    with _connect() as conn, conn.cursor() as cur:
        rows = cur.execute(
            f'SELECT episode_title FROM "{_SCHEMA}".episodes '
            "WHERE podcast_name = %s AND episode_title IS NOT NULL",
            (podcast_name,),
        ).fetchall()
    return {r[0] for r in rows}


def get_existing_episode_numbers(podcast_name: str) -> set[int]:
    with _connect() as conn, conn.cursor() as cur:
        rows = cur.execute(
            f'SELECT episode_number FROM "{_SCHEMA}".episodes '
            "WHERE podcast_name = %s AND episode_number IS NOT NULL",
            (podcast_name,),
        ).fetchall()
    return {int(r[0]) for r in rows}


def get_all_podcast_names() -> list[str]:
    with _connect() as conn, conn.cursor() as cur:
        rows = cur.execute(
            f'SELECT DISTINCT podcast_name FROM "{_SCHEMA}".episodes '
            "WHERE podcast_name IS NOT NULL ORDER BY podcast_name"
        ).fetchall()
    return [r[0] for r in rows]


def validate_episode_in_tags_and_tickers(
    episode_id: str, tags: list[str], tickers: list[str]
) -> dict[str, Any]:
    """Membership check, redesigned for the mirror.

    The former ``tags/{tag}/episodes`` and ``tickers/{ticker}/episodes``
    Firestore subcollections aren't mirrored (contract § 11.1 — they're pure
    derivations of ``episodes.tags``/``episodes.related_tickers``, which the
    backend already queries directly via GIN index). So "does episode X show
    up under tag Y" becomes "is Y in episode X's own tags array" — the same
    array written in the same call as the rest of the episode doc.
    """
    doc = get_episode_by_id(episode_id) or {}
    doc_tags = {str(t).lower() for t in (doc.get("tags") or [])}
    doc_tickers = {str(t).upper() for t in (doc.get("related_tickers") or [])}

    tags_details = {t.lower(): (t.lower() in doc_tags) for t in tags if t}
    tickers_details = {t.upper(): (t.upper() in doc_tickers) for t in tickers if t}

    return {
        "tags_valid": all(tags_details.values()) if tags_details else True,
        "tickers_valid": all(tickers_details.values()) if tickers_details else True,
        "tags_details": tags_details,
        "tickers_details": tickers_details,
    }


# --- podcasts (show metadata) --------------------------------------------------


def get_podcast_show(podcast_name: str) -> Optional[dict[str, Any]]:
    doc_id = _podcast_doc_id(podcast_name)
    with _connect() as conn, conn.cursor() as cur:
        row = cur.execute(
            f'SELECT podcast_name, doc FROM "{_SCHEMA}".podcasts WHERE podcast_name = %s',
            (doc_id,),
        ).fetchone()
    return _row_to_dict(*row) if row else None


def get_all_podcast_shows() -> list[dict[str, Any]]:
    with _connect() as conn, conn.cursor() as cur:
        rows = cur.execute(f'SELECT podcast_name, doc FROM "{_SCHEMA}".podcasts').fetchall()
    return [_row_to_dict(pid, doc) for pid, doc in rows]
