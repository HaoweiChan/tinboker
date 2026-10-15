"""Summary links must identify the company behind a listing, not just a valid code."""

import pytest
from shared.tickers import TickerInfo
from src.pipeline.utils import extract_tags_and_tickers, unlink_mismatched_tickers
from src.podcast.content_builder.nodes.tags_tickers import derive_tags_tickers


@pytest.fixture(autouse=True)
def ticker_registry(monkeypatch):
    rows = {
        "SPG": ("西蒙地產", "Simon Property Group", "US", ()),
        "AMZN": ("亞馬遜", "Amazon.com Inc.", "US", ()),
        "SPCX": ("SpaceX", "Space Exploration Technologies", "US", ()),
        "2330": ("台積電", "Taiwan Semiconductor", "TW", ()),
        "1503": ("士林電機", "Shihlin Electric", "TW", ()),
        "005930": ("三星電子", "Samsung Electronics", "KR", ()),
        "STUB": ("STUB", "STUB", "US", ()),
    }
    infos = {code: TickerInfo(code, name, english, market, "", "company", aliases)
             for code, (name, english, market, aliases) in rows.items()}
    monkeypatch.setattr("shared.tickers.lookup_ticker", lambda code: infos.get(code.upper().removesuffix(".TW")))
    monkeypatch.setattr("shared.tickers.prime_tickers", lambda symbols: None)


def test_wrong_company_is_unlinked_and_excluded_from_related_tickers():
    result = derive_tags_tickers({"markdown_report": "曾任職於[Springer Nature](#ticker:SPG)。"})
    assert result == {"markdown_report": "曾任職於Springer Nature。", "tags": [], "related_tickers": []}


def test_structured_fallback_cannot_restore_a_rejected_link():
    result = extract_tags_and_tickers({
        "summary_text": "[Springer Nature](#ticker:SPG)", "related_tickers": ["SPG"],
    })
    assert result["tickers"] == []


def test_same_symbol_can_still_have_a_valid_link():
    result = derive_tags_tickers({
        "markdown_report": "[Springer Nature](#ticker:SPG) 與 [Simon Property Group](#ticker:SPG)",
    })
    assert result["markdown_report"] == "Springer Nature 與 [Simon Property Group](#ticker:SPG)"
    assert result["related_tickers"] == ["SPG"]


@pytest.mark.parametrize(("label", "ticker"), [
    ("Simon Property", "SPG"), ("SPG", "SPG"), ("西蒙地產", "SPG"),
    ("AWS", "AMZN"), ("Amazon", "AMZN"), ("SpaceX", "SPCX"),
    ("台積電", "2330"), ("Taiwan Semiconductor", "2330"), ("士電", "1503"), ("三星", "005930"),
    ("Unknown Company", "ZZZZ"), ("Unresolved Company", "STUB"),
])
def test_compatible_or_incomparable_names_are_preserved(label, ticker):
    markdown = f"[{label}](#ticker:{ticker})"
    assert unlink_mismatched_tickers(markdown) == markdown


def test_clearly_different_taiwan_company_is_unlinked():
    assert unlink_mismatched_tickers("[鴻海](#ticker:2330)") == "鴻海"


def test_structured_only_fallback_is_preserved():
    assert extract_tags_and_tickers({"related_tickers": ["SPG"]})["tickers"] == ["SPG"]


def test_market_suffix_does_not_bypass_company_check():
    assert unlink_mismatched_tickers("[鴻海](#ticker:2330.TW)") == "鴻海"
