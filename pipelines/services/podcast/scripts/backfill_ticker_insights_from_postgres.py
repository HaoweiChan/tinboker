#!/usr/bin/env python3
"""Phase B2 migration from legacy Postgres ticker rows to Firestore.

Migrates historical rows from the old ``ticker_insights`` / renamed
``ticker_recommendations`` Postgres table into the Firestore composite path:

    ticker_insights/{episode_id}/tickers/{ticker}

The script intentionally reuses the live exporter normalizer so backfilled docs
match new podcast pipeline writes: canonical ticker tokens, internal ``market``
namespace, Chinese horizons, and the § 4.2 five-tier ``sentiment_label`` enum.

Historical scale is expected to be low-thousands, so writes use ordinary
Firestore WriteBatch commits in chunks of 500 operations. Each chunk is atomic;
there is no partition worker or distributed coordinator.

Usage:
    uv run python services/podcast/scripts/backfill_ticker_insights_from_postgres.py --dry-run
    uv run python services/podcast/scripts/backfill_ticker_insights_from_postgres.py --postgres-url "$DATABASE_URL"
    uv run python services/podcast/scripts/backfill_ticker_insights_from_postgres.py --table ticker_recommendations
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sqlalchemy as sa

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVICE_ROOT))

from src.podcast.exporters.ticker_insights import (  # noqa: E402
    build_insight_doc,
    score_to_label,
    write_many_episode_insights,
)
from src.service.upload_to_firebase import FirebaseService  # noqa: E402

DEFAULT_TABLE = "ticker_insights"
DEFAULT_BATCH_SIZE = 500

_POSTGRES_ENV_KEYS = (
    "LEGACY_RECOMMENDATION_DATABASE_URL",
    "RECOMMENDATION_DATABASE_URL",
    "TICKER_INSIGHTS_DATABASE_URL",
    "POSTGRES_URL",
    "POSTGRES_DATABASE_URL",
    "DATABASE_URL",
)

_COLUMN_CANDIDATES = (
    "id",
    "episode_id",
    "podcaster",
    "podcast_launch_time",
    "ticker",
    "bluf_thesis",
    "time_horizon",
    "sentiment_score",
    "sentiment_label",
    "sentiment",
    "reasons",
    "risks",
    "created_at",
)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _iso_utc(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, str):
        try:
            return _iso_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return value
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _split_table_name(raw: str) -> tuple[str, str]:
    parts = raw.split(".")
    if len(parts) == 1:
        schema, table = "public", parts[0]
    elif len(parts) == 2:
        schema, table = parts
    else:
        raise ValueError(f"Invalid table name: {raw!r}")
    for part in (schema, table):
        if not _IDENTIFIER_RE.fullmatch(part):
            raise ValueError(f"Unsafe table identifier: {raw!r}")
    return schema, table


def _qualified_table(raw: str) -> str:
    schema, table = _split_table_name(raw)
    return f'"{schema}"."{table}"'


def _postgres_url(cli_value: str | None) -> str:
    if cli_value:
        return cli_value
    for key in _POSTGRES_ENV_KEYS:
        value = os.getenv(key)
        if value:
            return value
    keys = ", ".join(_POSTGRES_ENV_KEYS)
    raise RuntimeError(f"Postgres URL is required; set one of: {keys}")


def _table_columns(conn: sa.Connection, table_name: str) -> set[str]:
    schema, table = _split_table_name(table_name)
    rows = conn.execute(
        sa.text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = :table
            """
        ),
        {"schema": schema, "table": table},
    )
    return {str(row[0]) for row in rows}


