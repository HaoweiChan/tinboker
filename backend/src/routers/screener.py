"""Internal read API for the whole-market TW anomaly screener (issue #450).

``GET /api/screener/candidates`` returns the ranked Stage-1 passers for a trading
day. Machine-only — gated by the ``X-Internal-Key`` header vs the ``INTERNAL_API_KEY``
setting (same mechanism as the #449 whole-market data endpoints). Missing/bad key
→ 401.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from src.config import settings
from src.database.models import ScreenerCandidate
from src.database.postgres import get_session

router = APIRouter(prefix="/api/screener", tags=["screener"])


def require_internal_key(x_internal_key: Optional[str] = Header(None, alias="X-Internal-Key")) -> None:
    """Reject the request unless the caller presents the shared internal key."""
    expected = settings.internal_api_key
    if not expected or x_internal_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing internal key")


def _serialize(row: ScreenerCandidate) -> dict:
    return {
        "date": row.date,
        "ticker": row.ticker,
        "rank": row.rank,
        "final_score": row.final_score,
        "momentum_score": row.momentum_score,
        "institution_score": row.institution_score,
        "factors": row.factors or {},
        "is_60d_high": bool(row.is_60d_high),
        "crowded": bool(row.crowded),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/candidates", dependencies=[Depends(require_internal_key)])
def get_candidates(
    date: Optional[str] = Query(None, description="Trading day YYYY-MM-DD; defaults to the latest present"),
    limit: Optional[int] = Query(None, ge=1, description="Max rows; default = all for that date"),
    db: Session = Depends(get_session),
) -> dict:
    """Ranked screener candidates for a date, ordered by ``rank`` asc."""
    if not date:
        latest = (
            db.query(ScreenerCandidate.date)
            .order_by(ScreenerCandidate.date.desc())
            .first()
        )
        if not latest:
            return {"date": None, "count": 0, "candidates": []}
        date = latest[0]

    query = (
        db.query(ScreenerCandidate)
        .filter(ScreenerCandidate.date == date)
        .order_by(ScreenerCandidate.rank.asc())
    )
    if limit:
        query = query.limit(limit)
    rows = query.all()
    return {"date": date, "count": len(rows), "candidates": [_serialize(r) for r in rows]}
