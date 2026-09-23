"""Tests for the /picks price-return path (PR 2 of the paid-membership work).

Covers what had no test before:
1. The split guard in `src.routers.stock._window_returns` — `stock_daily_ohlc` holds
   unadjusted closes, so a window spanning a stock split (6669's real 2026-09-02
   3-for-1) must come back `None`, not a fabricated -60%-ish return. Same rule and
   warm tables as `mention_sync.compute_trading_day_returns` (see
   `_resolve_price_break_date`), including the boundary (a break landing exactly on
   a window's own end date) and the fail-closed contract (a series-read error must
   never fall back to serving the un-guarded number).
2. The member gate on `POST /api/stocks/batch-prices-windows` (401 anonymous, 402
   signed-in-but-not-a-member, 200 for a member) — this route now powers the paid
   /picks page.
3. The per-ticker dedup of the split-guard series read in `get_batch_prices_windows`
   — a ticker mentioned by N picks in one request reads its series once, not N times.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.database.models as models
import src.routers.stock as stock
from src.database import postgres
from src.models.user import UserResponse
from src.utils.dependencies import get_current_user

TICKER = "SPLTST"  # alphabetic → infer_market() says US, so a DB miss never fans out to FinMind


@pytest.fixture()
def warm_db(monkeypatch, tmp_path):
    """File-backed SQLite (its own connection, like the prod pool — an in-memory
    StaticPool can silently starve `asyncio.to_thread` reads under concurrency; see
    tests/unit/test_batch_prices_no_upstream.py for the same fixture shape)."""
    engine = create_engine(f"sqlite:///{tmp_path / 'warm.db'}", connect_args={"check_same_thread": False})
    postgres.Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(postgres, "engine", engine)
    monkeypatch.setattr(postgres, "SessionLocal", sessionmaker(autocommit=False, autoflush=False, bind=engine))

    async def _no_cache(key):
        return None

    async def _no_set(key, value, ttl=0):
        return False

    monkeypatch.setattr(stock, "cache_get", _no_cache)
    monkeypatch.setattr(stock, "cache_set", _no_set)
    return engine


def _seed(engine, ticker: str, day0: datetime, closes: list[float]) -> None:
    session = sessionmaker(bind=engine)()
    for offset, close in enumerate(closes):
        date = (day0 + timedelta(days=offset)).strftime("%Y-%m-%d")
        session.add(models.StockDailyOHLC(ticker=ticker, date=date, close=close, source="test"))
    session.commit()
    session.close()


def _day0() -> datetime:
    # Far enough in the past that d7/d30/d90 have all elapsed by "now", regardless
    # of when this test runs; seeded 120 consecutive calendar days from here.
    return datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=120)


def _ms(dt: datetime) -> int:
    """Naive-UTC datetime → Unix ms (inverse of datetime.utcfromtimestamp)."""
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


# --- (a) a split-like break: windows before it keep their value, at/after it are None --

def test_windows_across_a_price_break_are_null_not_fabricated(warm_db):
    day0 = _day0()
    closes = [
        100.0 + offset * 0.5 if offset < 20 else 38.0 + (offset - 20) * 0.05
        for offset in range(120)
    ]
    _seed(warm_db, TICKER, day0, closes)
    # day19 (last pre-break) = 109.5, day20 = 38.0 → ratio 0.347, outside PRICE_BREAK_BAND.

    reference_ms = _ms(day0)
    current_price = closes[-1]  # post-break "latest" close
    res = asyncio.run(stock._window_returns(TICKER, reference_ms, current_price))

    assert res["baseline"] == 100.0
    assert res["d7"] == pytest.approx(3.5)      # day7 = 103.5, entirely before the break
    assert res["d30"] is None                   # day30 is past the break
    assert res["d90"] is None                   # day90 is past the break
    assert res["since"] is None                 # latest close is past the break too


# --- (b) a normal series: values are unchanged vs. a hand-computed number ------------

def test_normal_series_values_match_hand_computed_returns(warm_db):
    day0 = _day0()
    closes = [100.0 + offset * 1.0 for offset in range(120)]  # no break anywhere
    _seed(warm_db, TICKER, day0, closes)

    reference_ms = _ms(day0)
    current_price = closes[-1]
    res = asyncio.run(stock._window_returns(TICKER, reference_ms, current_price))

    assert res["baseline"] == 100.0
    assert res["d7"] == pytest.approx((107.0 - 100.0) / 100.0 * 100)   # 7.0
    assert res["d30"] == pytest.approx((130.0 - 100.0) / 100.0 * 100)  # 30.0
    assert res["d90"] == pytest.approx((190.0 - 100.0) / 100.0 * 100)  # 90.0
    assert res["since"] == pytest.approx((closes[-1] - 100.0) / 100.0 * 100)  # 119.0


# --- an earlier settled window can stay scored even though "since" cannot -----------

def test_since_is_none_while_an_earlier_window_keeps_its_value(warm_db):
    day0 = _day0()
    # Break lands between d7 and d30, so d7 is fully pre-break but "since" (anchored
    # on the latest, post-break close) is not.
    closes = [
        100.0 + offset * 0.5 if offset < 15 else 40.0 + (offset - 15) * 0.05
        for offset in range(120)
    ]
    _seed(warm_db, TICKER, day0, closes)

    res = asyncio.run(stock._window_returns(TICKER, _ms(day0), closes[-1]))
    assert res["d7"] is not None and res["d7"] == pytest.approx(3.5)
    assert res["since"] is None


# --- boundary: a break exactly on a window's own end date nulls that window ---------

def test_break_exactly_on_a_window_end_date_nulls_it(warm_db):
    day0 = _day0()
    # Break lands exactly on day+7 — the d7 window's own resolved end date.
    closes = [
        100.0 + offset * 0.5 if offset < 7 else 38.0 + (offset - 7) * 0.05
        for offset in range(120)
    ]
    _seed(warm_db, TICKER, day0, closes)
    # day6 (last pre-break) = 103.0, day7 = 38.0 → ratio 0.369, outside PRICE_BREAK_BAND.

    res = asyncio.run(stock._window_returns(TICKER, _ms(day0), closes[-1]))
    assert res["baseline"] == 100.0
    assert res["d7"] is None   # the break IS day7's close, not just before/after it
    assert res["d30"] is None
    assert res["d90"] is None


# --- fail-closed: a series-read error must never serve the un-guarded number --------

def test_series_read_failure_yields_all_none_not_the_unguarded_number(warm_db, monkeypatch):
    day0 = _day0()
    closes = [100.0 + offset * 1.0 for offset in range(120)]  # normal series, no break —
    _seed(warm_db, TICKER, day0, closes)                      # would score real numbers if not for the failure

    def _raise(ticker, since):
        raise RuntimeError("simulated DB outage")
    monkeypatch.setattr(stock, "_read_series_since", _raise)

    from src.main import app
    app.dependency_overrides[get_current_user] = lambda: _user(is_member=True)
    try:
        item = {"ticker": TICKER, "reference_ms": _ms(day0)}
        r = _client().post("/api/stocks/batch-prices-windows", json={"items": [item]})
        assert r.status_code == 200
        key = f"{TICKER}:{_ms(day0)}"
        assert r.json()[key] == {"baseline": None, "d7": None, "d30": None, "d90": None, "since": None}
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# --- per-ticker dedup: N picks of one ticker read its series once, not N times ------

def test_series_read_is_deduped_per_ticker_not_per_pick(warm_db, monkeypatch):
    day0 = _day0()
    closes = [100.0 + offset * 1.0 for offset in range(120)]
    _seed(warm_db, TICKER, day0, closes)

    real = stock._read_series_since
    calls: list[tuple[str, str]] = []

    def _counting(ticker, since):
        calls.append((ticker, since))
        return real(ticker, since)
    monkeypatch.setattr(stock, "_read_series_since", _counting)

    from src.main import app
    app.dependency_overrides[get_current_user] = lambda: _user(is_member=True)
    try:
        items = [
            {"ticker": TICKER, "reference_ms": _ms(day0)},
            {"ticker": TICKER, "reference_ms": _ms(day0 + timedelta(days=5))},  # same ticker, another episode
        ]
        r = _client().post("/api/stocks/batch-prices-windows", json={"items": items})
        assert r.status_code == 200
        assert len(calls) == 1  # one shared series read for the ticker, not two
    finally:
        app.dependency_overrides.pop(get_current_user, None)


# --- (c) route-level member gate -----------------------------------------------------

def _client() -> TestClient:
    from src.main import app
    return TestClient(app)


def _user(is_member: bool) -> UserResponse:
    now = datetime.utcnow()
    return UserResponse(
        id="u1", google_id="g1", email="a@b.com", name="Test User", email_verified=True,
        created_at=now, updated_at=now,
        member_until=(now + timedelta(days=1)) if is_member else None,
    )


def test_batch_prices_windows_requires_auth():
    from src.main import app
    app.dependency_overrides.pop(get_current_user, None)
    r = _client().post("/api/stocks/batch-prices-windows", json={"items": []})
    assert r.status_code == 401


def test_batch_prices_windows_402_for_signed_in_non_member():
    from src.main import app
    app.dependency_overrides[get_current_user] = lambda: _user(is_member=False)
    try:
        r = _client().post("/api/stocks/batch-prices-windows", json={"items": []})
        assert r.status_code == 402
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_batch_prices_windows_200_for_member():
    from src.main import app
    app.dependency_overrides[get_current_user] = lambda: _user(is_member=True)
    try:
        r = _client().post("/api/stocks/batch-prices-windows", json={"items": []})
        assert r.status_code == 200
        assert r.json() == {}
    finally:
        app.dependency_overrides.pop(get_current_user, None)
