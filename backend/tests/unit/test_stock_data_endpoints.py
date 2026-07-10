"""Whole-universe market-data read endpoints (issue #449).

DB-backed round trip through ``GET /api/stocks/daily-ohlc`` and
``/daily-institutional``: market filtering (source set), date-range windowing, the 90-day
cap, and internal-key gating. SQLite fixture mirrors ``test_screener.py``'s ``screener_db``.
"""

import os
import tempfile

import pytest

import src.database.postgres as pg
from src.config import settings

KEY = "test-secret-key"
HDR = {"X-Internal-Key": KEY}


@pytest.fixture()
def data_db():
    """Fresh SQLite engine bound to a temp file, tables created, internal key set."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    prev_engine, prev_session = pg.engine, pg.SessionLocal
    prev_use_pg, prev_path = settings.use_postgres, settings.database_path
    prev_key = settings.internal_api_key

    settings.use_postgres = False
    settings.database_path = path
    settings.internal_api_key = KEY
    pg.engine = None
    pg.SessionLocal = None
    pg.init_engine()
    from src.database import models  # noqa: F401  (register models on Base)
    pg.create_all_tables()

    _seed()
    try:
        yield
    finally:
        pg.engine, pg.SessionLocal = prev_engine, prev_session
        settings.use_postgres = prev_use_pg
        settings.database_path = prev_path
        settings.internal_api_key = prev_key
        if os.path.exists(path):
            os.unlink(path)


def _seed():
    from src.database.models import StockDailyOHLC, StockInstitutionalDaily
    ohlc = [
        # market=us (polygon)
        ("AAPL", "2026-07-08", "polygon", 100.0), ("AAPL", "2026-07-09", "polygon", 101.0),
        ("MSFT", "2026-07-09", "polygon", 200.0),
        ("OLD", "2026-01-01", "polygon", 50.0),   # out of the July window
        # market=tw (twse + tpex)
        ("2330", "2026-07-09", "twse", 1000.0), ("6488", "2026-07-09", "tpex", 500.0),
    ]
    for s in pg.get_session():
        for ticker, date, source, close in ohlc:
            s.add(StockDailyOHLC(ticker=ticker, date=date, source=source, close=close, volume=1234.0, trading_value=close * 1234.0))
        s.add(StockInstitutionalDaily(
            ticker="2330", date="2026-07-09", source="twse",
            foreign_net_shares=10000.0, trust_net_shares=5000.0, total_net_shares=15000.0,
        ))
        s.commit()
        break


def _client():
    from fastapi.testclient import TestClient
    from src.main import app
    return TestClient(app)


# --- auth -------------------------------------------------------------------- #
def test_requires_internal_key(data_db):
    c = _client()
    assert c.get("/api/stocks/daily-ohlc", params={"market": "us", "date": "2026-07-09"}).status_code == 401
    assert c.get(
        "/api/stocks/daily-ohlc", params={"market": "us", "date": "2026-07-09"}, headers={"X-Internal-Key": "nope"}
    ).status_code == 401


# --- daily-ohlc -------------------------------------------------------------- #
def test_us_market_returns_only_polygon_rows(data_db):
    r = _client().get("/api/stocks/daily-ohlc", params={"market": "us", "start": "2026-07-01", "end": "2026-07-31"}, headers=HDR)
    assert r.status_code == 200
    rows = r.json()
    assert {row["ticker"] for row in rows} == {"AAPL", "MSFT"}   # no TW, no out-of-window OLD
    assert all(row["source"] == "polygon" for row in rows)
    # ordered by (date, ticker): 07-08 AAPL, then 07-09 AAPL, MSFT
    assert [(row["ticker"], row["date"]) for row in rows] == [("AAPL", "2026-07-08"), ("AAPL", "2026-07-09"), ("MSFT", "2026-07-09")]
    assert rows[0]["trading_value"] == 100.0 * 1234.0


def test_tw_market_returns_twse_and_tpex(data_db):
    r = _client().get("/api/stocks/daily-ohlc", params={"market": "tw", "date": "2026-07-09"}, headers=HDR)
    assert r.status_code == 200
    assert {row["ticker"] for row in r.json()} == {"2330", "6488"}


def test_date_shorthand_windows_a_single_day(data_db):
    r = _client().get("/api/stocks/daily-ohlc", params={"market": "us", "date": "2026-07-09"}, headers=HDR)
    assert {row["ticker"] for row in r.json()} == {"AAPL", "MSFT"}   # 07-08 AAPL excluded


def test_empty_range_returns_empty_list(data_db):
    r = _client().get("/api/stocks/daily-ohlc", params={"market": "us", "date": "2026-06-01"}, headers=HDR)
    assert r.status_code == 200
    assert r.json() == []


def test_range_over_90_days_rejected(data_db):
    r = _client().get("/api/stocks/daily-ohlc", params={"market": "us", "start": "2026-01-01", "end": "2026-07-01"}, headers=HDR)
    assert r.status_code == 400


def test_unknown_market_rejected(data_db):
    assert _client().get("/api/stocks/daily-ohlc", params={"market": "jp", "date": "2026-07-09"}, headers=HDR).status_code == 400


def test_missing_range_rejected(data_db):
    assert _client().get("/api/stocks/daily-ohlc", params={"market": "us"}, headers=HDR).status_code == 400


# --- daily-institutional ----------------------------------------------------- #
def test_institutional_tw_returns_net_shares(data_db):
    r = _client().get("/api/stocks/daily-institutional", params={"market": "tw", "date": "2026-07-09"}, headers=HDR)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["ticker"] == "2330"
    assert rows[0]["trust_net_shares"] == 5000.0
    assert rows[0]["total_net_shares"] == 15000.0


def test_institutional_us_rejected(data_db):
    assert _client().get("/api/stocks/daily-institutional", params={"market": "us", "date": "2026-07-09"}, headers=HDR).status_code == 400
