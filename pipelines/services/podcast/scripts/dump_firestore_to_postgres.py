#!/usr/bin/env python3
"""One-shot mirror: Firestore ``graphfolio-db`` → Postgres (schema ``firestore_mirror``).

Why: the podcast catalog (episodes / podcasts / tags / tickers / users) lives in Firestore today.
This copies it verbatim into Postgres on the VPS so the data is consolidated alongside the wiki
store, *without* touching Firestore (the live webui still reads it) — see
``docs/data-consolidation-plan.md`` (Phase 1). Re-runnable: every table is upserted ``ON CONFLICT``.

Each collection becomes one table: a few promoted/indexed columns + a ``doc`` JSONB holding the
whole document (so nothing is lost, incl. all the ``*_url`` fields on episodes).

Usage::

    # connection string (psycopg / libpq form):
    uv run python services/podcast/scripts/dump_firestore_to_postgres.py \
        --database-url 'postgresql://podcast_user:PASS@127.0.0.1:5432/podcast_db'
    # ...or POSTGRES_HOST/PORT/DB/USER/PASSWORD env vars (same names the other services use).
    # --firestore-database defaults to 'graphfolio-db'; --gcp-project to GOOGLE_CLOUD_PROJECT or
    #   the ADC project. --schema defaults to 'firestore_mirror'. --dry-run to only count.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

import psycopg
from google.cloud import firestore

# (collection, table, pk_column, [(promoted_col, sql_type, doc_key), ...])
COLLECTIONS: list[tuple[str, str, str, list[tuple[str, str, str]]]] = [
    (
        "episodes",
        "episodes",
        "episode_id",
        [
            ("podcast_name", "text", "podcast_name"),
            ("episode_number", "integer", "episode_number"),
            ("episode_title", "text", "episode_title"),
            ("created_time", "timestamptz", "created_time"),
            ("num_likes", "integer", "num_likes"),
            ("number_click", "integer", "number_click"),
            ("related_tickers", "jsonb", "related_tickers"),
        ],
    ),
    ("podcasts", "podcasts", "podcast_name", []),
    ("tags", "tags", "tag", []),
    ("tickers", "tickers", "ticker", []),
    (
        "users",
        "users",
        "id",
        [("email", "text", "email"), ("name", "text", "name")],
    ),
]


def _jsonable(value):
    """Recursively convert Firestore values into something json.dumps can handle."""
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dt.datetime):
        return value.isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    # Firestore GeoPoint / DocumentReference etc. — stringify; we don't expect these here.
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _coerce(col_type: str, raw):
    if raw is None:
        return None
    if col_type == "timestamptz":
        if isinstance(raw, dt.datetime):
            return raw
        if isinstance(raw, str):
            try:
                return dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None
    if col_type == "integer":
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    if col_type == "jsonb":
        return psycopg.types.json.Jsonb(_jsonable(raw))
    return raw  # text


def _database_url(args) -> str:
    if args.database_url:
        return args.database_url
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "podcast_db")
    user = os.getenv("POSTGRES_USER", "podcast_user")
    pw = os.getenv("POSTGRES_PASSWORD", "")
    if not pw:
        sys.exit("error: no --database-url and POSTGRES_PASSWORD is unset")
    return f"postgresql://{user}:{pw}@{host}:{port}/{db}"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--database-url", help="psycopg/libpq connection string for the target DB")
    ap.add_argument("--firestore-database", default="graphfolio-db")
    ap.add_argument(
        "--gcp-project", default=os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT_ID")
    )
    ap.add_argument("--schema", default="firestore_mirror")
    ap.add_argument(
        "--dry-run", action="store_true", help="only count Firestore docs; write nothing"
    )
    args = ap.parse_args()

    fs = firestore.Client(project=args.gcp_project, database=args.firestore_database)
    print(f"firestore: project={fs.project} database={args.firestore_database}")

    if args.dry_run:
        for coll, *_ in COLLECTIONS:
            n = sum(1 for _ in fs.collection(coll).stream())
            print(f"  {coll}: {n} docs")
        return 0

    url = _database_url(args)
    with psycopg.connect(url, autocommit=False) as conn, conn.cursor() as cur:
        cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{args.schema}"')
        for coll, table, pk, promoted in COLLECTIONS:
            cols = (
                [f'"{pk}" text PRIMARY KEY']
                + [f'"{c}" {t}' for c, t, _ in promoted]
                + ['"doc" jsonb NOT NULL']
            )
            cur.execute(f'CREATE TABLE IF NOT EXISTS "{args.schema}"."{table}" ({", ".join(cols)})')
            # add any newly-promoted columns if the table already existed
            for c, t, _ in promoted:
                cur.execute(
                    f'ALTER TABLE "{args.schema}"."{table}" ADD COLUMN IF NOT EXISTS "{c}" {t}'
                )
        conn.commit()

        grand_total = 0
        for coll, table, pk, promoted in COLLECTIONS:
            before = cur.execute(f'SELECT count(*) FROM "{args.schema}"."{table}"').fetchone()[0]
            insert_cols = [pk] + [c for c, _, _ in promoted] + ["doc"]
            placeholders = ", ".join(["%s"] * len(insert_cols))
            updates = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in insert_cols if c != pk)
            col_list = ", ".join(f'"{c}"' for c in insert_cols)
            sql = (
                f'INSERT INTO "{args.schema}"."{table}" ({col_list}) '
                f'VALUES ({placeholders}) ON CONFLICT ("{pk}") DO UPDATE SET {updates}'
            )
            n = 0
            for snap in fs.collection(coll).stream():
                data = snap.to_dict() or {}
                row = [snap.id]
                for _, t, key in promoted:
                    row.append(_coerce(t, data.get(key)))
                row.append(psycopg.types.json.Jsonb(_jsonable(data)))
                cur.execute(sql, row)
                n += 1
            conn.commit()
            after = cur.execute(f'SELECT count(*) FROM "{args.schema}"."{table}"').fetchone()[0]
            print(f"  {coll:>10} -> {args.schema}.{table}: read {n} docs; rows {before} -> {after}")
            grand_total += n

        # round-trip sanity check on a sample episode
        sample = cur.execute(
            f"SELECT episode_id, episode_title, doc->>'mp3_public_url' "
            f'FROM "{args.schema}".episodes LIMIT 1'
        ).fetchone()
        print(f"  sample episode row: {sample}")
        print(f"done: {grand_total} documents mirrored into schema '{args.schema}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
