"""Unit tests for the daily-close refresher's read/compute helpers."""

from datetime import datetime, timedelta, timezone

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


# ── batch_read_latest_closes / change_pct_from_pairs ──────────────────────────
# Both warm tables are queried, so the fake session answers each of the two queries with
# the same rows — a duplicate (ticker, date) must collapse, not double up.

def test_batch_read_takes_the_two_newest_per_ticker(monkeypatch):
    _patch_session(monkeypatch, [
        ("AAPL", "2026-09-01", 90.0),
        ("AAPL", "2026-09-08", 110.0),
        ("AAPL", "2026-09-05", 100.0),
    ])
    got = r.batch_read_latest_closes(["AAPL"], ref_date_str="2026-09-09")
    assert got == {"AAPL": [("2026-09-05", 100.0), ("2026-09-08", 110.0)]}
    assert r.change_pct_from_pairs(got["AAPL"]) == pytest.approx(10.0)


def test_change_pct_needs_two_usable_closes():
    assert r.change_pct_from_pairs(None) is None
    assert r.change_pct_from_pairs([("2026-09-08", 110.0)]) is None      # only one close
    assert r.change_pct_from_pairs([("2026-09-05", 0.0), ("2026-09-08", 110.0)]) is None  # div-by-zero


def test_batch_read_db_error_is_empty(monkeypatch):
    class _Boom:
        def query(self, *a, **k):
            raise RuntimeError("db down")

    def _gen():
        yield _Boom()
    monkeypatch.setattr(r, "get_session", _gen)
    # Must never raise into the request path — a DB hiccup renders as null prices.
    assert r.batch_read_latest_closes(["AAPL"]) == {}


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


# ── intraday guard + same-day overwrite ───────────────────────────────────────

class _Store:
    """Fake session over a {(ticker, date): row} dict; first() honours the date filter."""

    def __init__(self, rows=None):
        self.rows = dict(rows or {})
        self.committed = False

    def query(self, *a, **k):
        return self

    def filter(self, *clauses):
        self._key = tuple(c.right.value for c in clauses)
        return self

    def first(self):
        return self.rows.get(self._key)

    def add(self, row):
        self.rows[(row.ticker, row.date)] = row

    def commit(self):
        self.committed = True

    def rollback(self):
        pass


class _Fin:
    def __init__(self, rows):
        self.rows = rows

    def list_daily_ticker_summary_range(self, *a):
        return self.rows


def _freeze(monkeypatch, fixed_utc):
    class _DT(datetime):
        @classmethod
        def utcnow(cls):
            return fixed_utc.replace(tzinfo=None)

        @classmethod
        def now(cls, tz=None):
            return fixed_utc.astimezone(tz) if tz else fixed_utc.replace(tzinfo=None)

    monkeypatch.setattr(r, "datetime", _DT)


def test_tw_row_for_today_is_not_written_before_1330_taipei(monkeypatch):
    # 2026-09-08 04:49 UTC = 12:49 Taipei: the market is open, Yahoo hands back a partial bar.
    _freeze(monkeypatch, datetime(2026, 9, 8, 4, 49, tzinfo=timezone.utc))
    store = _Store()
    monkeypatch.setattr(r, "get_session", lambda: iter([store]))
    rows = [{"date": "2026-09-07", "close": 110.2}, {"date": "2026-09-08", "close": 109.95}]
    assert r._fetch_and_store_closes("0050", _Fin(rows), None) == 1
    assert ("0050", "2026-09-08") not in store.rows
    assert store.rows[("0050", "2026-09-07")].close == 110.2

    # After the close the same row is final and gets stored; a stale same-day value is overwritten.
    _freeze(monkeypatch, datetime(2026, 9, 8, 6, 0, tzinfo=timezone.utc))  # 14:00 Taipei
    store.rows[("0050", "2026-09-08")] = r.StockDailyClose(ticker="0050", date="2026-09-08", close=109.95)
    assert r._fetch_and_store_closes("0050", _Fin([{"date": "2026-09-08", "close": 109.65}]), None) == 1
    assert store.rows[("0050", "2026-09-08")].close == 109.65


def test_close_is_final_us_uses_new_york_1600():
    ny_1559 = datetime(2026, 9, 8, 19, 59, tzinfo=timezone.utc)  # EDT = UTC-4
    assert r.close_is_final("AAPL", "2026-09-08", now=ny_1559) is False
    assert r.close_is_final("AAPL", "2026-09-08", now=ny_1559 + timedelta(minutes=1)) is True
    assert r.close_is_final("AAPL", "2026-09-07", now=ny_1559) is True
