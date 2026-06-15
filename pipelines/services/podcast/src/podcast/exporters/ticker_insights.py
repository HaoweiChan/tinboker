"""Write per-(episode, ticker) ticker-insight documents into Firestore.

Output path: ``ticker_insights/{episode_id}/tickers/{ticker}``.
Schema: ``schema_version: 3`` per ``docs/spec-from-platform.md`` § 4.

The pipeline produces a list of TickerInsight rows under
``episode_data.summary_result["ticker_insights"]``. This
module normalizes that list into spec-compliant docs:

    * ``time_horizon`` mapped from English (LLM output) to Chinese
      (``短期`` / ``中期`` / ``長期``).
    * ``sentiment_label`` derived from ``sentiment_score`` using the spec
      cutoffs (``≥0.80`` STRONG_BULLISH, ``≥0.60`` BULLISH, ``≥0.40`` NEUTRAL,
      ``≥0.20`` BEARISH, else STRONG_BEARISH). The score itself is preserved
      in Firestore for sort/tie-break; the spec marks it as internal-only so
      the platform's public serializer must omit it.
    * Risk severity collapses any legacy ``CRITICAL`` to ``HIGH`` so old data
      written before the 3-tier prompt update still validates.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from shared.tickers import canonical_symbol, is_valid_ticker_symbol

SCHEMA_VERSION = 3

_HORIZON_MAP = {
    "SHORT_TERM": "短期",
    "MEDIUM_TERM": "中期",
    "LONG_TERM": "長期",
    "短期": "短期",
    "中期": "中期",
    "長期": "長期",
}

_SEVERITY_NORMALIZE = {
    "LOW": "LOW",
    "MEDIUM": "MEDIUM",
    "HIGH": "HIGH",
    "CRITICAL": "HIGH",  # legacy 4-tier fallback
}


def score_to_label(score: float | None) -> str:
    """Map a 0.0–1.0 score to the 5-tier sentiment label (spec § 4.2)."""
    if score is None:
        return "NEUTRAL"
    if score >= 0.80:
        return "STRONG_BULLISH"
    if score >= 0.60:
        return "BULLISH"
    if score >= 0.40:
        return "NEUTRAL"
    if score >= 0.20:
        return "BEARISH"
    return "STRONG_BEARISH"


def horizon_to_chinese(horizon: str | None) -> str:
    return _HORIZON_MAP.get((horizon or "").upper(), "中期")


def _iso_utc(value: Any) -> str:
    """Coerce common datetime representations to ISO 8601 UTC."""
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return _iso_utc(dt)
        except ValueError:
            return value  # already formatted, pass through
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _extract_list(raw: Any) -> list[dict[str, Any]]:
    """Pull the list of ticker rows from the LLM wrapper or accept a bare list."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    if isinstance(raw, dict):
        # Prefer the current wrapper; tolerate the old key for cached historical
        # payloads that are backfilled into ticker_insights.
        for key in ("ticker_insights", "ticker_recommendations"):
            value = raw.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
    return []


def _clean_locations(item: dict[str, Any]) -> dict[str, Any]:
    """Carry the location quad (time + char index) through if present."""
    out: dict[str, Any] = {}
    for key in ("start_time", "end_time", "start_index", "end_index"):
        if key in item and item[key] is not None:
            out[key] = item[key]
    return out


def _normalize_reason(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "title": str(row.get("title", "")),
        "description": str(row.get("description", "")),
    }
    category = row.get("category")
    if category:
        out["category"] = str(category)
    out.update(_clean_locations(row))
    return out


def _normalize_risk(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "title": str(row.get("title", "")),
        "description": str(row.get("description", "")),
    }
    raw_severity = (row.get("severity") or "").upper()
    severity = _SEVERITY_NORMALIZE.get(raw_severity)
    if severity:
        out["severity"] = severity
    out.update(_clean_locations(row))
    return out


