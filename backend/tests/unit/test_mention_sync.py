"""Unit tests for the TKB-001 mention sync + post-mention window returns."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.services.mention_sync as ms
from src.database.models import (
    ContentMention,
    SectorPerformanceSnapshot,
    StockDailyClose,
    TickerPerformanceSnapshot,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    for model in (ContentMention, TickerPerformanceSnapshot, SectorPerformanceSnapshot, StockDailyClose):
        model.__table__.create(bind=engine)
    db = sessionmaker(bind=engine)()
    yield db
    db.close()


def _seed_closes(db, ticker: str, start: str, closes: list[float]):
    """Insert consecutive weekday closes starting at `start` (YYYY-MM-DD)."""
    day = datetime.strptime(start, "%Y-%m-%d")
    for close in closes:
        while day.weekday() >= 5:  # skip Sat/Sun like real close data
            day += timedelta(days=1)
        db.add(StockDailyClose(ticker=ticker, date=day.strftime("%Y-%m-%d"), close=close))
        day += timedelta(days=1)
    db.commit()


# ── compute_trading_day_returns ──────────────────────────────────────────

def test_window_returns_full(session):
    # Baseline 100 on the mention date, then 61 trading days of +1/day.
    _seed_closes(session, "2330", "2026-01-05", [100.0 + i for i in range(62)])
    out = ms.compute_trading_day_returns(session, "2330", "2026-01-05")
    assert out["baseline_close"] == 100.0
    assert out["r1d"] == pytest.approx(1.0)
    assert out["r5d"] == pytest.approx(5.0)
    assert out["r20d"] == pytest.approx(20.0)
    assert out["r60d"] == pytest.approx(60.0)


def test_window_returns_unelapsed_windows_stay_none(session):
    # Only 3 trading days after the mention -> r5d/r20d/r60d must stay None.
    _seed_closes(session, "NVDA", "2026-01-05", [200.0, 202.0, 204.0, 206.0])
    out = ms.compute_trading_day_returns(session, "NVDA", "2026-01-05")
    assert out["baseline_close"] == 200.0
    assert out["r1d"] == pytest.approx(1.0)
    assert out["r5d"] is None
    assert out["r20d"] is None
    assert out["r60d"] is None


def test_window_returns_weekend_mention_uses_prior_close(session):
    # Mention lands on Sunday 2026-01-11; baseline = Friday 01-09 close.
    _seed_closes(session, "2330", "2026-01-05", [100.0, 101.0, 102.0, 103.0, 110.0, 121.0])
    out = ms.compute_trading_day_returns(session, "2330", "2026-01-11")
    assert out["baseline_close"] == 110.0  # Friday 01-09
    assert out["r1d"] == pytest.approx(10.0)  # Monday 01-12 close 121


def test_window_returns_no_close_data(session):
    out = ms.compute_trading_day_returns(session, "0000", "2026-01-05")
    assert out["baseline_close"] is None
    assert all(out[f"r{n}d"] is None for n in ms.TRADING_WINDOWS)


# ── sync_ticker_mentions ─────────────────────────────────────────────────

def _insight_row(episode_id="gooaye_ep1", ticker="2330.TW", launch="2026-06-01T08:00:00Z"):
    return {
        "episode_id": episode_id,
        "ticker": ticker,
        "podcaster": "Gooaye 股癌",
        "podcast_launch_time": launch,
        "bluf_thesis": "先進製程需求強勁",
        "sentiment_label": "BULLISH",
        "reasons": [{"start_time": "12:30", "title": "CoWoS"}],
    }


def test_sync_ticker_mentions_inserts_and_is_idempotent(session, monkeypatch):
    monkeypatch.setattr(ms, "_fetch_recent_insight_rows", lambda days: [_insight_row()])
    assert ms.sync_ticker_mentions(session) == 1
    assert ms.sync_ticker_mentions(session) == 0  # same key -> no dup

    m = session.query(ContentMention).one()
    assert m.ticker == "2330"  # .TW stripped
    assert m.market == "TW"
    assert m.mention_type == "ticker"
    assert m.extraction_method == "pipeline_llm"
    assert m.confidence == ms.LLM_TICKER_CONFIDENCE
    assert m.sentiment_label == "BULLISH"
    assert m.mention_start_s == pytest.approx(750.0)  # "12:30" -> 12*60+30
    assert m.mentioned_at == datetime(2026, 6, 1, 8, 0, 0)


def test_sync_ticker_mentions_skips_incomplete_rows(session, monkeypatch):
    rows = [
        _insight_row(ticker=""),
        _insight_row(episode_id=""),
        {**_insight_row(), "podcast_launch_time": "not-a-date"},
    ]
    monkeypatch.setattr(ms, "_fetch_recent_insight_rows", lambda days: rows)
    assert ms.sync_ticker_mentions(session) == 0


def test_sync_ticker_mentions_us_market(session, monkeypatch):
    monkeypatch.setattr(
        ms, "_fetch_recent_insight_rows",
        lambda days: [_insight_row(episode_id="ep2", ticker="nvda")],
    )
    ms.sync_ticker_mentions(session)
    m = session.query(ContentMention).one()
    assert m.ticker == "NVDA"
    assert m.market == "US"


# ── sync_sector_mentions ─────────────────────────────────────────────────

def test_sync_sector_mentions_inserts_and_is_idempotent(session, monkeypatch):
    record = {
        "episode_id": "gooaye_ep1",
        "podcaster": "Gooaye 股癌",
        "exposure_id": "sector_semiconductor",
        "display_name": "半導體",
        "confidence": 1.0,
        "mentioned_at": datetime.utcnow() - timedelta(days=3),
        "members": ["2330", "2454"],
        "mention_text": "半導體",
    }
    monkeypatch.setattr(ms, "_scan_sector_exposures", lambda: [record])
    assert ms.sync_sector_mentions(session) == 1
    assert ms.sync_sector_mentions(session) == 0

    m = session.query(ContentMention).one()
    assert m.mention_type == "sector"
    assert m.exposure_id == "sector_semiconductor"
    assert m.extraction_method == "alias_match"
    assert m.payload["members"] == ["2330", "2454"]


def test_sync_sector_mentions_dedups_within_one_batch(session, monkeypatch):
    """Prod episodes list the same exposure_id twice; with autoflush off the
    old per-row lookup never saw the first insert and the commit died on the
    unique key — taking every row of the pass with it."""
    record = {
        "episode_id": "ep1", "podcaster": "股癌", "exposure_id": "ai-servers",
        "display_name": "AI 伺服器", "confidence": 0.8,
        "mentioned_at": datetime.utcnow() - timedelta(days=3),
        "members": ["2330", "2382"], "mention_text": "AI 伺服器",
    }
    monkeypatch.setattr(ms, "_scan_sector_exposures", lambda: [record, dict(record)])
    assert ms.sync_sector_mentions(session) == 1
    assert session.query(ContentMention).count() == 1


def test_sync_sector_mentions_respects_lookback(session, monkeypatch):
    record = {
        "episode_id": "old_ep",
        "podcaster": "p",
        "exposure_id": "sector_x",
        "display_name": "X",
        "confidence": 1.0,
        "mentioned_at": datetime.utcnow() - timedelta(days=999),
        "members": [],
        "mention_text": None,
    }
    monkeypatch.setattr(ms, "_scan_sector_exposures", lambda: [record])
    assert ms.sync_sector_mentions(session, days=400) == 0


# ── snapshots ────────────────────────────────────────────────────────────

def test_compute_ticker_snapshots(session, monkeypatch):
    _seed_closes(session, "2330", "2026-01-05", [100.0 + i for i in range(62)])
    session.add(ContentMention(
        mention_key="ep1:ticker:2330", episode_id="ep1", mention_type="ticker",
        ticker="2330", mentioned_at=datetime(2026, 1, 5), confidence=0.9,
        extraction_method="pipeline_llm",
    ))
    session.commit()

    assert ms.compute_ticker_snapshots(session) == 1
    snap = session.query(TickerPerformanceSnapshot).one()
    assert snap.mention_date == "2026-01-05"
    assert snap.baseline_close == 100.0
    assert snap.r1d == pytest.approx(1.0)
    assert snap.r60d == pytest.approx(60.0)

    # Complete snapshot -> second run recomputes nothing.
    assert ms.compute_ticker_snapshots(session) == 0


def test_compute_sector_snapshots_averages_members(session):
    _seed_closes(session, "2330", "2026-01-05", [100.0, 110.0])  # r1d = +10%
    _seed_closes(session, "2454", "2026-01-05", [100.0, 120.0])  # r1d = +20%
    session.add(ContentMention(
        mention_key="ep1:sector:sector_semi", episode_id="ep1", mention_type="sector",
        exposure_id="sector_semi", mentioned_at=datetime(2026, 1, 5), confidence=1.0,
        extraction_method="alias_match", payload={"members": ["2330", "2454", "9999"]},
    ))
    session.commit()

    assert ms.compute_sector_snapshots(session) == 1
    snap = session.query(SectorPerformanceSnapshot).one()
    assert snap.member_count == 2  # 9999 has no close data
    assert snap.r1d == pytest.approx(15.0)
    assert snap.r60d is None  # windows not elapsed
