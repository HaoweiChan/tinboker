"""Unit tests for the daily-close refresher's read/compute helpers."""

import asyncio
import pytest

import src.services.stock_close_refresh as r


def test_is_tw():
    assert r._is_tw("2330") is True
    assert r._is_tw("2330.TW") is True
    assert r._is_tw("AAPL") is False
    assert r._is_tw("NVDA") is False


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def query(self, *a, **k):
        return _FakeQuery(self._rows)


def _patch_session(monkeypatch, rows):
    def _gen():
        yield _FakeSession(rows)
    monkeypatch.setattr(r, "get_session", _gen)


def test_eod_change_two_closes(monkeypatch):
    # rows are (close,) tuples ordered date DESC: latest=110, prev=100 -> +10%
    _patch_session(monkeypatch, [(110.0,), (100.0,)])
    assert asyncio.run(r.get_eod_change_pct("AAPL")) == pytest.approx(10.0)


def test_eod_change_needs_two_rows(monkeypatch):
    _patch_session(monkeypatch, [(110.0,)])  # only one close
    assert asyncio.run(r.get_eod_change_pct("AAPL")) is None


def test_eod_change_zero_prev_is_none(monkeypatch):
    _patch_session(monkeypatch, [(110.0,), (0.0,)])  # avoid div-by-zero
    assert asyncio.run(r.get_eod_change_pct("AAPL")) is None


def test_eod_change_db_error_is_none(monkeypatch):
    class _Boom:
        def query(self, *a, **k):
            raise RuntimeError("db down")
    def _gen():
        yield _Boom()
    monkeypatch.setattr(r, "get_session", _gen)
    # Must never raise into the request path.
    assert asyncio.run(r.get_eod_change_pct("AAPL")) is None


# ── backfill_us_mention_history ───────────────────────────────────────────────

class _Bars:
    def __init__(self, n):
        self.n = n
        self.calls = []

    def get_daily_ohlc(self, ticker, start, end):
        self.calls.append((ticker, start))
        from src.services.providers.base import Bar
        return [Bar(date=f"2025-08-{d:02d}", open=1, high=1, low=1, close=1, volume=0) for d in range(1, self.n + 1)]


def test_us_history_fetches_only_tickers_without_a_bar_that_old(monkeypatch):
    monkeypatch.setattr(r, "_us_mention_tickers", lambda db: [("NVDA", "2025-08-05"), ("MSFT", "2025-09-01")])
    monkeypatch.setattr(r, "_has_bar_on_or_before", lambda db, t, d: t == "MSFT")  # MSFT already has history
    stored = {}
    monkeypatch.setattr(r, "_store_ohlc_bars", lambda t, bars: stored.setdefault(t, len(bars)))
    _patch_session(monkeypatch, [])
    provider = _Bars(3)
    assert r.backfill_us_mention_history(provider=provider, gap_seconds=0) == 3
    assert provider.calls == [("NVDA", "2025-07-26")]  # 10-day pad before the earliest mention
    assert stored == {"NVDA": 3}


def test_us_history_with_nothing_mentioned_makes_no_provider_call(monkeypatch):
    monkeypatch.setattr(r, "_us_mention_tickers", lambda db: [])
    _patch_session(monkeypatch, [])
    provider = _Bars(3)
    assert r.backfill_us_mention_history(provider=provider, gap_seconds=0) == 0
    assert provider.calls == []
