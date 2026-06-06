"""Recompute the ``trending_tickers/{ticker}`` aggregate from ticker_insights.

Spec source: ``docs/spec-from-platform.md`` § 5. Each ticker gets one document
that powers the Stock Index page and the home-rail trending widget. The
aggregate is recomputed in full from the per-(episode, ticker) source of truth
— there's no incremental state to maintain.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from .ticker_insights import SCHEMA_VERSION, score_to_label


def _parse_launch_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def aggregate_trending(
    insights: Iterable[dict[str, Any]],
    *,
    now: datetime | None = None,
    top_n: int = 5,
) -> dict[str, dict[str, Any]]:
    """Group per-(episode, ticker) insight docs into per-ticker trending rows.

    Each input dict is expected to follow the schema written by
    :func:`ticker_insights.build_insight_doc` — that's the same shape the
    Firestore ``ticker_insights/*/tickers/*`` collection group yields.
    """
    now = now or datetime.now(timezone.utc)
    horizon_30d = now - timedelta(days=30)
    horizon_90d = now - timedelta(days=90)

    by_ticker: dict[str, list[dict[str, Any]]] = {}
    for row in insights:
        ticker = row.get("ticker")
        if not ticker:
            continue
        by_ticker.setdefault(ticker, []).append(row)

    out: dict[str, dict[str, Any]] = {}
    for ticker, rows in by_ticker.items():
        scores: list[float] = []
        last_dt: datetime | None = None
        podcaster_counts: Counter = Counter()
        episode_records: list[tuple[datetime, dict[str, Any]]] = []
        count_30d = 0
        count_90d = 0
        for row in rows:
            score = row.get("sentiment_score")
            if isinstance(score, (int, float)):
                scores.append(float(score))
            launch_dt = _parse_launch_time(row.get("podcast_launch_time"))
            if launch_dt:
                if last_dt is None or launch_dt > last_dt:
                    last_dt = launch_dt
                if launch_dt >= horizon_30d:
                    count_30d += 1
                if launch_dt >= horizon_90d:
                    count_90d += 1
                episode_records.append(
                    (
                        launch_dt,
                        {
                            "episode_id": row.get("episode_id"),
                            "podcast_name": row.get("podcaster"),
                            "launch_time": row.get("podcast_launch_time"),
                        },
                    )
                )
            podcaster = row.get("podcaster")
            if podcaster:
                podcaster_counts[podcaster] += 1

        avg_score = _avg(scores)
        episode_records.sort(key=lambda x: x[0], reverse=True)
        doc: dict[str, Any] = {
            "ticker": ticker,
            "schema_version": SCHEMA_VERSION,
            "count_30d": count_30d,
            "count_90d": count_90d,
            "count_all_time": len(rows),
            "sentiment_label": score_to_label(avg_score),
            "last_mentioned": (
                last_dt.astimezone(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z")
                if last_dt
                else None
            ),
            "top_podcasters": [
                {"name": name, "count": count}
                for name, count in podcaster_counts.most_common(top_n)
            ],
            "top_episodes": [item for _, item in episode_records[:top_n]],
            "computed_at": now.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
        }
        if avg_score is not None:
            doc["sentiment_score"] = avg_score  # internal; serializer must drop
        out[ticker] = doc
    return out


def fetch_all_insights(firestore_client: Any) -> list[dict[str, Any]]:
    """Stream every doc in the ``ticker_insights`` collection group.

    A collection-group query pulls every ``ticker_insights/{x}/tickers/{y}``
    document in one pass. For ~5000 docs (the projected backfill size) this
    runs comfortably under the 60s Firestore query budget.
    """
    group = firestore_client.collection_group("tickers")
    return [snap.to_dict() for snap in group.stream()]


def write_trending(
    firestore_client: Any,
    docs: dict[str, dict[str, Any]],
) -> int:
    """Replace each ``trending_tickers/{ticker}`` document. Returns the count.

    Stale tickers (no longer in ``docs`` but present in Firestore) are NOT
    deleted automatically — that's a separate housekeeping concern.
    """
    if not docs:
        return 0
    collection = firestore_client.collection("trending_tickers")
    # Firestore batches cap at 500 operations.
    batch_size = 400
    pending = list(docs.items())
    written = 0
    while pending:
        chunk = pending[:batch_size]
        pending = pending[batch_size:]
        batch = firestore_client.batch()
        for ticker, doc in chunk:
            batch.set(collection.document(ticker), doc)
        batch.commit()
        written += len(chunk)
    return written
