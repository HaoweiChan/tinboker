"""Unit tests for the TKB-001 mention endpoints (routers/mentions.py).

Endpoints are called directly with get_session monkeypatched onto an
in-memory SQLite session; the cdn cache decorator returns a JSONResponse,
so assertions parse the response body.
"""

import asyncio
import json
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.routers.mentions as api
from src.database.models import (
    ContentMention,
    SectorPerformanceSnapshot,
    StockDailyClose,
    TickerPerformanceSnapshot,
)


@pytest.fixture
def session(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    for model in (ContentMention, TickerPerformanceSnapshot, SectorPerformanceSnapshot, StockDailyClose):
        model.__table__.create(bind=engine)
    db = sessionmaker(bind=engine)()

    def _gen():
        yield db

    monkeypatch.setattr(api, "get_session", _gen)
    yield db
    db.close()


def _call(coro) -> dict:
    response = asyncio.run(coro)
    return json.loads(response.body)


def _seed_ticker_mention(db, episode_id="ep1", ticker="2330", with_snapshot=True):
    m = ContentMention(
        mention_key=f"{episode_id}:ticker:{ticker}", episode_id=episode_id,
        podcaster="Gooaye 股癌", mention_type="ticker", ticker=ticker, market="TW",
        mentioned_at=datetime(2026, 6, 1, 8, 0), confidence=0.9,
        extraction_method="pipeline_llm", sentiment_label="BULLISH", thesis="測試論點",
    )
    db.add(m)
    db.commit()
    if with_snapshot:
        db.add(TickerPerformanceSnapshot(
            mention_id=m.id, ticker=ticker, mention_date="2026-06-01",
            baseline_close=100.0, r1d=1.0, r5d=5.0, r20d=None, r60d=None,
        ))
        db.commit()
    return m


def _seed_sector_mention(db, episode_id="ep1", exposure_id="sector_semi"):
    m = ContentMention(
        mention_key=f"{episode_id}:sector:{exposure_id}", episode_id=episode_id,
        podcaster="Gooaye 股癌", mention_type="sector", exposure_id=exposure_id,
        display_name="半導體", mentioned_at=datetime(2026, 6, 1, 8, 0),
        confidence=1.0, extraction_method="alias_match",
        payload={"members": ["2330", "2454"]},
    )
    db.add(m)
    db.commit()
    db.add(SectorPerformanceSnapshot(
        mention_id=m.id, exposure_id=exposure_id, mention_date="2026-06-01",
        member_count=2, r1d=15.0, r5d=None, r20d=None, r60d=None,
    ))
    db.commit()
    return m


def test_ticker_mentions_endpoint(session):
    _seed_ticker_mention(session)
    body = _call(api.get_ticker_mentions("2330.TW", limit=50))

    assert body["ticker"] == "2330"
    assert body["disclaimer"] == api.DISCLAIMER
    assert len(body["mentions"]) == 1
    m = body["mentions"][0]
    assert m["episode_id"] == "ep1"
    assert m["confidence"] == 0.9
    assert m["extraction_method"] == "pipeline_llm"
    assert m["performance"]["baseline_close"] == 100.0
    assert m["performance"]["r1d"] == 1.0
    assert m["performance"]["r20d"] is None  # unelapsed window serialises as null


def test_ticker_mentions_without_snapshot(session):
    _seed_ticker_mention(session, with_snapshot=False)
    body = _call(api.get_ticker_mentions("2330", limit=50))
    assert body["mentions"][0]["performance"] is None


def test_ticker_mentions_empty(session):
    body = _call(api.get_ticker_mentions("9999", limit=50))
    assert body["mentions"] == []
    assert body["disclaimer"]  # disclaimer present even when empty


def test_sector_mentions_endpoint(session):
    _seed_sector_mention(session)
    body = _call(api.get_sector_mentions("sector_semi", limit=50))

    assert body["exposure_id"] == "sector_semi"
    assert body["disclaimer"] == api.DISCLAIMER
    m = body["mentions"][0]
    assert m["display_name"] == "半導體"
    assert m["extraction_method"] == "alias_match"
    assert m["performance"]["r1d"] == 15.0
    assert m["performance"]["member_count"] == 2


def test_episode_mentions_endpoint(session):
    _seed_ticker_mention(session)
    _seed_sector_mention(session)
    body = _call(api.get_episode_mentions("ep1"))

    assert body["episode_id"] == "ep1"
    assert body["disclaimer"] == api.DISCLAIMER
    assert len(body["ticker_mentions"]) == 1
    assert len(body["sector_mentions"]) == 1
    assert body["ticker_mentions"][0]["ticker"] == "2330"
    assert body["sector_mentions"][0]["exposure_id"] == "sector_semi"


def test_episode_mentions_empty(session):
    body = _call(api.get_episode_mentions("nope"))
    assert body["ticker_mentions"] == []
    assert body["sector_mentions"] == []
    assert body["disclaimer"]
