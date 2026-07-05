"""M3: /topics 三大法人 net-flow windows are computed from stock_institutional_daily
(Postgres) × latest close, not FinMind. Hermetic — seeds known net-share rows + a close
and checks the trailing-window NT$ sums and the foreign/total split.
"""

import os
import tempfile
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.database.models  # noqa: F401 — register tables on Base.metadata
import src.services.podcast as podcast_mod
from src.database.models import StockDailyOHLC, StockInstitutionalDaily
from src.database.postgres import Base
from src.services.podcast import PodcastService


@pytest.fixture()
def svc(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(podcast_mod, "get_session",
                        lambda: iter([Session()]))  # one session per call, GC-closed

    today = datetime.utcnow().date()

    def d(delta):
        return (today - timedelta(days=delta)).isoformat()

    s = Session()
    # latest close = 1000 (so NT$ = net_shares × 1000)
    s.add(StockDailyOHLC(ticker="2330", date=d(0), close=1000.0, trading_value=0.0, source="twse"))
    # institutional net shares across three days
    rows = [
        (d(0), 60.0, 100.0),    # today
        (d(3), 30.0, 50.0),     # inside 5d (cutoff today-4), outside 1d
        (d(15), 10.0, 20.0),    # inside 20d (cutoff today-19), outside 5d
    ]
    for dt, fn, tn in rows:
        s.add(StockInstitutionalDaily(ticker="2330", date=dt, foreign_net_shares=fn,
                                      total_net_shares=tn, source="twse"))
    s.commit()
    s.close()

    yield PodcastService.__new__(PodcastService)
    engine.dispose()
    os.unlink(path)


def test_institutional_windows_nt_dollars(svc):
    out = svc._read_tw_institutional_net_windows(["2330"], windows=(1, 5, 20))
    # total net shares × close(1000): 1d=100, 5d=150, 20d=170
    assert out["total"]["1"]["2330"] == 100_000.0
    assert out["total"]["5"]["2330"] == 150_000.0
    assert out["total"]["20"]["2330"] == 170_000.0
    # foreign: 1d=60, 5d=90, 20d=100
    assert out["foreign"]["1"]["2330"] == 60_000.0
    assert out["foreign"]["5"]["2330"] == 90_000.0
    assert out["foreign"]["20"]["2330"] == 100_000.0


def test_no_close_means_skipped(svc, monkeypatch):
    # A ticker with institutional rows but no OHLC close contributes nothing (can't value it).
    out = svc._read_tw_institutional_net_windows(["9999"], windows=(1, 5, 20))
    assert out == {"total": {"1": {}, "5": {}, "20": {}},
                   "foreign": {"1": {}, "5": {}, "20": {}}}
