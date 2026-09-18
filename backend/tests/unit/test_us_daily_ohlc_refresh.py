"""Parsing/normalization for the whole-market US daily OHLC warmer (issue #449).

The only non-trivial logic is mapping a Polygon grouped-daily agg → a stock_daily_ohlc row
(dollar-volume derivation + US-symbol filtering); the fetch/upsert are I/O. No network —
hand-built ``SimpleNamespace`` aggs mirror the Polygon ``GroupedDailyAgg`` shape.
"""

from types import SimpleNamespace

from src.services.us_daily_ohlc_refresh import _f, _normalize_grouped


def _agg(**kw):
    """A Polygon grouped-daily agg stand-in (attribute access, like the real SDK object)."""
    base = dict(ticker="AAPL", open=100.0, high=105.0, low=99.0, close=104.0, volume=1_000_000.0, vwap=102.0)
    base.update(kw)
    return SimpleNamespace(**base)


def test_f():
    assert _f("1234.5") == 1234.5
    assert _f(0) == 0.0
    assert _f(None) is None
    assert _f("--") is None


def test_normalize_full_mapping_dollar_volume_from_vwap():
    row = _normalize_grouped(_agg(), "2026-07-09")
    assert row == {
        "ticker": "AAPL", "date": "2026-07-09", "open": 100.0, "high": 105.0,
        "low": 99.0, "close": 104.0, "volume": 1_000_000.0,
        "trading_value": 102.0 * 1_000_000.0,  # vwap × volume
        "source": "polygon",
    }


def test_trading_value_falls_back_to_close_when_vwap_missing():
    row = _normalize_grouped(_agg(vwap=None), "2026-07-09")
    assert row["trading_value"] == 104.0 * 1_000_000.0  # close × volume


def test_trading_value_none_when_volume_missing():
    row = _normalize_grouped(_agg(volume=None, vwap=None), "2026-07-09")
    assert row["trading_value"] is None
    assert row["volume"] is None


def test_lowercases_are_uppercased_and_kept():
    row = _normalize_grouped(_agg(ticker="spy"), "2026-07-09")
    assert row["ticker"] == "SPY"  # ETFs kept — the US screener needs sector ETFs


def test_dotted_class_share_kept():
    assert _normalize_grouped(_agg(ticker="BRK.B"), "2026-07-09")["ticker"] == "BRK.B"


def test_non_us_symbols_dropped():
    assert _normalize_grouped(_agg(ticker="2330"), "2026-07-09") is None   # TW numeric
    assert _normalize_grouped(_agg(ticker="ABC1"), "2026-07-09") is None   # digit → not a plain symbol
    assert _normalize_grouped(_agg(ticker=""), "2026-07-09") is None


def test_missing_close_dropped():
    assert _normalize_grouped(_agg(close=None), "2026-07-09") is None


# ── Budget-aware fetching (the shared Massive minute budget, PR #726) ──

import asyncio

import src.services.us_daily_ohlc_refresh as u


def test_a_spent_budget_defers_instead_of_walking_back_through_dates(monkeypatch):
    """Probing five more dates when the budget is spent just burns five more refusals."""
    calls = []

    def _fetch(iso):
        calls.append(iso)
        return None  # budget spent

    monkeypatch.setattr(u, "_fetch_grouped", _fetch)
    assert asyncio.run(u.refresh_us_daily_ohlc()) == 0
    assert len(calls) == 1


def test_a_non_trading_day_still_walks_back(monkeypatch):
    seen = []

    def _fetch(iso):
        seen.append(iso)
        return [] if len(seen) < 3 else [{"ticker": "AAPL", "date": iso, "close": 1.0}]

    monkeypatch.setattr(u, "_fetch_grouped", _fetch)
    monkeypatch.setattr(u, "_upsert_rows", lambda rows: len(rows))
    assert asyncio.run(u.refresh_us_daily_ohlc()) == 1
    assert len(seen) == 3


def test_fetch_grouped_reports_budget_refusal_as_none(monkeypatch):
    from src.services.massive_service import MassiveAPIError

    class _Svc:
        @property
        def client(self):
            raise MassiveAPIError("Massive minute budget spent")

    monkeypatch.setattr(u, "MassiveAPIService", _Svc)
    assert u._fetch_grouped("2026-09-17") is None


def test_fetch_grouped_reports_other_failures_as_empty(monkeypatch):
    class _Svc:
        @property
        def client(self):
            raise RuntimeError("network")

    monkeypatch.setattr(u, "MassiveAPIService", _Svc)
    assert u._fetch_grouped("2026-09-17") == []


def test_backfill_spacing_matches_the_us_warmers():
    assert u._BACKFILL_GAP_SECONDS >= 12.0
