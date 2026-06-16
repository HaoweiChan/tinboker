"""
Ticker insights service: read-only access to Firestore-backed ticker insight data.

Phase A scope (this file): trending_tickers/{ticker} → /api/ticker-insights/trending.
Phase B (TODO): ticker_insights/{episode_id}/tickers/{ticker} → by-ticker / by-podcaster.

Contract: docs/firestore-contract.md §§ 4–5.
"""
import asyncio
import json
import logging
from datetime import date, datetime, timedelta
from typing import Any, List, Optional, Tuple

from src.cache.cache_config import CACHE_TTL
from src.cache.redis_client import cache_get, cache_set
from src.services.firestore_service import FirestoreService

logger = logging.getLogger(__name__)

TRENDING_TTL = 7200  # 2h, matches recommendation_service
INSIGHT_TTL = 7200  # 2h
RECENT_TTL = 600  # 10 min — /recent is a live feed; align with the ~10-min pipeline pull
SCHEMA_VERSION = 3
SUPPORTED_SCHEMA_VERSIONS = {2, SCHEMA_VERSION}
TRENDING_COLLECTION = "trending_tickers"
# Collection-group ID for ticker_insights/{episode_id}/tickers/{ticker}.
# Same ID as the legacy inverted-index root collection, so callers MUST filter
# results by a supported `schema_version` to disambiguate.
INSIGHTS_SUBCOLLECTION = "tickers"
SEVERITY_LEVELS = {"HIGH", "MEDIUM", "LOW"}
SENTIMENT_LABELS = {
    "STRONG_BULLISH",
    "BULLISH",
    "NEUTRAL",
    "BEARISH",
    "STRONG_BEARISH",
}


def _score_to_label(score: Optional[float]) -> str:
    """Score-to-label cutoffs per spec § 4.2."""
    if score is None:
        return "NEUTRAL"
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "NEUTRAL"
    if s >= 0.80:
        return "STRONG_BULLISH"
    if s >= 0.60:
        return "BULLISH"
    if s >= 0.40:
        return "NEUTRAL"
    if s >= 0.20:
        return "BEARISH"
    return "STRONG_BEARISH"


def _pick_count(doc: dict, days: int) -> int:
    """Select the rolling-window count field per § 5.2."""
    if days == 0:
        return int(doc.get("count_all_time") or 0)
    if days <= 30:
        return int(doc.get("count_30d") or 0)
    return int(doc.get("count_90d") or 0)


def _resolve_date_range(
    start_date: Optional[str], end_date: Optional[str]
) -> Tuple[date, date]:
    """Parse ISO YYYY-MM-DD; default to last 7 days when either side is missing."""
    end_parsed = _parse_iso_date(end_date)
    start_parsed = _parse_iso_date(start_date)
    if start_parsed is None or end_parsed is None:
        today = date.today()
        return today - timedelta(days=7), today
    return start_parsed, end_parsed


def _parse_iso_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        if "T" in s or " " in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _ticker_candidates(ticker: str) -> List[str]:
    """Normalize and expand a ticker to the variants the agents pipeline may write.

    Mirrors the legacy Postgres normalization (`UPPER(REPLACE(ticker, '.TW', ''))`)
    by querying for both the bare symbol and its `.TW` variant. Firestore's `in`
    filter supports up to 30 values, so 2 is comfortably within bounds.
    """
    t = (ticker or "").upper().strip()
    if not t:
        return []
    if t.endswith(".TW"):
        return [t, t[:-3]]
    return [t, f"{t}.TW"]


def _in_range(iso_str: str, start: date, end: date) -> bool:
    """Inclusive date-range check against an ISO 8601 timestamp string."""
    if not iso_str:
        return False
    try:
        d = datetime.fromisoformat(iso_str.replace("Z", "+00:00")).date()
    except (ValueError, TypeError):
        return False
    return start <= d <= end


def _safe_int(value: Any) -> int:
    """Best-effort int; 0 on anything non-numeric (defends against dirty docs)."""
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return 0


