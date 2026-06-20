"""US slow-data provider routing + Massive boundary guard.

Regression cover for the prod 429 storm: display names ("聯發科", "FOXCONN") and TW codes
("00993A") were leaking into the US-equities upstream. The guard must reject them before any
HTTP call, while real US symbols pass.
"""

from src.services.massive_service import MassiveAPIService, _looks_us
from src.services.providers import is_us_ticker


class TestUsTickerGuard:
    def test_real_symbols_pass(self):
        for t in ["NVDA", "AAPL", "F", "BRK.B", "brk.b"]:
            assert is_us_ticker(t) is True
            assert _looks_us(t) is True

    def test_junk_is_rejected(self):
        # Chinese display names, English company names, TW numeric/ETF codes, empties.
        for t in ["聯發科", "MEDIATEK", "FOXCONN", "SALESFORCE", "2330", "00993A", "", "   "]:
            assert is_us_ticker(t) is False
            assert _looks_us(t) is False

    def test_guard_short_circuits_without_http(self):
        # __new__ skips __init__/client setup; if the guard didn't return first, the call
        # would raise on the missing client — so a clean None/[] proves no HTTP was attempted.
        svc = MassiveAPIService.__new__(MassiveAPIService)
        assert svc.get_ticker_details("聯發科") is None
        assert svc.get_ticker_snapshot("FOXCONN") is None
        assert svc.list_daily_ticker_summary_range("SALESFORCE", "2026-06-10", "2026-06-20") == []
        assert svc.list_daily_ticker_summary("00993A") == []
