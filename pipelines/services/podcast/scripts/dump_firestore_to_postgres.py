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
from pathlib import Path

import psycopg
from google.cloud import firestore

# Make `src.podcast.exporters.postgres_mirror` importable (the ticker_insights /
# trending_tickers DDL+upsert SQL shared with the live dual-write paths), same
# sys.path trick as scripts/refresh_trending_tickers.py.
_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVICE_ROOT))

from src.podcast.exporters import postgres_mirror  # noqa: E402

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


def _invert_tag_fanout(pairs) -> dict[str, list[str]]:
    """Group ``(slug, episode_id)`` pairs read from ``tags/{slug}/episodes`` into
    ``{episode_id: sorted [slugs]}`` — the shape jsonb-merged onto
    ``episodes.doc['tags']``. Pulled out as a pure function so the grouping logic
    is unit-testable without a live Firestore client."""
    out: dict[str, set[str]] = {}
    for slug, episode_id in pairs:
        out.setdefault(episode_id, set()).add(slug)
    return {episode_id: sorted(slugs) for episode_id, slugs in out.items()}


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
        ti_n = sum(1 for _ in fs.collection_group("tickers").stream())
        print(f"  ticker_insights (collection group 'tickers'): {ti_n} docs")
        tt_n = sum(1 for _ in fs.collection("trending_tickers").stream())
        print(f"  trending_tickers: {tt_n} docs")
        tag_n = sum(1 for _ in fs.collection("tags").stream())
        print(f"  tags (parents, for the episodes.doc->'tags' backfill): {tag_n} docs")
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

        # ticker_insights (collection group 'tickers' under ticker_insights/{episode_id}/tickers/{ticker})
        # and trending_tickers share their DDL/upsert SQL with the live dual-write paths
        # (pipeline.steps.ticker_insights_export, scripts/refresh_trending_tickers.py) via
        # src.podcast.exporters.postgres_mirror — which is schema-locked to
        # EPISODE_DATABASE_SCHEMA, not this script's --schema flag.
        if args.schema != postgres_mirror.SCHEMA:
            print(
                f"  ⚠ --schema={args.schema!r} differs from EPISODE_DATABASE_SCHEMA "
                f"({postgres_mirror.SCHEMA!r}) — ticker_insights/trending_tickers share "
                "DDL with the live mirror writers and are schema-locked to the env var; "
                "skipping those two tables (rerun with EPISODE_DATABASE_SCHEMA set to match)."
            )
        else:
            cur.execute(postgres_mirror.DDL_TICKER_INSIGHTS)
            cur.execute(postgres_mirror.DDL_TRENDING_TICKERS)
            conn.commit()

            ti_n = 0
            for snap in fs.collection_group("tickers").stream():
                data = snap.to_dict() or {}
                episode_id = data.get("episode_id")
                if not episode_id and snap.reference.parent and snap.reference.parent.parent:
                    episode_id = snap.reference.parent.parent.id
                ticker = data.get("ticker") or snap.id
                if not episode_id or not ticker:
                    continue
                postgres_mirror.upsert_ticker_insights(cur, episode_id, {ticker: _jsonable(data)})
                ti_n += 1
            conn.commit()
            print(f"  ticker_insights -> {postgres_mirror.SCHEMA}.ticker_insights: read {ti_n} docs")
            grand_total += ti_n

            tt_n = 0
            for snap in fs.collection("trending_tickers").stream():
                data = snap.to_dict() or {}
                ticker = data.get("ticker") or snap.id
                if not ticker:
                    continue
                postgres_mirror.upsert_trending_tickers(cur, {ticker: _jsonable(data)})
                tt_n += 1
            conn.commit()
            print(f"  trending_tickers -> {postgres_mirror.SCHEMA}.trending_tickers: read {tt_n} docs")
            grand_total += tt_n

            # Invert tags/{slug}/episodes fan-out into episodes.doc->'tags' (mirror
            # only — Firestore is untouched, per the migration's cost rule). Historical
            # episodes were ingested before the live pipeline started stamping `tags`
            # onto the episode doc itself, so the fan-out subcollections are the only
            # source of truth for their tag membership. Cheaper than a collection-group
            # scan of "episodes" (which would also match the root `episodes` collection
            # and `tickers/*/episodes`, re-reading documents already read above):
            # enumerate the (small, curated-vocabulary) tag parents, then read only
            # their own fan-out subcollections.
            tag_slugs = [snap.id for snap in fs.collection("tags").stream()]
            pairs = (
                (slug, sub.id)
                for slug in tag_slugs
                for sub in fs.collection("tags").document(slug).collection("episodes").stream()
            )
            episode_tags = _invert_tag_fanout(pairs)

            merged = 0
            for episode_id, slugs in episode_tags.items():
                if postgres_mirror.merge_episode_doc(cur, episode_id, {"tags": slugs}):
                    merged += 1
            conn.commit()
            print(
                f"  tags (inverted from {len(tag_slugs)} tags/*/episodes fan-outs) -> "
                f"{postgres_mirror.SCHEMA}.episodes.doc->'tags': merged {merged}/{len(episode_tags)} episodes"
            )

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
