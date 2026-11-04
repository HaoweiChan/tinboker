"""M2: /topics TW trading-value windows are computed from stock_daily_ohlc (Postgres),
not FinMind. Hermetic — a temp-file sqlite seeded with known daily 成交金額 rows, so a
regression in the cutoff math or the FinMind→DB source swap fails here.
"""

import os
import tempfile
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.database.models  # noqa: F401 — registers all tables on Base.metadata
import src.services.podcast as podcast_mod
from src.database.models import StockDailyOHLC
from src.database.postgres import Base
from src.services.podcast import PodcastService


def _day(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()


@pytest.fixture()
def svc_with_rows(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")  # file (not :memory:) so sessions share it
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    def fake_get_session():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    monkeypatch.setattr(podcast_mod, "get_session", fake_get_session)

    # Dates are relative to today because the query first prefilters at max window +
    # 20 days; fixed dates would eventually age out. Day 32 stays just beyond the 30d
    # cutoff while remaining inside both the prefilter and the 90d window.
    rows = [
        ("2330", _day(0), 100.0), ("2330", _day(1), 50.0),
        ("2330", _day(5), 20.0),   # inside the 7d window (cutoff latest-6)
        ("2330", _day(32), 5.0),   # outside 30d (cutoff latest-29), inside 90d
        ("AAPL", _day(0), 999.0),  # not a TW ticker → filtered out
    ]
    s = Session()
    for t, d, tv in rows:
        s.add(StockDailyOHLC(ticker=t, date=d, close=1.0, trading_value=tv, source="twse"))
    s.commit()
    s.close()

    yield PodcastService.__new__(PodcastService)

    engine.dispose()
    os.unlink(path)


def test_windows_sum_from_db(svc_with_rows):
    out = svc_with_rows._read_tw_trading_value_windows(["2330", "AAPL"], windows=(1, 7, 30, 90))
    assert out["1"]["2330"] == 100.0                       # latest day only
    assert out["7"]["2330"] == 170.0                       # 100 + 50 + 20
    assert out["30"]["2330"] == 170.0                      # the 32-day-old row is excluded
    assert out["90"]["2330"] == 175.0                      # + the 32-day-old row's 5
    assert out["1"]["2330"] <= out["7"]["2330"] <= out["30"]["2330"] <= out["90"]["2330"]
    assert "AAPL" not in out["90"]                         # US ticker filtered before the read


def test_empty_when_no_tw_tickers(svc_with_rows):
    out = svc_with_rows._read_tw_trading_value_windows(["AAPL", "NVDA"])
    assert out == {"1": {}, "7": {}, "30": {}, "90": {}}
