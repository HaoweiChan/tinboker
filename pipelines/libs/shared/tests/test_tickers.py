"""Tests for the ticker registry (shared.tickers)."""

import pytest
from shared.tickers import (
    TickerInfo,
    canonical_symbol,
    is_valid_ticker_symbol,
    lookup_ticker,
    valid_tickers,
)


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


# --- is_valid_ticker_symbol -------------------------------------------------

@pytest.mark.parametrize("sym", [
    "2330", "2330.TW",              # TW number, with/without market suffix
    "00878B",                       # TW ETF with trailing class letter
    "NVDA", "nvda", "AAPL",         # US letter symbols
    "BRK.B",                        # US class share
    "SPY", "QQQ",                   # registry ETFs (type=etf)
    "SPCE",                         # real ticker (Virgin Galactic) — stays valid
    "ZZZZ",                         # not in registry but valid US shape
    "00878", "006208",             # real TW ETF codes — leading-zero guard must allow
])
def test_valid_symbols_pass(sym):
    assert is_valid_ticker_symbol(sym) is True


@pytest.mark.parametrize("sym", [
    # Market indices — both registry-stored (type=index) and not-in-registry.
    "VIX", "SPX", "DJI", "IXIC", "RUT", "NBI", "MSCI", "SOX", "NDX",
    # Private companies / wrong-or-junk symbols with no price data.
    "OPENAI", "ANTHROPIC", "SPACEX", "TSMC", "SPACE", "WD", "GIGA", "ASE",
    # Foreign / unlisted-on-our-feeds names that pass the US-letter shape.
    "YMTC", "BNP", "LINEPAY", "HSCEI",
    # Country / region abbreviations (mostly 2-letter, would pass the shape check).
    "US", "TW", "CN", "KR", "JP", "EU", "HK", "IN", "INDIA", "CHINA",
    # Bare asset-class / instrument words.
    "ETF", "BOND", "BONDS", "REIT",
    # TW leading-zero junk — no listing has 4+ leading zeros.
    "000000", "0000",
    # Name+ticker strings and multi-word asset-class labels.
    "台積電 (TSMC)", "TSMC (台積電)", "TSM Inc",
    "EMERGING MARKET LOCAL CURRENCY BONDS", "US HY BOND ETF",
    # CJK category names / phrases the LLM mislabels as tickers.
    "被動元件", "EDGE COMPUTING相關類股",
    # Empties / whitespace.
    "", "   ",
])
def test_junk_symbols_rejected(sym):
    assert is_valid_ticker_symbol(sym) is False


@pytest.mark.parametrize("bad", [None, 123, 4.5, ["NVDA"], object()])
def test_non_string_rejected(bad):
    assert is_valid_ticker_symbol(bad) is False  # type: ignore[arg-type]


def test_registry_index_and_private_types_are_not_tradeable():
    # These exist in the registry (so the wiki builder gets display metadata) but
    # must NOT count as tradeable tickers.
    assert lookup_ticker("SPX") is not None and lookup_ticker("SPX").type == "index"
    assert lookup_ticker("OPENAI") is not None and lookup_ticker("OPENAI").type == "private"
    assert is_valid_ticker_symbol("SPX") is False
    assert is_valid_ticker_symbol("OPENAI") is False


def test_valid_tickers_filters_canonicalizes_and_dedupes():
    raw = [
        "2330.TW", "2330", "nvda",          # → 2330 (deduped), NVDA
        "SPX", "VIX", "MSCI",               # indices dropped
        "ETF", "台積電 (TSMC)", "TSMC",       # junk dropped
        "", None,                            # falsy / non-str dropped
    ]
    assert valid_tickers(raw) == ["2330", "NVDA"]
    assert valid_tickers([]) == []
    assert valid_tickers(None) == []
