"""Parsing/normalization for the whole-market TW daily OHLC fetcher (M1).

The exchange feeds return ROC-format dates and string numerics; getting the conversion
and field mapping right is the only non-trivial logic (the fetch/upsert are I/O). No
network — hand-built payloads mirror the live TWSE/TPEx OpenAPI shapes (verified 2026-07-05).

The per-source backfill-completeness check (Fix #2 for the 2026-07-09 zero-candidate
screener incident) does touch the DB, so it gets a small SQLite fixture mirroring
``test_screener.py``'s ``screener_db``.
"""

import os
import tempfile

import pytest

from src.services.tw_daily_ohlc_refresh import (
    _MIN_ROWS_PER_DAY,
    _MIN_TPEX_ROWS,
    _MIN_TWSE_ROWS,
    _normalize_tpex,
    _normalize_tpex_hist,
    _normalize_tpex_insti,
    _normalize_twse,
    _normalize_twse_hist,
    _normalize_twse_t86,
    _num,
    _roc_to_iso,
    _rows_for_date,
    _rows_from_feed,
)


def test_roc_to_iso():
    assert _roc_to_iso("1150703") == "2026-07-03"
    assert _roc_to_iso("1000101") == "2011-01-01"
    assert _roc_to_iso("") is None
    assert _roc_to_iso("abc") is None
    assert _roc_to_iso("115070") is None  # too short (6 digits) → reject, not misparse


def test_num():
    assert _num("1,234.5") == 1234.5
    assert _num("0") == 0.0
    assert _num("--") is None
    assert _num("") is None
    assert _num(None) is None


def test_normalize_twse_full_mapping():
    row = _normalize_twse({
        "Date": "1150703", "Code": "2330", "ClosingPrice": "1,000.00",
        "OpeningPrice": "990.0", "HighestPrice": "1005", "LowestPrice": "988",
        "TradeVolume": "20000000", "TradeValue": "19800000000",
    })
    assert row == {
        "ticker": "2330", "date": "2026-07-03", "open": 990.0, "high": 1005.0,
        "low": 988.0, "close": 1000.0, "volume": 20000000.0,
        "trading_value": 19800000000.0, "source": "twse",
    }


def test_normalize_tpex_full_mapping():
    row = _normalize_tpex({
        "Date": "1150703", "SecuritiesCompanyCode": "6488", "Close": "500",
        "Open": "495", "High": "505", "Low": "494", "TradingShares": "1000",
        "TransactionAmount": "500000",
    })
    assert row["ticker"] == "6488"
    assert row["trading_value"] == 500000.0
    assert row["source"] == "tpex"


def test_filter_drops_warrants_and_no_close():
    # 6-digit warrant code is rejected by is_tw_ticker; a '--' close is unusable.
    assert _normalize_twse({"Date": "1150703", "Code": "030192", "ClosingPrice": "5"}) is None
    assert _normalize_twse({"Date": "1150703", "Code": "2330", "ClosingPrice": "--"}) is None


# ── Backfill: historical whole-market feeds (list-of-lists tables, Chinese fields) ──

def test_normalize_twse_hist():
    # MI_INDEX table[8] column order (成交金額 in 成交金額, close in 收盤價); commas stripped.
    rec = {
        "證券代號": "2330", "證券名稱": "台積電", "成交股數": "20,000,000",
        "成交筆數": "50000", "成交金額": "19,800,000,000", "開盤價": "990",
        "最高價": "1005", "最低價": "988", "收盤價": "1,000",
    }
    row = _normalize_twse_hist(rec, "2026-07-03")
    assert row == {
        "ticker": "2330", "date": "2026-07-03", "open": 990.0, "high": 1005.0,
        "low": 988.0, "close": 1000.0, "volume": 20000000.0,
        "trading_value": 19800000000.0, "source": "twse",
    }


def test_normalize_tpex_hist():
    rec = {
        "代號": "6488", "名稱": "環球晶", "收盤": "500", "開盤": "495",
        "最高": "505", "最低": "494", "成交股數": "1,000", "成交金額(元)": "500,000",
    }
    row = _normalize_tpex_hist(rec, "2026-07-03")
    assert row["ticker"] == "6488" and row["trading_value"] == 500000.0 and row["source"] == "tpex"


def test_rows_from_feed_picks_stock_table_and_skips_holidays():
    payload = {
        "stat": "OK",
        "tables": [
            {"fields": ["指數", "收盤指數"], "data": [["發行量加權股價指數", "20000"]]},  # index table — no code col
            {"fields": ["證券代號", "收盤價", "開盤價", "最高價", "最低價", "成交股數", "成交金額"],
             "data": [["2330", "1000", "990", "1005", "988", "100", "99000"]]},
        ],
    }
    rows = _rows_from_feed(payload, "證券代號", _normalize_twse_hist, "2026-07-03")
    assert len(rows) == 1 and rows[0]["ticker"] == "2330"
    # A holiday returns stat != ok → no rows, no misparse.
    assert _rows_from_feed({"stat": "no data"}, "證券代號", _normalize_twse_hist, "2026-07-03") == []


# ── M3: 三大法人 institutional net-share normalizers (TWSE T86 + TPEx OpenAPI) ──────

