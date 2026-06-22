"""FinMind only serves TW — non-TW tickers must never reach finmind_budget.consume.

Regression for the launch budget incident where 6-digit Korean codes (005930) and other
non-TW tickers were routed into the TW-only FinMind API, exhausting the shared hourly
budget on calls that always 404.
"""

import pytest

from src.services.finmind_service import FinMindAPIService, is_tw_ticker


# (ticker, is_tw) — TW codes are 4-5 digits; 6-digit are KR, alpha is US, junk is neither.
CASES = [
    ("2330", True), ("1101", True), ("2330.TW", True), ("00878", True),  # TW
    ("005930", False), ("035420", False), ("000660", False), ("000150", False),  # KR (6-digit)
    ("000000", False), ("AAPL", False), ("0700", True), ("", False),  # US / junk / 4-digit HK collision
]


@pytest.mark.parametrize("ticker,expected", CASES)
def test_is_tw_ticker(ticker, expected):
    assert is_tw_ticker(ticker) is expected


def test_non_tw_tickers_never_consume_budget(monkeypatch):
    """Every per-ticker FinMind entry point must short-circuit before consume() for non-TW."""
    calls = []
    monkeypatch.setattr("src.services.finmind_budget.consume", lambda *a, **k: calls.append(a) or True)
    # A network call would mean the guard failed — make requests.get loud if reached.
    monkeypatch.setattr("src.services.finmind_service.requests.get",
                        lambda *a, **k: pytest.fail("non-TW ticker reached the network"))

    svc = FinMindAPIService(api_key="test-key")
    for ticker in ("005930", "035420", "000660", "AAPL", "000000"):
        assert svc.get_ticker_details(ticker) is None
        assert svc.get_ticker_snapshot(ticker) is None
        assert svc.list_daily_ticker_summary_range(ticker, "2026-06-01", "2026-06-23") == []
        assert svc.list_financials_ratios(ticker) == []
        assert svc.get_daily_aggregates(ticker) == []

    assert calls == [], f"non-TW tickers reached finmind_budget.consume: {calls}"
