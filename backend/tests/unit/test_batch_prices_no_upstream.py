"""One cold /stock/NVDA page load must not fan out to Massive (2026-09-09 dev 429 storm).

The page issues two ``/batch-prices`` GETs (~90 tickers each) and one
``/batch-prices-since``; each cold US ticker used to cost 5-6 Massive SDK calls
(details, snapshot, aggregates, income statements, ratios [, daily range]) — ~1,450
calls per page view on a ~5/min budget, and the resulting 429s broke unrelated
endpoints (a 1W chart fetch 404'd). Batch routes now read the warm Postgres tables +
Redis only.
"""
import collections
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import src.database.models as models
import src.services.massive_service as m
from src.database import postgres

US = ["NVDA", "INTU"] + [f"C{chr(65 + i // 26)}{chr(65 + i % 26)}" for i in range(88)]  # 90 US-shaped


@pytest.fixture()
def warm_db(monkeypatch, tmp_path):
    """NVDA warm in stock_daily_closes; INTU only in stock_daily_ohlc (the tables drift).

    File-backed SQLite with a normal pool: the routes fan ``asyncio.to_thread`` reads out
    per ticker, and the in-memory StaticPool's single shared connection silently returns
    empty rows under that concurrency (7/90 in a probe) — a harness artifact, so give each
    thread its own connection like Postgres does.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{tmp_path / 'warm.db'}", connect_args={"check_same_thread": False})
    postgres.Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(postgres, "engine", engine)
    monkeypatch.setattr(postgres, "SessionLocal", sessionmaker(autocommit=False, autoflush=False, bind=engine))
    s = postgres.SessionLocal()
    s.add_all([
        models.StockDailyClose(ticker="NVDA", date="2026-09-05", close=100.0),
        models.StockDailyClose(ticker="NVDA", date="2026-09-08", close=110.0),
        models.StockDailyOHLC(ticker="INTU", date="2026-09-03", close=50.0, source=""),
        models.StockDailyOHLC(ticker="INTU", date="2026-09-04", close=55.0, source=""),
    ])
    s.commit()
    s.close()


@pytest.fixture()
def massive_calls(monkeypatch):
    """Route every Massive SDK call to a counter (details succeed, everything else empty)."""
    calls = collections.Counter()

    class FakeClient:
        def __getattr__(self, name):
            def _call(*a, **k):
                calls[name] += 1
                if name == "get_ticker_details":
                    return SimpleNamespace(ticker="NVDA", name="NVIDIA", market_cap=1, description="",
                                           currency_name="USD", branding=None)
                return []
            return _call

    monkeypatch.setattr(m.MassiveAPIService, "client", property(lambda self: FakeClient()))
    monkeypatch.setattr(m.MassiveAPIService, "_check_client", lambda self: None)
    return calls


@pytest.fixture()
def client(warm_db, massive_calls, monkeypatch):
    import src.routers.stock as stock

    async def _no_cache(key):
        return None

    async def _no_set(key, value, ttl=0):
        return False

    monkeypatch.setattr(stock, "cache_get", _no_cache)
    monkeypatch.setattr(stock, "cache_set", _no_set)
    from src.main import app
    return TestClient(app)


def _freeze_today(monkeypatch):
    """The warm-close window and since's 'today' are anchored on utcnow — pin it in both
    modules (the reader lives in stock_close_refresh, the route maths in the router)."""
    import src.routers.stock as stock
    import src.services.stock_close_refresh as close_refresh
    from datetime import datetime as _dt

    class _Now(_dt):
        @classmethod
        def utcnow(cls):
            return _dt(2026, 9, 9)

    monkeypatch.setattr(stock, "datetime", _Now)
    monkeypatch.setattr(close_refresh, "datetime", _Now)


def test_batch_prices_reads_both_warm_tables_and_never_calls_massive(client, massive_calls, monkeypatch):
    _freeze_today(monkeypatch)
    r = client.get("/api/stocks/batch-prices", params={"tickers": ",".join(US)})
    assert r.status_code == 200
    body = r.json()
    assert body["NVDA"] == 10.0            # stock_daily_closes
    assert body["INTU"] == 10.0            # stock_daily_ohlc only
    assert all(body[t] is None for t in US[2:])  # cold = cheap miss
    assert sum(massive_calls.values()) == 0, dict(massive_calls)


def test_batch_prices_since_never_calls_massive(client, massive_calls, monkeypatch):
    _freeze_today(monkeypatch)
    items = [{"ticker": t, "reference_ms": 1788566400000} for t in US]  # 2026-09-05 UTC
    r = client.post("/api/stocks/batch-prices-since", json={"items": items})
    assert r.status_code == 200
    body = r.json()
    assert body["NVDA"] == 10.0            # 100 on 09-05 -> 110 latest
    assert body["CAA"] is None
    assert sum(massive_calls.values()) == 0, dict(massive_calls)