def build_insight_doc(
    *,
    insight: dict[str, Any],
    episode_id: str,
    podcaster: str,
    podcast_launch_time: Any,
) -> dict[str, Any] | None:
    """Translate a single TickerInsight row into the spec-compliant doc.

    Returns None when the row is missing a ticker (the doc would be unkeyable).
    """
    raw_ticker = insight.get("ticker")
    # Skip rows whose "ticker" is not a real listing — the LLM emits sector/category
    # names ("被動元件", "EDGE COMPUTING相關類股") and private companies (ANTHROPIC)
    # here; writing them would create junk sentiment docs + pollute trending.
    if not raw_ticker or not is_valid_ticker_symbol(str(raw_ticker)):
        return None

    ticker = canonical_symbol(str(raw_ticker))
    score = insight.get("sentiment_score")
    try:
        score_value: float | None = float(score) if score is not None else None
    except (TypeError, ValueError):
        score_value = None

    reasons = [
        _normalize_reason(r)
        for r in (insight.get("reasons") or [])
        if isinstance(r, dict)
    ]
    risks = [
        _normalize_risk(r)
        for r in (insight.get("risks") or [])
        if isinstance(r, dict)
    ]

    doc: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "episode_id": episode_id,
        "podcaster": podcaster,
        "podcast_launch_time": _iso_utc(podcast_launch_time),
        "ticker": ticker,
        "bluf_thesis": str(insight.get("bluf_thesis", "")),
        "time_horizon": horizon_to_chinese(insight.get("time_horizon")),
        "sentiment_label": score_to_label(score_value),
        "reasons": reasons,
        "risks": risks,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    if score_value is not None:
        doc["sentiment_score"] = score_value  # internal — platform serializer omits
    if insight.get("price_target") is not None:
        # Not in spec; preserved internally because the LLM emits it and it's
        # cheap to retain. Public serializers must drop it.
        try:
            doc["price_target"] = float(insight["price_target"])
        except (TypeError, ValueError):
            pass
    return doc


def build_episode_insight_docs(
    *,
    raw_payload: Any,
    episode_id: str,
    podcaster: str,
    podcast_launch_time: Any,
) -> dict[str, dict[str, Any]]:
    """Translate the pipeline state ``ticker_insights`` payload into
    ``{canonical_ticker: insight_doc}`` ready for Firestore writes."""
    out: dict[str, dict[str, Any]] = {}
    for row in _extract_list(raw_payload):
        doc = build_insight_doc(
            insight=row,
            episode_id=episode_id,
            podcaster=podcaster,
            podcast_launch_time=podcast_launch_time,
        )
        if doc is None:
            continue
        # If the same ticker appears twice in one episode, the higher-magnitude
        # |score - 0.5| wins (stronger conviction overrides hedged mentions).
        existing = out.get(doc["ticker"])
        if existing is None:
            out[doc["ticker"]] = doc
            continue
        new_score = doc.get("sentiment_score") or 0.5
        old_score = existing.get("sentiment_score") or 0.5
        if abs(new_score - 0.5) > abs(old_score - 0.5):
            out[doc["ticker"]] = doc
    return out


def write_episode_insights(
    firestore_client: Any,
    *,
    episode_id: str,
    docs: dict[str, dict[str, Any]],
) -> int:
    """Batch-write per-ticker docs under ``ticker_insights/{episode_id}/tickers``.

    Returns the number of documents written. The whole subcollection is the
    canonical record per episode — reprocessing overwrites each ticker doc but
    leaves orphans for tickers that have dropped out of the new extraction.
    Callers that want a clean cutover can purge the subcollection beforehand.
    """
    if not docs or not episode_id:
        return 0
    parent = firestore_client.collection("ticker_insights").document(episode_id)
    batch = firestore_client.batch()
    for ticker, doc in docs.items():
        ref = parent.collection("tickers").document(ticker)
        batch.set(ref, doc)
    batch.commit()
    return len(docs)


def iter_insight_tickers(raw_payload: Any) -> Iterable[str]:
    """Yield canonical tickers present in a raw insights payload. Used by
    backfill scripts that want to enumerate without building full docs."""
    for row in _extract_list(raw_payload):
        ticker = row.get("ticker")
        if ticker and is_valid_ticker_symbol(str(ticker)):
            yield canonical_symbol(str(ticker))