def _coerce_ms(value: Any) -> int:
    """Coerce a reason/risk timestamp to integer milliseconds.

    Tolerates the two shapes the pipeline has emitted: a plain ms int, and a
    human-readable ``MM:SS.mmm`` / ``HH:MM:SS.mmm`` string (older output). A bad
    value yields 0 rather than 500-ing the whole insight response.
    """
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    if not s:
        return 0
    if ":" in s:
        try:
            parts = [float(p) for p in s.split(":")]
        except (ValueError, TypeError):
            return 0
        if len(parts) == 2:
            total_seconds = parts[0] * 60 + parts[1]
        elif len(parts) == 3:
            total_seconds = parts[0] * 3600 + parts[1] * 60 + parts[2]
        else:
            return 0
        return int(total_seconds * 1000)
    return _safe_int(s)


def _doc_to_insight(doc: dict) -> dict:
    """
    Map a ticker_insights subcollection doc to the TickerInsight API shape
    per spec § 4.3. Strips `sentiment_score` (internal-only per § 4.2).
    """
    label = doc.get("sentiment_label")
    if label not in SENTIMENT_LABELS:
        label = _score_to_label(doc.get("sentiment_score"))

    def _clean_risk(r: dict) -> dict:
        severity = r.get("severity")
        if severity not in SEVERITY_LEVELS:
            severity = None
        out = {
            "title": r.get("title") or "",
            "description": r.get("description") or "",
            "start_time": _coerce_ms(r.get("start_time")),
            "end_time": _coerce_ms(r.get("end_time")),
            "start_index": _safe_int(r.get("start_index")),
            "end_index": _safe_int(r.get("end_index")),
        }
        if severity:
            out["severity"] = severity
        return out

    def _clean_reason(r: dict) -> dict:
        out = {
            "title": r.get("title") or "",
            "description": r.get("description") or "",
            "start_time": _coerce_ms(r.get("start_time")),
            "end_time": _coerce_ms(r.get("end_time")),
            "start_index": _safe_int(r.get("start_index")),
            "end_index": _safe_int(r.get("end_index")),
        }
        category = r.get("category")
        if category:
            out["category"] = category
        return out

    return {
        "episode_id": doc.get("episode_id") or doc.get("_parent_id") or "",
        "podcaster": doc.get("podcaster") or "",
        "podcast_launch_time": doc.get("podcast_launch_time") or "",
        "ticker": doc.get("ticker") or "",
        "bluf_thesis": doc.get("bluf_thesis") or "",
        "time_horizon": doc.get("time_horizon") or "",
        "sentiment_label": label,
        "reasons": [
            _clean_reason(r) for r in (doc.get("reasons") or []) if isinstance(r, dict)
        ],
        "risks": [
            _clean_risk(r) for r in (doc.get("risks") or []) if isinstance(r, dict)
        ],
        "created_at": doc.get("created_at") or "",
    }


def _doc_to_trending(doc: dict, days: int) -> dict:
    """Map a trending_tickers/{ticker} Firestore doc to the TickerTrending API shape."""
    label = doc.get("sentiment_label")
    if label not in SENTIMENT_LABELS:
        label = _score_to_label(doc.get("sentiment_score"))
    return {
        "ticker": doc.get("ticker") or doc.get("id") or "",
        "count": _pick_count(doc, days),
        "sentiment_label": label,
        "last_mentioned": doc.get("last_mentioned") or "",
    }


