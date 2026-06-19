"""Recompute ``trending_tickers/{ticker}`` aggregates from ticker_insights.

Spec source: ``docs/firestore-contract.md`` § 5. Each ticker gets one document
that powers the Stock Index page and the home-rail trending widget. The module
supports both full backfills and hourly delta refreshes: recent insight docs
identify touched tickers, then only those tickers are recomputed from their
historical source rows.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from .ticker_insights import SCHEMA_VERSION, market_for_ticker, score_to_label

_QUERY_IN_LIMIT = 30
logger = logging.getLogger(__name__)


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


def _iso_utc(value: datetime) -> str:
    dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _row_ticker_market(row: dict[str, Any]) -> tuple[str, str] | None:
    raw_ticker = row.get("ticker")
    if not raw_ticker:
        return None
    ticker = str(raw_ticker).strip().upper()
    market = str(row.get("market") or market_for_ticker(ticker) or "").strip().upper()
    return ticker, market


def _trending_doc_id(
    ticker: str,
    market: str,
) -> str:
    """Return the Firestore doc id for ``trending_tickers``.

    US symbols stay exactly on the canonical token. Non-US symbols always carry
    the market suffix, which keeps the single-string Firestore path future-proof
    if a token ever exists in more than one market.
    """
    if not market:
        raise ValueError(f"missing market for trending ticker {ticker}")
    if market == "US":
        return ticker
    return f"{ticker}.{market}"


def market_collision_doc_ids(
    rows: Iterable[dict[str, Any]],
    *,
    strict: bool = True,
) -> dict[tuple[str, str], str]:
    """Validate and map multi-market ticker tokens to Firestore doc ids."""
    pairs: set[tuple[str, str]] = set()
    for row in rows:
        pair = _row_ticker_market(row)
        if pair is None:
            continue
        ticker, market = pair
        pairs.add(pair)

    unresolved = sorted(ticker for ticker, market in pairs if not market)
    if unresolved and strict:
        raise ValueError(
            "Cannot write trending_tickers for ticker tokens with "
            f"unknown market: {sorted(unresolved)}"
        )

    return {
        pair: _trending_doc_id(pair[0], pair[1])
        for pair in pairs
        if pair[1]
    }


def touched_ticker_markets(insights: Iterable[dict[str, Any]]) -> set[tuple[str, str]]:
    """Return the ticker/market pairs touched by a recent insight window."""
    out: set[tuple[str, str]] = set()
    for row in insights:
        pair = _row_ticker_market(row)
        if pair is not None:
            out.add(pair)
    return out


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
    rows = list(insights)
    now = now or datetime.now(timezone.utc)
    horizon_30d = now - timedelta(days=30)
    horizon_90d = now - timedelta(days=90)
    doc_id_by_pair = market_collision_doc_ids(rows, strict=False)

    by_pair: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        pair = _row_ticker_market(row)
        if pair is None:
            continue
        if pair not in doc_id_by_pair:
            logger.warning(
                "Skipping trending_tickers aggregation for %s: missing or invalid market",
                pair[0],
            )
            continue
        by_pair.setdefault(pair, []).append(row)

    out: dict[str, dict[str, Any]] = {}
    for (ticker, market), rows_for_pair in by_pair.items():
        scores: list[float] = []
        last_dt: datetime | None = None
        podcaster_counts: Counter = Counter()
        episode_records: list[tuple[datetime, dict[str, Any]]] = []
        count_30d = 0
        count_90d = 0
        for row in rows_for_pair:
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
        doc_id = doc_id_by_pair[(ticker, market)]
        doc: dict[str, Any] = {
            "ticker": ticker,
            "market": market or None,
            "schema_version": SCHEMA_VERSION,
            "count_30d": count_30d,
            "count_90d": count_90d,
            "count_all_time": len(rows_for_pair),
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
        out[doc_id] = doc
    return out


def fetch_all_insights(firestore_client: Any) -> list[dict[str, Any]]:
    """Stream every doc in the ``ticker_insights`` collection group.

    A collection-group query pulls every ``ticker_insights/{x}/tickers/{y}``
    document in one pass. For ~5000 docs (the projected backfill size) this
    runs comfortably under the 60s Firestore query budget.
    """
    group = firestore_client.collection_group("tickers")
    return [snap.to_dict() for snap in group.stream()]


def fetch_recent_insights(firestore_client: Any, since: datetime) -> list[dict[str, Any]]:
    """Stream recently-written insight rows for hourly delta refresh."""
    group = firestore_client.collection_group("tickers")
    query = group.where("created_at", ">=", _iso_utc(since))
    return [snap.to_dict() for snap in query.stream()]


def fetch_insights_for_ticker_markets(
    firestore_client: Any,
    ticker_markets: Iterable[tuple[str, str]],
) -> list[dict[str, Any]]:
    """Fetch historical insight rows for only the touched ticker tokens.

    Firestore collection-group ``in`` queries are capped, so symbols are chunked.
    Market filtering is applied client-side to tolerate legacy docs that predate
    the ``market`` field but can still be inferred from ticker shape.
    """
    wanted = set(ticker_markets)
    if not wanted:
        return []
    tickers = sorted({ticker for ticker, _market in wanted})
    rows: list[dict[str, Any]] = []
    group = firestore_client.collection_group("tickers")
    for i in range(0, len(tickers), _QUERY_IN_LIMIT):
        chunk = tickers[i : i + _QUERY_IN_LIMIT]
        query = group.where("ticker", "in", chunk)
        for snap in query.stream():
            data = snap.to_dict()
            pair = _row_ticker_market(data)
            if pair in wanted:
                rows.append(data)
    return rows


def write_trending(
    firestore_client: Any,
    docs: dict[str, dict[str, Any]],
) -> int:
    """Replace each ``trending_tickers/{ticker}`` document. Returns the count.

    Tickers that have dropped out of ``docs`` but still have a Firestore doc are
    NOT pruned here. Legacy *bare-token* docs orphaned by the ``{ticker}.{market}``
    doc-id scheme (PR #229) are cleaned separately — see
    :func:`delete_orphaned_bare_docs`, which the refresh job runs after this.
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
        chunk_written = 0
        for ticker, doc in chunk:
            if not validate_trending_document(ticker, doc):
                continue
            batch.set(collection.document(ticker), doc)
            chunk_written += 1
        if chunk_written:
            batch.commit()
            written += chunk_written
    return written


def validate_trending_document(doc_id: str, doc: dict[str, Any]) -> bool:
    """True when a pending trending doc satisfies the market namespace rule."""
    ticker = str(doc.get("ticker") or "").strip().upper()
    market = str(doc.get("market") or "").strip().upper()
    if not ticker or not market:
        logger.warning(
            "Skipping trending_tickers/%s write: missing ticker or market metadata",
            doc_id,
        )
        return False
    expected_doc_id = _trending_doc_id(ticker, market)
    if doc_id != expected_doc_id:
        logger.warning(
            "Skipping trending_tickers/%s write: expected document id %s for %s/%s",
            doc_id,
            expected_doc_id,
            ticker,
            market,
        )
        return False
    return True


def delete_orphaned_bare_docs(
    firestore_client: Any,
    docs: dict[str, dict[str, Any]],
) -> int:
    """Delete legacy bare-token ``trending_tickers`` docs orphaned by the suffix scheme.

    Before PR #229 a non-US ticker (e.g. ``2330``) was written at the bare doc id
    ``trending_tickers/2330``. PR #229 moved non-US tickers to ``{ticker}.{market}``
    (``trending_tickers/2330.TW``) but left the old doc in place. Both then stream
    out of the backend ``InsightService.get_trending``, which maps rows by the
    ``ticker`` *field* — so 2330 double-lists in StockIndex / WeeklyBuzz / HomeRail.

    For every suffixed (non-US) doc in ``docs`` — i.e. one we just wrote whose
    id differs from its bare ``ticker`` — delete the matching bare-token doc, but
    only when that bare doc is **not** itself a live US-market doc. That guard keeps
    a token that legitimately exists in both markets (US at the bare id, non-US at
    the suffixed id) from losing its US row. Pruning is scoped to tickers we just
    rewrote, so a bare doc is only removed once its suffixed replacement exists.

    Returns the number of bare docs deleted. Safe to call repeatedly (idempotent).
    """
    if not docs:
        return 0
    collection = firestore_client.collection("trending_tickers")

    # Orphan candidates: the bare token of each suffixed doc we just wrote. A US
    # doc already lives at the bare id (doc_id == ticker), so it is never a
    # candidate. Dedup so a token mentioned across markets is checked once.
    candidates: set[str] = set()
    for doc_id, doc in docs.items():
        ticker = str(doc.get("ticker") or "").strip().upper()
        if ticker and doc_id != ticker:
            candidates.add(ticker)

    stale_refs = []
    for ticker in sorted(candidates):
        ref = collection.document(ticker)
        snap = ref.get()
        if not getattr(snap, "exists", False):
            continue
        existing = snap.to_dict() or {}
        if str(existing.get("market") or "").strip().upper() == "US":
            continue  # legitimate US doc sharing the token — keep it
        stale_refs.append(ref)

    deleted = 0
    batch_size = 400  # Firestore batches cap at 500 operations.
    while stale_refs:
        chunk = stale_refs[:batch_size]
        stale_refs = stale_refs[batch_size:]
        batch = firestore_client.batch()
        for ref in chunk:
            batch.delete(ref)
        batch.commit()
        deleted += len(chunk)
    if deleted:
        logger.info("Deleted %d orphaned bare-token trending_tickers docs", deleted)
    return deleted
