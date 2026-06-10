"""
Read-only DB queries for ticker insights (podcast_db).
Assumes table ticker_insights exists and is populated elsewhere (tinboker-agents).
Schema: id, episode_id, podcast_launch_time, ticker, bluf_thesis, time_horizon,
        sentiment_score, sentiment, reasons (JSONB), risks (JSONB), created_at.
        Optional: podcaster (or filter by episode_id).
"""
import logging
from datetime import date, datetime
from typing import List, Optional, Any

import psycopg2.extras
from src.database.insight_db import get_connection, is_available

logger = logging.getLogger(__name__)

TABLE = "ticker_insights"


def _row_to_recommendation(row: Any) -> dict:
    """Map a DB row to frontend TickerInsight-compatible shape."""
    return {
        "id": row["id"],
        "episode_id": row["episode_id"] or "",
        "podcaster": row.get("podcaster") or "",
        "podcast_launch_time": _format_iso(row["podcast_launch_time"]),
        "ticker": row["ticker"] or "",
        "bluf_thesis": row["bluf_thesis"] or "",
        "time_horizon": row["time_horizon"] or "",
        "sentiment_score": row["sentiment_score"],
        "sentiment": row["sentiment"] or "",
        "reasons": row["reasons"] if row["reasons"] is not None else [],
        "risks": row["risks"] if row["risks"] is not None else [],
        "created_at": _format_iso(row["created_at"]),
    }


def _format_iso(val: Any) -> str:
    """Format timestamp/date to ISO string."""
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.isoformat() + ("Z" if val.tzinfo is None else "")
    if isinstance(val, date):
        return val.isoformat()
    return str(val)


def get_by_ticker(
    ticker: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[dict]:
    """
    Return recommendations for the given ticker in the date range.
    Ticker is matched case-insensitively; .TW suffix is normalized.
    """
    if not is_available():
        return []
    ticker_norm = (ticker or "").upper().replace(".TW", "").strip()
    if not ticker_norm:
        return []
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, episode_id, podcaster, podcast_launch_time, ticker, bluf_thesis,
                           time_horizon, sentiment_score, sentiment, reasons, risks, created_at
                    FROM ticker_insights
                    WHERE (UPPER(REPLACE(ticker, '.TW', '')) = %s OR ticker = %s)
                    AND (%s::date IS NULL OR podcast_launch_time::date >= %s)
                    AND (%s::date IS NULL OR podcast_launch_time::date <= %s)
                    ORDER BY podcast_launch_time DESC
                    """,
                    (ticker_norm, ticker, start_date, start_date, end_date, end_date),
                )
                rows = cur.fetchall()
                return [_row_to_recommendation(dict(r)) for r in rows]
    except Exception as e:
        logger.warning("get_by_ticker failed: %s", e)
        return []


def get_by_podcaster(
    podcaster: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    podcast_slug: Optional[str] = None,
) -> List[dict]:
    """
    Return recommendations from the given podcaster in the date range.
    Matches podcaster column (ILIKE %podcaster%). When podcast_slug is provided,
    also matches episode_id ILIKE %podcast_slug% so slug-based lookups work.
    """
    if not is_available():
        return []
    podcaster = (podcaster or "").strip()
    slug = (podcast_slug or "").strip() or None
    if not podcaster and not slug:
        return []
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Match podcaster column (show name) and optionally episode_id by slug
                if podcaster and slug:
                    cur.execute(
                        """
                        SELECT id, episode_id, podcaster, podcast_launch_time, ticker, bluf_thesis,
                               time_horizon, sentiment_score, sentiment, reasons, risks, created_at
                        FROM ticker_insights
                        WHERE (podcaster ILIKE %s OR episode_id ILIKE %s)
                        AND (%s::date IS NULL OR podcast_launch_time::date >= %s)
                        AND (%s::date IS NULL OR podcast_launch_time::date <= %s)
                        ORDER BY podcast_launch_time DESC
                        """,
                        (f"%{podcaster}%", f"%{slug}%", start_date, start_date, end_date, end_date),
                    )
                elif slug:
                    cur.execute(
                        """
                        SELECT id, episode_id, podcaster, podcast_launch_time, ticker, bluf_thesis,
                               time_horizon, sentiment_score, sentiment, reasons, risks, created_at
                        FROM ticker_insights
                        WHERE episode_id ILIKE %s
                        AND (%s::date IS NULL OR podcast_launch_time::date >= %s)
                        AND (%s::date IS NULL OR podcast_launch_time::date <= %s)
                        ORDER BY podcast_launch_time DESC
                        """,
                        (f"%{slug}%", start_date, start_date, end_date, end_date),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, episode_id, podcaster, podcast_launch_time, ticker, bluf_thesis,
                               time_horizon, sentiment_score, sentiment, reasons, risks, created_at
                        FROM ticker_insights
                        WHERE podcaster ILIKE %s
                        AND (%s::date IS NULL OR podcast_launch_time::date >= %s)
                        AND (%s::date IS NULL OR podcast_launch_time::date <= %s)
                        ORDER BY podcast_launch_time DESC
                        """,
                        (f"%{podcaster}%", start_date, start_date, end_date, end_date),
                    )
                rows = cur.fetchall()
                return [_row_to_recommendation(dict(r)) for r in rows]
    except Exception as e:
        logger.warning("get_by_podcaster failed: %s", e)
        return []


def get_most_discussed(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = 10,
) -> List[dict]:
    """
    Return most-discussed tickers in the date range as TickerTrending-compatible rows:
    ticker, count, sentiment_score (avg), last_mentioned (max podcast_launch_time).
    """
    if not is_available():
        return []
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT ticker,
                           COUNT(*) AS count,
                           AVG(CAST(sentiment_score AS DOUBLE PRECISION)) AS sentiment_score,
                           MAX(podcast_launch_time) AS last_mentioned
                    FROM ticker_insights
                    WHERE (%s::date IS NULL OR podcast_launch_time::date >= %s)
                    AND (%s::date IS NULL OR podcast_launch_time::date <= %s)
                    GROUP BY ticker
                    ORDER BY count DESC, last_mentioned DESC
                    LIMIT %s
                    """,
                    (start_date, start_date, end_date, end_date, limit),
                )
                rows = cur.fetchall()
                out: List[dict] = []
                for r in rows:
                    d = dict(r)
                    score = d.get("sentiment_score")
                    if score is not None:
                        score = float(score)
                    else:
                        score = 0.0
                    out.append({
                        "ticker": d.get("ticker") or "",
                        "count": int(d.get("count") or 0),
                        "sentiment_score": score,
                        "last_mentioned": _format_iso(d.get("last_mentioned")),
                    })
                return out
    except Exception as e:
        logger.warning("get_most_discussed failed: %s", e)
        return []
