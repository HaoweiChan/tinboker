"""Unit tests for the whole-market TW anomaly screener (issue #450).

Covers the pure compute layer (universe filter, Stage-1 gates, flags, scoring)
plus a DB-backed round trip through the compute service and the internal-key
gated read endpoint.
"""

import os
import tempfile
from datetime import datetime, timedelta

import pytest

import src.database.postgres as pg
from src.config import settings
from src.services import screener_refresh as sr


# --------------------------------------------------------------------------- #
# Synthetic-data helpers
# --------------------------------------------------------------------------- #
def _dates(n: int, start: str = "2025-01-01") -> list[str]:
    """n sequential YYYY-MM-DD strings (calendar days; ordering is all that matters)."""
    base = datetime.strptime(start, "%Y-%m-%d")
    return [(base + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(n)]


def _clean_breakout(n: int = 65):
    """A clean momentum breakout: flat ~100 then a gentle 5-session ramp to a fresh high,
    with today's volume spiking above the baseline. Passes all Stage-1 gates."""
    closes = [100.0] * (n - 5) + [101.0, 102.0, 103.0, 104.0, 105.0]
    volumes = [1000.0] * (n - 1) + [2500.0]
    return _dates(n), closes, volumes


def _positive_insti(dates, foreign=10000.0, trust=5000.0):
    """Strong 外資 + 投信 accumulation on every session."""
    return {d: (foreign, trust) for d in dates}


# --------------------------------------------------------------------------- #
# Universe filter
# --------------------------------------------------------------------------- #
def test_universe_filter():
    assert sr.passes_universe("2330") is True
    assert sr.passes_universe("1234") is True
    assert sr.passes_universe("2330.TW") is True   # suffix tolerated
    assert sr.passes_universe("0050") is False     # ETF (starts 00)
    assert sr.passes_universe("00878") is False    # 5 digits / ETF
    assert sr.passes_universe("2330A") is False     # warrant (letter)
    assert sr.passes_universe("233") is False       # not 4 digits
    assert sr.passes_universe("") is False


# --------------------------------------------------------------------------- #
# Stage 1 + flags (pure)
# --------------------------------------------------------------------------- #
def test_clean_breakout_passes_and_scores():
    dates, closes, volumes = _clean_breakout()
    m = sr.compute_stage1_metrics(dates, closes, volumes, _positive_insti(dates))
    assert m is not None
    assert m["is_60d_high"] is True            # today is the 60-session max
    assert m["close_ma20"] > 1.0 and m["close_ma60"] > 1.0
    assert m["vol_mult"] > sr.VOL_MULT_MIN
    assert m["institution_raw"] > 0

    m["ticker"] = "2330"
    scored = sr.score_pool([m])
    assert scored[0]["rank"] == 1
    assert isinstance(scored[0]["final_score"], float)


def test_overheated_name_filtered():
    # Same shape but a +25% 5-session jump trips the overheated hard-filter.
    dates = _dates(65)
    closes = [100.0] * 60 + [105.0, 110.0, 115.0, 120.0, 125.0]
    volumes = [1000.0] * 64 + [2500.0]
    assert sr.compute_stage1_metrics(dates, closes, volumes, _positive_insti(dates)) is None


def test_below_ma_name_filtered():
    # Downtrend: today sits below both moving averages -> dropped at Stage 1.
    dates = _dates(65)
    closes = [120.0] * 60 + [110.0, 108.0, 106.0, 104.0, 102.0]
    volumes = [1000.0] * 64 + [5000.0]
    assert sr.compute_stage1_metrics(dates, closes, volumes, _positive_insti(dates)) is None


def test_flags_not_60d_high_and_not_crowded():
    # A single spike WITHIN the trailing 60-session window sits above today, so
    # today is a 20d high but NOT a 60d high, and price_pos_60d lands near the
    # bottom of the 60d range (not crowded). The spike is placed at index 5 so it
    # falls inside closes[-60:] (the last 60 of 65 sessions = indices 5..64).
    dates = _dates(65)
    closes = [100.0] * 5 + [300.0] + [100.0] * 54 + [101.0, 102.0, 103.0, 104.0, 105.0]
    volumes = [1000.0] * 64 + [2500.0]
    m = sr.compute_stage1_metrics(dates, closes, volumes, _positive_insti(dates))
    assert m is not None
    assert m["is_60d_high"] is False
    assert m["crowded"] is False
    assert m["price_pos_60d"] < sr.CROWDED_THRESHOLD


def test_null_institutional_treated_as_zero():
    dates, closes, volumes = _clean_breakout()
    # No institutional rows at all -> institution_raw == 0, still passes Stage 1.
    m = sr.compute_stage1_metrics(dates, closes, volumes, {})
    assert m is not None
    assert m["institution_raw"] == 0.0


def test_scoring_ranks_by_final_score():
    # Three synthetic passers with strictly increasing momentum + institution.
    pool = []
    for i, tk in enumerate(["AAAA", "BBBB", "CCCC"]):
        pool.append({
            "ticker": tk,
            "close_ma20": 1.0 + 0.1 * i,
            "close_ma60": 1.0 + 0.1 * i,
            "vol_mult": 2.0 + i,
            "institution_raw": 10.0 * i,
        })
    scored = sr.score_pool(pool)
    by_ticker = {p["ticker"]: p for p in scored}
    assert by_ticker["CCCC"]["rank"] == 1   # highest on every input
    assert by_ticker["AAAA"]["rank"] == 3
    assert by_ticker["CCCC"]["final_score"] >= by_ticker["BBBB"]["final_score"] >= by_ticker["AAAA"]["final_score"]


def test_insufficient_history_returns_none():
    dates = _dates(30)
    closes = [100.0] * 30
    volumes = [1000.0] * 30
    assert sr.compute_stage1_metrics(dates, closes, volumes, {}) is None


# --------------------------------------------------------------------------- #
# DB round trip + endpoint
# --------------------------------------------------------------------------- #
@pytest.fixture()
def screener_db():
    """Fresh SQLite engine bound to a temp file, tables created, internal key set."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    prev_engine, prev_session = pg.engine, pg.SessionLocal
    prev_use_pg, prev_path = settings.use_postgres, settings.database_path
    prev_key = settings.internal_api_key

    settings.use_postgres = False
    settings.database_path = path
    settings.internal_api_key = "test-secret-key"
    pg.engine = None
    pg.SessionLocal = None
    pg.init_engine()
    # Register models on Base + create tables.
    from src.database import models  # noqa: F401
    pg.create_all_tables()

    try:
        yield
    finally:
        pg.engine, pg.SessionLocal = prev_engine, prev_session
        settings.use_postgres = prev_use_pg
        settings.database_path = prev_path
        settings.internal_api_key = prev_key
        if os.path.exists(path):
            os.unlink(path)


def _seed(ticker, dates, closes, volumes, insti=None):
    from src.database.models import StockDailyOHLC, StockInstitutionalDaily
    for s in pg.get_session():
        for d, c, v in zip(dates, closes, volumes):
            s.add(StockDailyOHLC(ticker=ticker, date=d, close=c, volume=v))
        if insti:
            for d, (fn, tn) in insti.items():
                s.add(StockInstitutionalDaily(ticker=ticker, date=d, foreign_net_shares=fn, trust_net_shares=tn))
        s.commit()
        break


def test_refresh_and_endpoint(screener_db):
    from fastapi.testclient import TestClient
    from src.database.models import ScreenerCandidate
    from src.main import app

    dates, closes, volumes = _clean_breakout()
    # A clean passer with strong accumulation...
    _seed("2330", dates, closes, volumes, _positive_insti(dates))
    # ...and a below-MA name that must be filtered out.
    down = [120.0] * 60 + [110.0, 108.0, 106.0, 104.0, 102.0]
    _seed("2317", dates, down, [1000.0] * 64 + [5000.0], _positive_insti(dates))

    written = sr.refresh_screener_for_date_sync()
    assert written == 1  # only 2330 survives Stage 1

    for s in pg.get_session():
        rows = s.query(ScreenerCandidate).all()
        assert {r.ticker for r in rows} == {"2330"}
        assert rows[0].rank == 1
        assert rows[0].factors and "institution_raw" in rows[0].factors
        break

    client = TestClient(app)
    target = dates[-1]

    # Missing key -> 401
    assert client.get("/api/screener/candidates").status_code == 401
    # Bad key -> 401
    assert client.get("/api/screener/candidates", headers={"X-Internal-Key": "nope"}).status_code == 401

    # Good key -> ranked rows for the latest date
    resp = client.get("/api/screener/candidates", headers={"X-Internal-Key": "test-secret-key"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == target
    assert body["count"] == 1
    cand = body["candidates"][0]
    assert cand["ticker"] == "2330"
    assert cand["rank"] == 1
    assert cand["is_60d_high"] is True
