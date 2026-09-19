"""Split guard on the two public return routes (sibling of test_picks_window_returns.py).

`POST /api/stocks/batch-prices-since` and `POST /api/stocks/batch-prices-trailing` read
unadjusted closes, so a return spanning a stock split (6669's real 2026-09-02 3-for-1
showed -60.3% on production) must come back `None`. For each route: a split series is
null, a normal series keeps its hand-computed value, and a failed series read fails
closed instead of serving the un-guarded number.
"""
import asyncio
from datetime import timedelta

import pytest
from sqlalchemy.orm import sessionmaker

import src.database.models as models
import src.routers.stock as stock
import tests.test_picks_window_returns as picks
from tests.test_picks_window_returns import TICKER, _day0, _ms, _seed

warm_db = picks.warm_db  # same file-backed SQLite fixture as the /picks guard tests

SPLIT_AT = 100  # day offset of the 3-for-1: inside d30/d90, before d7's anchor
NORMAL = [100.0 + offset for offset in range(120)]
SPLIT = [300.0 if offset < SPLIT_AT else 100.0 for offset in range(120)]


def _seed_closes(engine, closes: list[float]) -> None:
    """`stock_daily_closes` rows — the table the trailing route builds its windows from."""
    session = sessionmaker(bind=engine)()
    for offset, close in enumerate(closes):
        date = (_day0() + timedelta(days=offset)).strftime("%Y-%m-%d")
        session.add(models.StockDailyClose(ticker=TICKER, date=date, close=close))
    session.commit()
    session.close()


def _fail_series_read(monkeypatch) -> None:
    def _raise(ticker, since):
        raise RuntimeError("simulated DB outage")
    monkeypatch.setattr(stock, "_read_series_since", _raise)


def _since(ref_offset: int):
    item = stock.TickerDatePair(ticker=TICKER, reference_ms=_ms(_day0() + timedelta(days=ref_offset)))
    return asyncio.run(stock.get_batch_prices_since(stock.BatchPricesSinceRequest(items=[item])))[TICKER]


def _trailing() -> dict:
    return asyncio.run(stock.get_batch_prices_trailing(stock.BatchTrailingRequest(tickers=[TICKER])))[TICKER]


# --- /batch-prices-since ---------------------------------------------------------------

def test_since_across_a_split_is_null(warm_db):
    _seed(warm_db, TICKER, _day0(), SPLIT)
    assert _since(50) is None


def test_since_after_the_split_is_scored(warm_db):
    _seed(warm_db, TICKER, _day0(), SPLIT)
    assert _since(SPLIT_AT + 5) == 0.0


def test_since_normal_series_unchanged(warm_db):
    _seed(warm_db, TICKER, _day0(), NORMAL)
    assert _since(50) == pytest.approx(round((219.0 - 150.0) / 150.0 * 100, 2))


def test_since_series_read_failure_is_null(warm_db, monkeypatch):
    _seed(warm_db, TICKER, _day0(), NORMAL)
    _fail_series_read(monkeypatch)
    assert _since(50) is None


# --- /batch-prices-trailing ------------------------------------------------------------

def test_trailing_windows_across_a_split_are_null(warm_db):
    _seed_closes(warm_db, SPLIT)
    res = _trailing()
    assert res["d30"] is None and res["d90"] is None
    assert res["d1"] == 0.0 and res["d7"] == 0.0   # anchored after the split
    assert res["series"] == [100.0] * (120 - SPLIT_AT)  # sparkline starts at the split


def test_trailing_split_on_the_latest_day_nulls_d1(warm_db):
    _seed_closes(warm_db, [300.0] * 119 + [100.0])
    res = _trailing()
    assert [res[k] for k in ("d1", "d7", "d30", "d90")] == [None] * 4


def test_trailing_normal_series_unchanged(warm_db):
    _seed_closes(warm_db, NORMAL)
    res = _trailing()
    assert res["price"] == 219.0
    assert res["d1"] == pytest.approx(round(1 / 218.0 * 100, 2))
    assert res["d7"] == pytest.approx(round(7 / 212.0 * 100, 2))
    assert res["d30"] == pytest.approx(round(30 / 189.0 * 100, 2))
    assert res["d90"] == pytest.approx(round(90 / 129.0 * 100, 2))
    assert res["series"] == NORMAL[-30:]


def test_trailing_series_read_failure_is_null(warm_db, monkeypatch):
    _seed_closes(warm_db, NORMAL)
    _fail_series_read(monkeypatch)
    res = _trailing()
    assert [res[k] for k in ("d1", "d7", "d30", "d90")] == [None] * 4
