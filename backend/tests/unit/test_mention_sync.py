"""Unit tests for the TKB-001 mention sync + post-mention window returns."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.services.mention_sync as ms
from src.utils.market import market_date
from src.database.models import (
    ContentMention,
    SectorPerformanceSnapshot,
    StockDailyClose,
    StockDailyOHLC,
    TickerPerformanceSnapshot,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    for model in (ContentMention, TickerPerformanceSnapshot, SectorPerformanceSnapshot,
                  StockDailyClose, StockDailyOHLC):
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


# ── market-local mention date ────────────────────────────────────────────

def test_market_date_tw_late_utc_is_next_taipei_day():
    # 23:30 UTC on the 8th is 07:30 on the 9th in Taipei.
    assert market_date(datetime(2026, 9, 8, 23, 30), "TW") == "2026-09-09"
    assert market_date(datetime(2026, 9, 8, 15, 59), "TW") == "2026-09-08"
    assert market_date(datetime(2026, 9, 8, 16, 0), "TW") == "2026-09-09"


def test_market_date_us_early_utc_is_previous_new_york_day():
    # 01:00 UTC on the 9th is 21:00 EDT on the 8th; 05:00 UTC on Jan 9 is 00:00 EST.
    assert market_date(datetime(2026, 9, 9, 1, 0), "US") == "2026-09-08"
    assert market_date(datetime(2026, 1, 9, 4, 59), "US") == "2026-01-08"
    assert market_date(datetime(2026, 1, 9, 5, 0), "US") == "2026-01-09"


def test_ticker_snapshot_uses_taipei_date_for_tw_mention(session):
    """A 股癌 episode released 23:30 UTC Sun 01-11 (07:30 Mon 01-12 Taipei) must be scored
    from Monday's close, not Friday's."""
    _seed_closes(session, "2330", "2026-01-05", [100.0, 101.0, 102.0, 103.0, 110.0, 121.0, 133.1])
    _mention(session, "2330", datetime(2026, 1, 11, 23, 30), "sun-night")
    assert ms.compute_ticker_snapshots(session) == 1
    snap = session.query(TickerPerformanceSnapshot).one()
    assert snap.mention_date == "2026-01-12"
    assert snap.baseline_close == 121.0  # Monday 01-12, not Friday's 110
    assert snap.r1d == pytest.approx(10.0)


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


def test_sync_ticker_mentions_numeric_start_time_is_ms(session, monkeypatch):
    row = {**_insight_row(), "reasons": [{"start_time": 1575708, "title": "無稀土馬達"}]}
    monkeypatch.setattr(ms, "_fetch_recent_insight_rows", lambda days: [row])
    ms.sync_ticker_mentions(session)
    assert session.query(ContentMention).one().mention_start_s == pytest.approx(1575.708)


def test_sync_ticker_mentions_heals_start_s_of_existing_rows(session, monkeypatch):
    """Rows written before the ms fix hold values 1000x too large; a later
    pass re-sets them from the source without re-inserting."""
    row = {**_insight_row(), "reasons": [{"start_time": 1575708, "title": "x"}]}
    monkeypatch.setattr(ms, "_fetch_recent_insight_rows", lambda days: [row])
    ms.sync_ticker_mentions(session)
    session.query(ContentMention).update({"mention_start_s": 1575708.0})
    session.commit()
    assert ms.sync_ticker_mentions(session) == 0
    assert session.query(ContentMention).one().mention_start_s == pytest.approx(1575.708)
    assert ms.sync_ticker_mentions(session) == 0  # second pass changes nothing


def test_parse_start_s_shapes():
    assert ms._parse_start_s([{"start_time": 1575708}]) == pytest.approx(1575.708)
    assert ms._parse_start_s([{"start_time": "3695725"}]) == pytest.approx(3695.725)  # ms as string
    assert ms._parse_start_s([{"start_time": "00:06:00.233"}]) == pytest.approx(360.233)
    assert ms._parse_start_s([{"start_time": "12:30"}]) == pytest.approx(750.0)
    assert ms._parse_start_s([{"start_time": "n/a"}]) is None
    assert ms._parse_start_s("[]") is None


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


# ── sync_macro_mentions ──────────────────────────────────────────────────

def _macro_record(**kw):
    base = {
        "episode_id": "haojiao_ep1", "podcaster": "游庭皓的財經皓角",
        "mentioned_at": datetime.utcnow() - timedelta(days=2),
        "indicator_id": "US10Y", "display_name": "美債10年期殖利率", "level_quoted": "4.94%",
        "direction_expected": "UP", "claim": "回購反而讓殖利率衝高", "reasons": ["市場不滿回購力道"],
        "implication": "壓抑股市估值", "time_horizon": "SHORT_TERM", "quote": "殖利率直接衝高到4.94了",
        "start_time_s": 1288.08, "confidence": 0.9,
    }
    return {**base, **kw}


def test_sync_macro_mentions_inserts_once_and_keeps_seconds_as_seconds(session, monkeypatch):
    monkeypatch.setattr(ms, "_scan_macro_claims", lambda: [_macro_record(), _macro_record()])
    assert ms.sync_macro_mentions(session) == 1          # same (episode, indicator) twice → one row
    assert ms.sync_macro_mentions(session) == 0

    m = session.query(ContentMention).one()
    assert (m.mention_type, m.exposure_id, m.ticker) == ("macro", "US10Y", None)
    assert m.mention_key == "haojiao_ep1:macro:US10Y"
    assert m.thesis == "回購反而讓殖利率衝高" and m.sentiment_label == "UP"
    assert m.mention_start_s == 1288.08                   # NOT divided by 1000
    assert m.payload["level_quoted"] == "4.94%" and m.payload["quote"].startswith("殖利率")
    assert m.extraction_method == "pipeline_llm"


def test_sync_macro_mentions_respects_lookback_and_a_missing_time(session, monkeypatch):
    old = _macro_record(episode_id="old", mentioned_at=datetime.utcnow() - timedelta(days=999))
    untimed = _macro_record(episode_id="regen", indicator_id="WTI", start_time_s=None)
    monkeypatch.setattr(ms, "_scan_macro_claims", lambda: [old, untimed])
    assert ms.sync_macro_mentions(session, days=400) == 1
    assert session.query(ContentMention).one().mention_start_s is None


def test_scan_keeps_only_indicators_with_a_data_series(monkeypatch):
    from src.services import podcast as podcast_mod

    class _FS:
        def stream_documents_projected(self, collection, fields):
            assert "macro_claims" in fields and "sector_exposures" in fields
            return [
                {"id": "ep1", "podcast_name": "皓角", "released_at_ms": 1789000000000, "macro_claims": [
                    {"indicator_id": "us10y", "claim": "逼近5%"}, {"indicator_id": "BEEF", "claim": "漲七成"},
                    {"indicator_id": "WTI", "claim": "  "}]},
                {"id": "ep2", "retracted_at": "x", "macro_claims": [{"indicator_id": "WTI", "claim": "破百"}]},
            ]

    class _Svc:
        _SECTOR_SCAN_FIELDS = ["id", "podcast_name", "sector_exposures", "released_at_ms", "retracted_at"]
        firestore_service = _FS()

        @staticmethod
        def _dict_release_ms(doc):
            return doc.get("released_at_ms") or 0
    monkeypatch.setattr(podcast_mod, "PodcastService", _Svc)
    ms._scan_episodes.cache_clear()
    try:
        macro = ms._scan_macro_claims()
    finally:
        ms._scan_episodes.cache_clear()
    assert [(r["episode_id"], r["indicator_id"], r["claim"]) for r in macro] == [("ep1", "US10Y", "逼近5%")]


def test_macro_vocab_in_sync():
    """The backend owns the indicator list (it decides what has a data series); the
    pipeline keeps a copy because it cannot import backend code. Drift means the extractor
    emits ids the card 404s on, or never emits ones we can draw."""
    import ast
    import pathlib

    import pytest

    from src.services.macro_data import SERIES
    path = (pathlib.Path(__file__).resolve().parents[3]
            / "pipelines/services/podcast/src/podcast/content_builder/macro_vocab.py")
    if not path.exists():
        pytest.skip("pipelines/ tier not in this checkout")
    tree = ast.parse(path.read_text())
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", "") == "MACRO_SERIES")
    assert set(ast.literal_eval(node.value)) == set(SERIES)


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


# ── backfill: closes from the whole-market OHLC table, needy-mention selection ──

def _seed_ohlc(db, ticker: str, start: str, closes: list[float]):
    day = datetime.strptime(start, "%Y-%m-%d")
    for close in closes:
        while day.weekday() >= 5:
            day += timedelta(days=1)
        db.add(StockDailyOHLC(ticker=ticker, date=day.strftime("%Y-%m-%d"), close=close, source="twse"))
        day += timedelta(days=1)
    db.commit()


def test_window_returns_read_the_whole_market_ohlc_table_too(session):
    """stock_daily_closes is thin before mid-2026; the TWSE/TPEx history lands in
    stock_daily_ohlc. A call with closes only there must still be scorable."""
    _seed_ohlc(session, "2330", "2026-03-02", [100.0, 110.0, 120.0, 130.0, 140.0, 150.0, 160.0])
    out = ms.compute_trading_day_returns(session, "2330", "2026-03-02")
    assert out["baseline_close"] == 100.0
    assert out["r1d"] == 10.0 and out["r5d"] == 50.0


def test_close_only_table_wins_when_both_have_a_date(session):
    _seed_ohlc(session, "2330", "2026-03-02", [100.0, 111.0])
    _seed_closes(session, "2330", "2026-03-02", [100.0, 110.0])
    assert ms.compute_trading_day_returns(session, "2330", "2026-03-02")["r1d"] == 10.0


def _mention(db, ticker: str, when: datetime, key: str) -> ContentMention:
    m = ContentMention(
        mention_key=key, episode_id=key, mention_type="ticker", ticker=ticker, market="TW",
        mentioned_at=when, extraction_method="pipeline_llm", sentiment_label="BULLISH",
    )
    db.add(m)
    db.commit()
    return m


def test_old_mentions_get_snapshots_even_past_the_per_cycle_limit(session):
    """The old shape scanned only the newest `limit` mentions, so anything older never
    got a snapshot. Selecting the needy ones must reach the old row when the new one
    is already complete."""
    _seed_closes(session, "2330", "2025-09-01", [100.0] * 70)
    old = _mention(session, "2330", datetime(2025, 9, 1), "old")
    new = _mention(session, "2330", datetime(2025, 9, 2), "new")
    assert ms.compute_ticker_snapshots(session, limit=1) == 1  # newest first: `new`
    assert ms.compute_ticker_snapshots(session, limit=1) == 1  # then `old`, not `new` again
    assert {s.mention_id for s in session.query(TickerPerformanceSnapshot).all()} == {old.id, new.id}
    assert ms.compute_ticker_snapshots(session, limit=1) == 0  # both complete → nothing to do


def test_a_snapshot_without_price_data_is_retried_once_closes_arrive(session):
    """A mention older than the recompute horizon whose snapshot has no baseline was
    frozen forever; a later history backfill must be able to fill it."""
    m = _mention(session, "2330", datetime(2025, 9, 1), "m")
    assert ms.compute_ticker_snapshots(session) == 1
    snap = session.query(TickerPerformanceSnapshot).filter_by(mention_id=m.id).one()
    assert snap.baseline_close is None
    _seed_ohlc(session, "2330", "2025-09-01", [100.0] * 70)
    assert ms.compute_ticker_snapshots(session) == 1
    session.refresh(snap)
    assert snap.baseline_close == 100.0 and snap.r60d == 0.0
    assert ms.compute_ticker_snapshots(session) == 0


# ── price breaks: stock_daily_ohlc closes are unadjusted ─────────────────

# 6669 緯穎, real closes 2026-08-20 .. 09-04: the 3-for-1 split lands on 2026-09-02.
WIWYNN = [6325, 6255, 6300, 6440, 6785, 6815, 7200, 7095, 7800, 2610, 2475, 2565]


def test_windows_across_a_split_are_null_not_minus_66(session):
    _seed_ohlc(session, "6669", "2026-08-20", WIWYNN)
    out = ms.compute_trading_day_returns(session, "6669", "2026-08-27")
    assert out["price_break_date"] == "2026-09-02"
    assert out["r1d"] == pytest.approx((7200 - 6815) / 6815 * 100, abs=0.01)  # before the split
    assert out["r5d"] is None  # 09-03 would be 2475 vs 6815 = -63.68%

    # Mentioned the day before: even r1d crosses it.
    out = ms.compute_trading_day_returns(session, "6669", "2026-09-01")
    assert out["r1d"] is None and out["price_break_date"] == "2026-09-02"

    # Baseline after the split: clean again.
    out = ms.compute_trading_day_returns(session, "6669", "2026-09-02")
    assert out["price_break_date"] is None
    assert out["r1d"] == pytest.approx((2475 - 2610) / 2610 * 100, abs=0.01)


def _add_mention(db, key, **kw):
    m = ContentMention(mention_key=key, episode_id="ep", confidence=1.0,
                       extraction_method="test", **kw)
    db.add(m)
    db.commit()
    return m


def test_rescore_reaches_completed_snapshots_scored_before_the_fix(session):
    _seed_ohlc(session, "6669", "2026-08-20", WIWYNN)
    _seed_ohlc(session, "3008", "2026-08-20", [5515, 5610, 5385, 5720, 6290, 6915, 7065, 7650, 7580, 7810, 7150, 7400])
    assert ms.detect_price_breaks(session, "2026-01-01") == [("6669", "2026-09-02")]

    tick = _add_mention(session, "t1", mention_type="ticker", ticker="6669", mentioned_at=datetime(2026, 8, 27, 2))
    other = _add_mention(session, "t2", mention_type="ticker", ticker="3008", mentioned_at=datetime(2026, 8, 27, 2))
    sect = _add_mention(session, "s1", mention_type="sector", exposure_id="ai_server",
                    mentioned_at=datetime(2026, 8, 27, 2), payload={"members": ["6669", "3008"]})
    # What the old scorer left behind: complete-looking rows with the split baked in.
    session.add_all([
        TickerPerformanceSnapshot(mention_id=tick.id, ticker="6669", mention_date="2026-08-27",
                                  baseline_close=6815, r1d=5.65, r5d=-63.68),
        TickerPerformanceSnapshot(mention_id=other.id, ticker="3008", mention_date="2026-08-27",
                                  baseline_close=6915, r1d=2.17),
        SectorPerformanceSnapshot(mention_id=sect.id, exposure_id="ai_server", mention_date="2026-08-27",
                                  member_count=2, r5d=-30.0),
    ])
    session.commit()

    stats = ms.rescore_price_break_snapshots(session)
    assert stats == {"price_break_ticker_rescored": 1, "price_break_sector_rescored": 1}
    snaps = {s.ticker: s for s in session.query(TickerPerformanceSnapshot)}
    assert snaps["6669"].r5d is None and snaps["6669"].price_break_date == "2026-09-02"
    assert snaps["3008"].price_break_date is None
    sector = session.query(SectorPerformanceSnapshot).one()
    assert sector.r5d == pytest.approx((7150 - 6915) / 6915 * 100, abs=0.01)  # 3008 alone
    assert sector.price_break_date == "2026-09-02"

    # Stamped, so the next cycle leaves them alone.
    assert ms.rescore_price_break_snapshots(session) == {
        "price_break_ticker_rescored": 0, "price_break_sector_rescored": 0}
