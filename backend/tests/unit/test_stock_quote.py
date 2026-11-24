"""Valuation feed parsing and the stock-page quote (price facts the page, its title and
the crawler body share). Pure functions only; shapes mirror the live feeds (2026-11-24)."""

from src.routers.stock import quote_from_bars
from src.services.tw_daily_ohlc_refresh import _normalize_tpex_val, _normalize_twse_val


def test_twse_valuation_maps_all_three_ratios():
    rec = {"Date": "1151123", "Code": "2801", "Name": "彰銀", "PEratio": "14.43", "DividendYield": "4.18", "PBratio": "1.31"}
    assert _normalize_twse_val(rec) == {
        "ticker": "2801", "date": "2026-11-23", "pe": 14.43, "pb": 1.31, "dividend_yield": 4.18, "source": "twse",
    }


def test_twse_loss_maker_has_no_pe_but_keeps_yield():
    rec = {"Date": "1151123", "Code": "2002", "PEratio": "", "DividendYield": "0.00", "PBratio": "0.85"}
    row = _normalize_twse_val(rec)
    assert row["pe"] is None and row["pb"] == 0.85 and row["dividend_yield"] == 0.0


def test_tpex_valuation_and_warrant_filter():
    rec = {"Date": "1151123", "SecuritiesCompanyCode": "5483", "PriceEarningRatio": "14.54",
           "YieldRatio": "2.72", "PriceBookRatio": "1.17"}
    assert _normalize_tpex_val(rec) == {
        "ticker": "5483", "date": "2026-11-23", "pe": 14.54, "pb": 1.17, "dividend_yield": 2.72, "source": "tpex",
    }
    assert _normalize_tpex_val({**rec, "SecuritiesCompanyCode": "712345"}) is None  # 6-digit warrant


def _bar(d, c, h=None, lo=None, v=1000):
    return {"date": d, "open": c, "high": h or c, "low": lo or c, "close": c, "volume": v}


def test_quote_change_and_52w_range():
    bars = [_bar("2026-01-02", 20, h=21, lo=19), _bar("2026-11-20", 25.4, h=26), _bar("2026-11-23", 25.1, v=34784072)]
    q = quote_from_bars(bars, {"pe": 14.43})
    assert q["close"] == 25.1 and q["prev_close"] == 25.4 and q["date"] == "2026-11-23"
    assert q["change"] == -0.3 and q["change_pct"] == -1.18
    assert q["high_52w"] == 26 and q["low_52w"] == 19 and q["range_from"] == "2026-01-02"
    assert q["volume"] == 34784072 and q["valuation"] == {"pe": 14.43}


def test_quote_range_starts_after_a_split_and_hides_that_days_change():
    bars = [_bar("2026-08-01", 1000, h=1100), _bar("2026-09-01", 1050), _bar("2026-09-02", 105)]
    q = quote_from_bars(bars, None)
    assert q["change"] is None and q["change_pct"] is None
    assert q["high_52w"] == 105 and q["range_from"] == "2026-09-02"


def test_quote_needs_bars():
    assert quote_from_bars([], None) is None
    one = quote_from_bars([_bar("2026-11-23", 10)], None)
    assert one["change"] is None and one["prev_close"] is None
