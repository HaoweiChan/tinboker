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