def _select_legacy_rows(
    conn: sa.Connection,
    *,
    table_name: str,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    columns = _table_columns(conn, table_name)
    missing_required = {"episode_id", "ticker"} - columns
    if missing_required:
        missing = ", ".join(sorted(missing_required))
        raise RuntimeError(f"{table_name} is missing required column(s): {missing}")

    selected = [c for c in _COLUMN_CANDIDATES if c in columns]
    order_cols = [c for c in ("created_at", "id", "episode_id", "ticker") if c in columns]
    order_sql = ", ".join(f'"{c}"' for c in order_cols) or '"episode_id", "ticker"'
    limit_sql = " LIMIT :limit" if limit else ""
    sql = sa.text(
        f"""
        SELECT {", ".join(f'"{c}"' for c in selected)}
        FROM {_qualified_table(table_name)}
        ORDER BY {order_sql}
        {limit_sql}
        """
    )
    params = {"limit": limit} if limit else {}
    return [dict(row) for row in conn.execute(sql, params).mappings()]


def _json_list(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if not isinstance(value, list):
        return []

    out: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            out.append(item)
        elif isinstance(item, str):
            out.append({"title": "", "description": item})
    return out


def _score_from_sentiment(value: Any) -> float | None:
    if value is None:
        return None
    label = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if not label:
        return None
    if "strong" in label and ("bull" in label or "positive" in label):
        return 0.9
    if "bull" in label or "positive" in label:
        return 0.7
    if "neutral" in label or "neut" in label:
        return 0.5
    if "strong" in label and ("bear" in label or "negative" in label):
        return 0.1
    if "bear" in label or "negative" in label:
        return 0.3
    return None


def normalize_legacy_score(score: Any, sentiment_fallback: Any = None) -> float | None:
    """Coerce historical score shapes to the current 0.0-1.0 contract range."""
    try:
        value = float(score) if score is not None else None
    except (TypeError, ValueError):
        value = None

    if value is None:
        return _score_from_sentiment(sentiment_fallback)
    if value > 1:
        if value <= 10:
            value = value / 10
        elif value <= 100:
            value = value / 100
    return max(0.0, min(1.0, value))


def _legacy_row_to_doc(row: Mapping[str, Any]) -> dict[str, Any] | None:
    episode_id = str(row.get("episode_id") or "").strip()
    if not episode_id:
        return None

    score = normalize_legacy_score(row.get("sentiment_score"), row.get("sentiment"))
    insight = {
        "ticker": row.get("ticker"),
        "bluf_thesis": row.get("bluf_thesis") or "",
        "time_horizon": row.get("time_horizon"),
        "sentiment_score": score,
        "reasons": _json_list(row.get("reasons")),
        "risks": _json_list(row.get("risks")),
    }
    doc = build_insight_doc(
        insight=insight,
        episode_id=episode_id,
        podcaster=str(row.get("podcaster") or ""),
        podcast_launch_time=row.get("podcast_launch_time") or row.get("created_at"),
    )
    if doc is None or not doc.get("market"):
        return None
    if row.get("created_at") is not None:
        doc["created_at"] = _iso_utc(row.get("created_at"))
    # Be explicit in the migration path: the label is always derived from the
    # normalized legacy score, never copied from old freeform sentiment text.
    doc["sentiment_label"] = score_to_label(score)
    return doc


def build_episode_docs_from_legacy_rows(
    rows: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, dict[str, dict[str, Any]]], list[Mapping[str, Any]]]:
    """Return ``{episode_id: {ticker: doc}}`` plus rows skipped as unkeyable."""
    episode_docs: dict[str, dict[str, dict[str, Any]]] = {}
    skipped: list[Mapping[str, Any]] = []

    for row in rows:
        doc = _legacy_row_to_doc(row)
        if doc is None:
            skipped.append(row)
            continue
        episode_id = doc["episode_id"]
        ticker = doc["ticker"]
        by_ticker = episode_docs.setdefault(episode_id, {})
        existing = by_ticker.get(ticker)
        if existing is None:
            by_ticker[ticker] = doc
            continue
        new_score = doc.get("sentiment_score") or 0.5
        old_score = existing.get("sentiment_score") or 0.5
        if abs(new_score - 0.5) > abs(old_score - 0.5):
            by_ticker[ticker] = doc

    return episode_docs, skipped


def _count_docs(episode_docs: Mapping[str, Mapping[str, Any]]) -> int:
    return sum(len(docs) for docs in episode_docs.values())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--postgres-url", help="legacy Postgres SQLAlchemy URL")
    ap.add_argument("--table", default=DEFAULT_TABLE, help="legacy table name")
    ap.add_argument("--limit", type=int, help="read at most N rows")
    ap.add_argument("--dry-run", action="store_true", help="build docs but do not write")
    ap.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Firestore WriteBatch chunk size; must be <= 500",
    )
    args = ap.parse_args()

    if args.batch_size <= 0 or args.batch_size > DEFAULT_BATCH_SIZE:
        raise SystemExit("--batch-size must be between 1 and 500")

    engine = sa.create_engine(_postgres_url(args.postgres_url))
    with engine.connect() as conn:
        rows = _select_legacy_rows(conn, table_name=args.table, limit=args.limit)

    episode_docs, skipped = build_episode_docs_from_legacy_rows(rows)
    total_docs = _count_docs(episode_docs)
    print(
        f"Read {len(rows)} legacy rows from {args.table}; "
        f"built {total_docs} Firestore docs across {len(episode_docs)} episodes."
    )
    if skipped:
        print(f"Skipped {len(skipped)} rows with missing/invalid episode, ticker, or market metadata.")

    if args.dry_run:
        sample = next(iter(next(iter(episode_docs.values())).values()), None) if episode_docs else None
        if sample:
            print(
                "Sample:",
                {
                    "episode_id": sample.get("episode_id"),
                    "ticker": sample.get("ticker"),
                    "market": sample.get("market"),
                    "sentiment_label": sample.get("sentiment_label"),
                },
            )
        return 0

    fb = FirebaseService()
    written = write_many_episode_insights(
        fb.db,
        episode_docs,
        batch_size=args.batch_size,
    )
    print(f"Wrote {written} ticker_insights docs in <= {args.batch_size}-op Firestore batches.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
