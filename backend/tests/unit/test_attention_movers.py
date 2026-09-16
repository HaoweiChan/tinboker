"""聲量水位 movers: the week's tickers at their own-year high / low, state only."""

import asyncio
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.database.models import ContentMention, StockTranslation
from src.services import attention


@pytest.fixture
def db(monkeypatch):
    # attention_movers runs its query in a worker thread: share one connection across threads.
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    for model in (ContentMention, StockTranslation):
        model.__table__.create(bind=engine)
    session = sessionmaker(bind=engine)()

    def _gen():
        yield session

    monkeypatch.setattr(attention, "get_session", _gen)
    monkeypatch.setattr("src.services.paid_weekly.get_session", _gen, raising=False)
    # Fixtures below use one show and names that appear only in-week; both floors have their own test.
    monkeypatch.setattr(attention, "MOVER_MIN_SHOWS", 1)
    monkeypatch.setattr(attention, "MIN_MENTION_DAYS", 1)
    yield session
    session.close()


def _mention(db, ticker, day, podcaster="Gooaye 股癌", n=1):
    for k in range(n):
        db.add(ContentMention(
            mention_key=f"{ticker}:{day}:{podcaster}:{k}", episode_id=f"ep-{day}-{k}", podcaster=podcaster,
            mention_type="ticker", ticker=ticker, market="TW",
            mentioned_at=datetime.combine(day, datetime.min.time()) + timedelta(hours=8), confidence=0.9,
            extraction_method="pipeline_llm", sentiment_label="BULLISH", thesis="t",
        ))
    db.commit()


def test_movers_pick_own_year_highs_and_lows_from_the_weeks_mentions(db, monkeypatch):
    # 2026-W37 = 2026-09-07..13. Thirty filler tickers make a market broad enough that one
    # name spiking does not move everyone else's share (a three-ticker market would).
    # HOT is silent all year and explodes this week; COLD was loud all year, goes quiet,
    # and gets one mention this week at its own low.
    days = [date(2026, 9, 13) - timedelta(days=i) for i in range(400)][::-1]
    for idx, d in enumerate(days):
        for k in range(30):
            _mention(db, f"FILL{k:02d}", d, n=(idx + k) % 3 + 1)
        if d < date(2026, 9, 1):
            _mention(db, "COLD", d, n=4)
    for d in days[-5:]:
        _mention(db, "HOT", d, n=8)
    _mention(db, "COLD", date(2026, 9, 9), n=1)
    db.add(StockTranslation(ticker="HOT", market="TW", name_zh_tw="熱股", name_en="Hot", aliases=[]))
    db.commit()

    # The periodic filler pattern parks several fillers at their own low on the last day
    # too; lift the cap so the assertion is about COLD's state, not its rank among them.
    monkeypatch.setattr(attention, "MOVER_LIMIT", 100)
    out = asyncio.run(attention.attention_movers("2026-W37", allowed=None))
    assert out["start"] == "2026-09-07" and out["end"] == "2026-09-13"
    assert [r["ticker"] for r in out["high"]] == ["HOT"]
    assert out["high"][0]["name"] == "熱股" and out["high"][0]["level"] >= 90 and out["high"][0]["shows"] == 1
    assert "COLD" in [r["ticker"] for r in out["low"]]
    cold = next(r for r in out["low"] if r["ticker"] == "COLD")
    assert cold["level"] <= 10 and cold["mentions"] == 1
    assert not any(r["ticker"].startswith("FILL") for r in out["high"])
    assert set(out["high"][0]) == {"ticker", "name", "level", "mentions", "shows"}  # no returns, no raw share
    assert out["as_of"] == "2026-09-13"


def test_movers_respect_the_roster(db):
    days = [date(2026, 9, 13) - timedelta(days=i) for i in range(200)][::-1]
    for idx, d in enumerate(days):
        for k in range(10):
            _mention(db, f"FILL{k:02d}", d, n=(idx + k) % 3 + 1)
    for d in days[-4:]:
        _mention(db, "EN", d, podcaster="CNBC's Fast Money", n=5)
    assert [r["ticker"] for r in asyncio.run(attention.attention_movers("2026-W37", allowed=None))["high"]] == ["EN"]
    assert asyncio.run(attention.attention_movers("2026-W37", allowed=frozenset({"Gooaye 股癌"})))["high"] == []


def test_movers_on_a_week_in_progress_measure_the_latest_day_and_say_so(db):
    # Data stops on Wednesday 2026-09-09; a run on that week must not measure an empty Sunday.
    days = [date(2026, 9, 9) - timedelta(days=i) for i in range(200)][::-1]
    for idx, d in enumerate(days):
        for k in range(10):
            _mention(db, f"FILL{k:02d}", d, n=(idx + k) % 3 + 1)
    for d in days[-3:]:
        _mention(db, "HOT", d, n=6)
    out = asyncio.run(attention.attention_movers("2026-W37", allowed=None))
    assert out["as_of"] == "2026-09-09" and out["end"] == "2026-09-13"
    assert [r["ticker"] for r in out["high"]] == ["HOT"]


def test_movers_need_two_shows_behind_a_state(db, monkeypatch):
    # One show saying a thin-history name once ranks it at 100; that is a mention, not a state.
    monkeypatch.setattr(attention, "MOVER_MIN_SHOWS", 2)
    days = [date(2026, 9, 13) - timedelta(days=i) for i in range(200)][::-1]
    for idx, d in enumerate(days):
        for k in range(10):
            _mention(db, f"FILL{k:02d}", d, n=(idx + k) % 3 + 1)
    _mention(db, "ONCE", date(2026, 9, 10), n=1)
    for d in days[-3:]:
        _mention(db, "TWO", d, n=4)
        _mention(db, "TWO", d, podcaster="財報狗", n=1)
    assert [r["ticker"] for r in asyncio.run(attention.attention_movers("2026-W37", allowed=None))["high"]] == ["TWO"]


def test_movers_rank_breadth_first_at_the_saturated_top(db, monkeypatch):
    # Two names both at level ≥ 99: the one four shows raised ten times leads the one a
    # single pair said once — at the top the level carries no order, breadth does.
    monkeypatch.setattr(attention, "MOVER_MIN_SHOWS", 1)
    days = [date(2026, 9, 13) - timedelta(days=i) for i in range(200)][::-1]
    for idx, d in enumerate(days):
        for k in range(10):
            _mention(db, f"FILL{k:02d}", d, n=(idx + k) % 3 + 1)
    for d in days[-3:]:
        for show in ("Gooaye 股癌", "財報狗", "兆華與股惑仔", "財經一路發"):
            _mention(db, "BROAD", d, podcaster=show, n=1)
    for d in days[-2:]:
        _mention(db, "THIN", d, n=6)
        _mention(db, "THIN", d, podcaster="財報狗", n=6)
    out = asyncio.run(attention.attention_movers("2026-W37", allowed=None))
    assert [r["ticker"] for r in out["high"]][:2] == ["BROAD", "THIN"]