def test_normalize_twse_t86():
    # foreign = 外陸資買賣超 + 外資自營商買賣超; total = 三大法人買賣超. Net can be negative.
    # 投信買賣超股數 (issue #450 Part A) is a sibling column on the same T86 record.
    rec = {
        "證券代號": "2330", "外陸資買賣超股數(不含外資自營商)": "1,000",
        "外資自營商買賣超股數": "100", "投信買賣超股數": "300", "三大法人買賣超股數": "1,500",
    }
    assert _normalize_twse_t86(rec, "2026-07-03") == {
        "ticker": "2330", "date": "2026-07-03",
        "foreign_net_shares": 1100.0, "trust_net_shares": 300.0,
        "total_net_shares": 1500.0, "source": "twse",
    }
    # negative net + 0 total are valid (kept); warrant code filtered out.
    neg = _normalize_twse_t86({"證券代號": "2317", "外陸資買賣超股數(不含外資自營商)": "-5,000",
                               "外資自營商買賣超股數": "0", "投信買賣超股數": "0",
                               "三大法人買賣超股數": "0"}, "2026-07-03")
    assert neg["foreign_net_shares"] == -5000.0 and neg["total_net_shares"] == 0.0
    assert neg["trust_net_shares"] == 0.0
    # missing 投信 field (e.g. an older/short payload) defaults to 0.0, never crashes.
    missing = _normalize_twse_t86({"證券代號": "2330", "三大法人買賣超股數": "10"}, "2026-07-03")
    assert missing["trust_net_shares"] == 0.0
    assert _normalize_twse_t86({"證券代號": "030123", "三大法人買賣超股數": "5"}, "2026-07-03") is None


def test_normalize_tpex_insti():
    rec = {
        "SecuritiesCompanyCode": "6488", "TotalDifference": "2000",
        "Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Difference": "1500",
        "ForeignDealers-Difference": "200",
        "SecuritiesInvestmentTrustCompanies-Difference": "400",
    }
    assert _normalize_tpex_insti(rec, "2026-07-03") == {
        "ticker": "6488", "date": "2026-07-03",
        "foreign_net_shares": 1700.0, "trust_net_shares": 400.0,
        "total_net_shares": 2000.0, "source": "tpex",
    }


# ── Fix #2: per-source backfill completeness (2026-07-09 zero-candidate incident) ──

@pytest.fixture()
def ohlc_db():
    """Fresh SQLite engine bound to a temp file, tables created — mirrors
    ``test_screener.py``'s ``screener_db`` fixture (no internal-API-key setup needed here)."""
    import src.database.postgres as pg
    from src.config import settings

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    prev_engine, prev_session = pg.engine, pg.SessionLocal
    prev_use_pg, prev_path = settings.use_postgres, settings.database_path

    settings.use_postgres = False
    settings.database_path = path
    pg.engine = None
    pg.SessionLocal = None
    pg.init_engine()
    from src.database import models  # noqa: F401
    pg.create_all_tables()

    try:
        yield pg
    finally:
        pg.engine, pg.SessionLocal = prev_engine, prev_session
        settings.use_postgres = prev_use_pg
        settings.database_path = prev_path
        if os.path.exists(path):
            os.unlink(path)


def test_rows_for_date_tpex_only_partial_day_not_skipped(ohlc_db):
    """A TPEx-only day (880 real-world rows) clears the OLD combined
    ``>= _MIN_ROWS_PER_DAY`` (500) bar on its own but must fail the NEW per-source rule
    (twse >= _MIN_TWSE_ROWS AND tpex >= _MIN_TPEX_ROWS), so backfill does not skip it and
    its missing TWSE half gets fetched."""
    from src.database.models import StockDailyOHLC

    for s in ohlc_db.get_session():
        for i in range(880):
            s.add(StockDailyOHLC(ticker=f"PAD-{i:05d}", date="2026-07-09", close=1.0, source="tpex"))
        s.commit()
        break

    twse_n, tpex_n = _rows_for_date("2026-07-09")
    assert twse_n == 0
    assert tpex_n == 880

    # The bug: old check only looked at the combined total.
    assert (twse_n + tpex_n) >= _MIN_ROWS_PER_DAY  # would have been wrongly "filled"
    # The fix: per-source check correctly says "not filled" (skip condition is False).
    assert not (twse_n >= _MIN_TWSE_ROWS and tpex_n >= _MIN_TPEX_ROWS)


def test_rows_for_date_both_sources_filled_is_skipped(ohlc_db):
    from src.database.models import StockDailyOHLC

    for s in ohlc_db.get_session():
        for i in range(_MIN_TWSE_ROWS):
            s.add(StockDailyOHLC(ticker=f"TW-{i:05d}", date="2026-07-08", close=1.0, source="twse"))
        for i in range(_MIN_TPEX_ROWS):
            s.add(StockDailyOHLC(ticker=f"TP-{i:05d}", date="2026-07-08", close=1.0, source="tpex"))
        s.commit()
        break

    twse_n, tpex_n = _rows_for_date("2026-07-08")
    assert twse_n >= _MIN_TWSE_ROWS and tpex_n >= _MIN_TPEX_ROWS  # skip condition is True