class InsightService:
    """Reads ticker insight / trending data from Firestore."""

    def __init__(self) -> None:
        self._fs = FirestoreService()

    async def get_trending(self, days: int = 30, limit: int = 100) -> List[dict]:
        """
        Return TickerTrending[] from Firestore trending_tickers/*.

        days=30 → count_30d, days=90 → count_90d, days=0 → count_all_time.
        Replaces /api/recommendations/buzz (spec § 5.2).
        """
        cache_key = f"ticker_insights:trending:{days}:{limit}"
        cached = await cache_get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception as e:
                logger.warning("Trending cache deserialize failed: %s", e)

        docs = await asyncio.to_thread(
            self._fs.get_all_documents, TRENDING_COLLECTION
        )
        rows = [_doc_to_trending(d, days) for d in docs if d.get("ticker") or d.get("id")]
        rows = [r for r in rows if r["count"] > 0 and r["ticker"]]

        if not rows:
            logger.info("trending_tickers empty; falling back to episode aggregation")
            rows = await self._aggregate_from_episodes(days)
            rows = rows[:limit]
            try:
                await cache_set(
                    cache_key,
                    json.dumps(rows, default=str),
                    CACHE_TTL.get("ticker_insights_trending", TRENDING_TTL),
                )
            except Exception as e:
                logger.warning("Trending cache set failed (episode fallback): %s", e)
            return rows
        # Sort by count desc, then last_mentioned desc (ISO strings sort lexicographically).
        rows.sort(key=lambda r: (r["count"], r["last_mentioned"]), reverse=True)
        rows = rows[:limit]

        try:
            await cache_set(
                cache_key,
                json.dumps(rows, default=str),
                CACHE_TTL.get("ticker_insights_trending", TRENDING_TTL),
            )
        except Exception as e:
            logger.warning("Trending cache set failed: %s", e)
        return rows

    async def _aggregate_from_episodes(self, days: int) -> List[dict]:
        """Aggregate trending tickers from episodes.related_tickers when trending_tickers is empty."""
        from collections import Counter

        episode_docs = await asyncio.to_thread(
            self._fs.get_all_documents, "episodes"
        )
        cutoff_ms = None
        if days > 0:
            cutoff_ms = (datetime.utcnow() - timedelta(days=days)).timestamp() * 1000

        counts: Counter = Counter()
        last_seen: dict = {}
        for doc in episode_docs:
            ts_ms = doc.get("released_at_ms") or 0
            if cutoff_ms and ts_ms < cutoff_ms:
                continue
            tickers = doc.get("related_tickers") or []
            ts_s = ts_ms / 1000 if ts_ms > 1e10 else ts_ms or 0
            try:
                dt = datetime.utcfromtimestamp(ts_s).strftime("%Y-%m-%d") if ts_s else ""
            except (OSError, OverflowError, ValueError):
                dt = ""
            for ticker in tickers:
                if not ticker:
                    continue
                counts[ticker] += 1
                if dt > last_seen.get(ticker, ""):
                    last_seen[ticker] = dt

        rows = [
            {
                "ticker": t,
                "count": c,
                "sentiment_label": "NEUTRAL",
                "last_mentioned": last_seen.get(t, ""),
            }
            for t, c in counts.most_common()
        ]
        rows.sort(key=lambda r: (r["count"], r["last_mentioned"]), reverse=True)
        return rows

    async def get_by_ticker(
        self,
        ticker: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[dict]:
        """
        Return TickerInsight[] for the given ticker in the date range.
        Default window: last 7 days. Spec § 4.4.
        """
        tickers = _ticker_candidates(ticker)
        if not tickers:
            return []

        start, end = _resolve_date_range(start_date, end_date)
        cache_key = f"ticker_insights:by_ticker:{','.join(tickers)}:{start}:{end}"
        cached = await cache_get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception as e:
                logger.warning("Insight cache deserialize failed: %s", e)

        # Collection-group query on the `tickers` subcollection. Filter on the
        # explicit `ticker` field — the legacy root `tickers/{X}` parent docs
        # don't carry a `ticker` field, so this naturally excludes them.
        docs = await asyncio.to_thread(
            self._fs.query_collection_group,
            INSIGHTS_SUBCOLLECTION,
            [("ticker", "in", tickers)],
            None,
            None,
            None,
        )
        rows = []
        for d in docs:
            if d.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
                continue
            if not _in_range(d.get("podcast_launch_time") or "", start, end):
                continue
            rows.append(_doc_to_insight(d))
        rows.sort(key=lambda r: r["podcast_launch_time"], reverse=True)

        try:
            await cache_set(
                cache_key,
                json.dumps(rows, default=str),
                CACHE_TTL.get("ticker_insights_by_ticker", INSIGHT_TTL),
            )
        except Exception as e:
            logger.warning("Insight cache set failed: %s", e)
        return rows

    async def get_by_podcaster(
        self,
        podcaster: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[dict]:
        """
        Return TickerInsight[] from the given podcaster in the date range.
        Default window: last 7 days.

        Spec § 4.1 mandates a `podcaster` field on every insight doc, so the
        legacy `episode_id ILIKE %slug%` matching from the Postgres path is
        no longer needed.
        """
        name = (podcaster or "").strip()
        if not name:
            return []

        start, end = _resolve_date_range(start_date, end_date)
        # `:v2` + short TTL — /picks channel-history reads this, so edits/purges
        # (e.g. templated-insight cleanup) should reflect within minutes, and the
        # bump sidesteps any pre-cleanup cached rows.
        cache_key = f"ticker_insights:by_podcaster:v2:{name}:{start}:{end}"
        cached = await cache_get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception as e:
                logger.warning("Insight cache deserialize failed: %s", e)

        docs = await asyncio.to_thread(
            self._fs.query_collection_group,
            INSIGHTS_SUBCOLLECTION,
            [("podcaster", "==", name)],
            None,
            None,
            None,
        )
        rows = []
        for d in docs:
            if d.get("schema_version") not in SUPPORTED_SCHEMA_VERSIONS:
                continue
            if not _in_range(d.get("podcast_launch_time") or "", start, end):
                continue
            rows.append(_doc_to_insight(d))
        rows.sort(key=lambda r: r["podcast_launch_time"], reverse=True)

        try:
            await cache_set(cache_key, json.dumps(rows, default=str), RECENT_TTL)
        except Exception as e:
            logger.warning("Insight cache set failed: %s", e)
        return rows

    async def get_recent(self, limit: int = 100) -> List[dict]:
        """
        Recent TickerInsight[] across ALL podcasters, newest-first (blended feed).

        Collection-group query on the `tickers` subcollection ordered by
        `podcast_launch_time` DESC with a hard limit — the /picks blended timeline.
        Over-fetches (2×) so legacy / non-conforming docs can be dropped before
        trimming to `limit`. Requires a single-field COLLECTION_GROUP index on
        `tickers.podcast_launch_time` (descending).
        """
        limit = max(1, min(int(limit or 100), 200))
        # `:v2` namespace — the response now carries episode_title; bumping the key
        # also sidesteps any rows cached before that field existed.
        cache_key = f"ticker_insights:recent:v2:{limit}"
        cached = await cache_get(cache_key)
        if cached:
            try:
                return json.loads(cached)
            except Exception as e:
                logger.warning("Recent cache deserialize failed: %s", e)

        docs = await asyncio.to_thread(
            self._fs.query_collection_group,
            INSIGHTS_SUBCOLLECTION,
            None,
            "podcast_launch_time",
            "DESCENDING",
            limit * 2,
        )
        rows = [
            _doc_to_insight(d)
            for d in docs
            if d.get("schema_version") in SUPPORTED_SCHEMA_VERSIONS
        ][:limit]

        # Attach the source episode title (so the blended feed can show "which
        # episode mentioned this"). One batched read per cache-miss; the episode
        # doc id == the insight's episode_id.
        ep_ids = list({r["episode_id"] for r in rows if r.get("episode_id")})
        if ep_ids:
            try:
                eps = await asyncio.to_thread(self._fs.get_documents_batch, "episodes", ep_ids)
                title_map = {e.get("id"): (e.get("episode_title") or "") for e in eps}
                for r in rows:
                    r["episode_title"] = title_map.get(r.get("episode_id"), "")
            except Exception as e:
                logger.warning("Recent episode-title join failed: %s", e)

        try:
            await cache_set(cache_key, json.dumps(rows, default=str), RECENT_TTL)
        except Exception as e:
            logger.warning("Recent cache set failed: %s", e)
        return rows
