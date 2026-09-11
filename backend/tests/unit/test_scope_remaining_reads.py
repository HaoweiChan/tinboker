"""The ContentMention readers outside routers/mentions.py honour the release roster:
og's stock card daily counts and the paid weekly's track record."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.routers.og as og
from src.database.models import ContentMention, TickerPerformanceSnapshot
from src.services import paid_weekly as pw

TW = "Gooaye 股癌"
EN = "CNBC's Fast Money"


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    for model in (ContentMention, TickerPerformanceSnapshot):
        model.__table__.create(bind=engine)
    session = sessionmaker(bind=engine)()

    def _gen():
        yield session

    monkeypatch.setattr(og, "get_session", _gen)
    yield session
    session.close()


def _seed(db, episode_id, podcaster, day="2026-08-04"):
    m = ContentMention(
        mention_key=f"{episode_id}:ticker:2330", episode_id=episode_id, podcaster=podcaster,
        mention_type="ticker", ticker="2330", market="TW",
        mentioned_at=datetime.fromisoformat(day + "T08:00:00"), confidence=0.9,
        extraction_method="pipeline_llm", sentiment_label="BULLISH", thesis="t",
    )
    db.add(m)
    db.commit()
    db.add(TickerPerformanceSnapshot(mention_id=m.id, ticker="2330", mention_date=day,
                                     baseline_close=100.0, r1d=1.0, r5d=2.0, r20d=5.0, r60d=None))
    db.commit()


def test_track_record_scores_only_roster_shows(db):
    _seed(db, "tw", TW)
    _seed(db, "en", EN)
    calls = lambda allowed: {c["podcaster"] for c in pw.query_track_record(db, "2026-W32", allowed)["calls"]}  # noqa: E731
    assert calls(None) == {TW, EN}                 # no language scope configured
    assert calls(frozenset({TW})) == {TW}          # roster applied
    assert calls(frozenset()) == set()             # empty roster fails closed


def test_stock_card_daily_counts_only_roster_shows(db):
    _seed(db, "tw", TW)
    _seed(db, "en", EN)
    assert og._daily_mentions("2330", "2026-08-01", None)[0]["n"] == 2
    assert og._daily_mentions("2330", "2026-08-01", frozenset({TW}))[0]["n"] == 1
    assert og._daily_mentions("2330", "2026-08-01", frozenset()) == []
