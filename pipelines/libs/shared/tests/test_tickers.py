"""Tests for the ticker registry (shared.tickers)."""

from shared.tickers import TickerInfo, canonical_symbol, lookup_ticker


def test_lookup_by_canonical_and_alias():
    a = lookup_ticker("2330")
    b = lookup_ticker("2330.TW")
    c = lookup_ticker("2330 tw")
    assert a == b == c
    assert isinstance(a, TickerInfo)
    assert a.symbol == "2330" and a.name == "台積電" and a.market == "TW" and a.type == "company"


def test_lookup_case_insensitive_us_ticker():
    assert lookup_ticker("nvda") == lookup_ticker("NVDA")
    assert lookup_ticker("NVDA").name == "輝達"
    assert lookup_ticker("SPY").type == "etf"


def test_lookup_strips_market_suffix():
    assert lookup_ticker("005930.KS").symbol == "005930"
    assert lookup_ticker("2317:TW").symbol == "2317"


def test_unknown_ticker_returns_none():
    assert lookup_ticker("ZZZZ") is None
    assert lookup_ticker("") is None
    assert lookup_ticker(None) is None  # type: ignore[arg-type]


def test_canonical_symbol():
    assert canonical_symbol("2330.TW") == "2330"
    assert canonical_symbol("nvda") == "NVDA"
    # unknowns: trimmed + upper-cased, unchanged otherwise
    assert canonical_symbol(" foo ") == "FOO"
    assert canonical_symbol("9999") == "9999"
