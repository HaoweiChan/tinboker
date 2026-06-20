"""Ticker-symbol validation: keep real listings, drop LLM-invented junk.

Regression for the backfill finding that the summarizer tags private companies and
sector/category names with #ticker:/ticker (OPENAI, ANTHR, 被動元件, 臺股), which
polluted related_tickers, per-episode sentiment docs, and trending.
"""
import pytest
from shared.tickers import is_valid_ticker_symbol, valid_tickers


@pytest.mark.parametrize("sym", [
    "2330", "2317", "00878", "0050",          # Taiwan listings (incl. ETF letter suffix)
    "005930", "000660",                        # Korea listings (Samsung, SK Hynix) — kept
    "NVDA", "AVGO", "RKLB", "CRM", "NOW", "SNOW", "INTC", "TSM",  # US listings
    "BRK.B",                                   # US with share class
    "SPCE",                                    # a REAL ticker (Virgin Galactic) — kept
])
def test_real_listings_are_valid(sym):
    assert is_valid_ticker_symbol(sym)


@pytest.mark.parametrize("sym", [
    "OPENAI", "ANTHROPIC",                     # too long for a US symbol
    "ANTHR", "SPCX",                           # private-company hallucinations (denylist)
    "JPOW", "POWELL", "YELLEN", "MUSK", "BUFFETT",  # people — esp. Jerome Powell
    "N", "X", "A",                             # bare single letters (transcription fragments)
    "FED", "FOMC", "VIX", "DXY", "LIBOR",      # macro / index / policy abbreviations
    "被動元件", "臺股",                          # CJK sector/category names
    "EDGE COMPUTING相關類股", "ESTAR LABS",     # phrases with spaces
    "衛星/火箭相關類股 (台股)",                  # phrase with punctuation
    "", "  ", None, 1234,                       # empties / non-strings
])
def test_junk_is_invalid(sym):
    assert not is_valid_ticker_symbol(sym)


def test_drops_person_names_and_single_letters_keeps_kr():
    # Reported regression: the extractor emitted "JPOW" (Jerome Powell) and a bare
    # "N" as related_tickers, rendering priceless junk pills on /sector rows. They
    # must be dropped while real TW/US tickers AND the price-feed-less Korean codes
    # (005930 Samsung, 000660 SK Hynix) survive untouched.
    # valid_tickers preserves input order (callers sort); junk is simply removed.
    raw = ["2330", "NVDA", "JPOW", "N", "005930", "000660", "被動元件", "FED"]
    assert valid_tickers(raw) == ["2330", "NVDA", "005930", "000660"]


def test_valid_tickers_filters_canonicalizes_dedups():
    # 2330.TW canonicalizes to 2330 and de-dupes against it.
    out = valid_tickers(["2330", "2330.TW", "OPENAI", "被動元件", "NVDA"])
    assert out == ["2330", "NVDA"]


def test_cleans_observed_related_tickers():
    raw = ["2308", "2330", "4935", "ANTHR", "ASTS", "NVDA", "OPENAI", "RKLB", "SPCE", "TSLA"]
    assert valid_tickers(raw) == ["2308", "2330", "4935", "ASTS", "NVDA", "RKLB", "SPCE", "TSLA"]


def test_cleans_observed_insight_tickers():
    raw = ["ANTHROPIC", "ASTS", "EDGE COMPUTING相關類股", "ESTAR LABS", "FLY",
           "RKLB", "SPCX", "TSLA", "臺股", "衛星/火箭相關類股 (台股)", "被動元件"]
    assert valid_tickers(raw) == ["ASTS", "FLY", "RKLB", "TSLA"]
