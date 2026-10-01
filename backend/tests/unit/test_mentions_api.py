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
    StockTranslation,
    TickerPerformanceSnapshot,
)


@pytest.fixture
def session(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    for model in (ContentMention, TickerPerformanceSnapshot, SectorPerformanceSnapshot, StockDailyClose, StockTranslation):
        model.__table__.create(bind=engine)
    db = sessionmaker(bind=engine)()

    def _gen():
        yield db

    monkeypatch.setattr(api, "get_session", _gen)
    # Release roster: None = no language scope, so these tests see every seeded row.
    # test_ticker_mentions_respects_release_roster overrides it.
    monkeypatch.setattr(api.podcast_service, "_allowed_podcast_names", _roster(None))
    yield db
    db.close()


def _roster(names):
    async def _allowed():
        return names
    return _allowed


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


def test_ticker_mentions_respects_release_roster(session, monkeypatch):
    _seed_ticker_mention(session, episode_id="tw", ticker="2330")
    m = _seed_ticker_mention(session, episode_id="en", ticker="2330", with_snapshot=False)
    m.podcaster = "CNBC's Fast Money"
    session.commit()
    monkeypatch.setattr(api.podcast_service, "_allowed_podcast_names", _roster(frozenset({"Gooaye 股癌"})))
    body = _call(api.get_ticker_mentions("2330", limit=50))
    assert [x["episode_id"] for x in body["mentions"]] == ["tw"]
    monkeypatch.setattr(api.podcast_service, "_allowed_podcast_names", _roster(frozenset()))
    assert _call(api.get_ticker_mentions("2330", limit=50))["mentions"] == []  # fail closed


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


# ── /episodes/{id}/cross-show ────────────────────────────────────────────────

def _mention(db, episode_id, show, ticker, label, when, name=None):
    db.add(ContentMention(
        mention_key=f"{episode_id}:ticker:{ticker}", episode_id=episode_id, podcaster=show,
        mention_type="ticker", ticker=ticker, display_name=name, market="TW", mentioned_at=when,
        confidence=0.9, extraction_method="pipeline_llm", sentiment_label=label,
    ))
    db.commit()


def test_cross_show_relation_names_how_the_episode_sits_against_the_others():
    r = api.cross_show_relation
    assert r("BULLISH", 0, 0, 0) == "alone"
    assert r("BULLISH", 6, 2, 2) == "aligned"
    assert r("BEARISH", 6, 2, 2) == "opposite"
    assert r("NEUTRAL", 6, 2, 2) == "reserved"
    assert r(None, 6, 2, 2) == "reserved"
    assert r("BULLISH", 5, 0, 5) == "split"       # nobody holds 60%
    assert r("BULLISH", 1, 8, 1) == "firmer"      # the others sit on the fence
    assert r("NEUTRAL", 1, 8, 1) == "aligned"


def test_cross_show_counts_other_shows_inside_the_window_before_the_episode(session):
    aired = datetime(2026, 9, 20, 3, 0)
    # Names come from the translation table; the mention's own display_name is the fallback.
    session.add(StockTranslation(ticker="2330", market="TW", name_zh_tw="台積電", name_en="TSMC"))
    session.commit()
    _mention(session, "ep", "股癌", "2330", "BULLISH", aired)
    _mention(session, "ep", "股癌", "3037", "BEARISH", aired, name="欣興")
    _mention(session, "ep", "股癌", "6981", "NEUTRAL", aired)
    # Other shows on 2330: two bullish, one of them later the same day.
    _mention(session, "a1", "財經一路發", "2330", "STRONG_BULLISH", datetime(2026, 9, 10, 1, 0))
    _mention(session, "b1", "財報狗", "2330", "BULLISH", datetime(2026, 9, 20, 22, 0))
    # 3037: the others lean bullish, this episode is bearish.
    _mention(session, "a2", "財經一路發", "3037", "BULLISH", datetime(2026, 9, 15, 1, 0))
    _mention(session, "a3", "財經一路發", "3037", "BULLISH", datetime(2026, 9, 16, 1, 0))
    # Not second opinions: the same show, a mention after the release day, one too old.
    _mention(session, "old-own", "股癌", "2330", "BEARISH", datetime(2026, 9, 12, 3, 0))
    _mention(session, "later", "M觀點", "2330", "BEARISH", datetime(2026, 9, 21, 9, 0))
    _mention(session, "ancient", "M觀點", "2330", "BEARISH", datetime(2026, 8, 1, 9, 0))

    body = _call(api.get_episode_cross_show("ep"))

    assert body["podcaster"] == "股癌" and body["as_of"] == "2026-09-20" and body["window_days"] == 30
    assert body["shows_in_window"] == 3  # 股癌, 財經一路發, 財報狗 — M觀點 is outside the window
    by = {r["ticker"]: r for r in body["rows"]}
    assert by["2330"] == {
        "ticker": "2330", "name": "台積電", "stance": "BULLISH",
        "others": {"shows": 2, "mentions": 2, "bull": 2, "neutral": 0, "bear": 0}, "relation": "aligned",
    }
    assert by["3037"]["others"] == {"shows": 1, "mentions": 2, "bull": 2, "neutral": 0, "bear": 0}
    assert by["3037"]["name"] == "欣興" and by["3037"]["relation"] == "opposite"
    assert by["6981"]["relation"] == "alone" and by["6981"]["others"]["shows"] == 0
    # Most-discussed elsewhere first.
    assert [r["ticker"] for r in body["rows"]] == ["2330", "3037", "6981"]
    assert "並非投資建議" in body["disclaimer"]


def test_cross_show_is_empty_for_an_episode_with_no_ticker_mentions(session):
    body = _call(api.get_episode_cross_show("nope"))
    assert body["rows"] == [] and body["shows_in_window"] == 0


def test_cross_show_respects_the_release_roster(session, monkeypatch):
    aired = datetime(2026, 9, 20, 3, 0)
    _mention(session, "ep", "股癌", "2330", "BULLISH", aired)
    _mention(session, "en1", "Some English Show", "2330", "BEARISH", datetime(2026, 9, 18, 3, 0))
    monkeypatch.setattr(api.podcast_service, "_allowed_podcast_names", _roster(frozenset({"股癌"})))

    body = _call(api.get_episode_cross_show("ep"))

    assert body["rows"][0]["relation"] == "alone" and body["shows_in_window"] == 1

