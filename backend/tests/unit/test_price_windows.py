"""Unit tests for forward windowed-return computation (picks scoreboard).

Covers `_window_returns` in src.routers.stock: completed windows compute a pct,
not-yet-elapsed windows stay None ("—" in the UI), and a missing baseline yields
all-None. `_get_reference_close` is monkeypatched so no DB/external API is touched.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

import src.routers.stock as stock


def _ms(dt: datetime) -> int:
    """Naive-UTC datetime → Unix ms (inverse of datetime.utcfromtimestamp)."""
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def _patch_closes(monkeypatch, mention_date_str: str, baseline, other):
    """Stub _get_reference_close: `baseline` on the mention date, `other` elsewhere."""
    async def _fake(ticker, ref_date_str, db):
        return baseline if ref_date_str == mention_date_str else other
    monkeypatch.setattr(stock, "_get_reference_close", _fake)


def test_completed_windows(monkeypatch):
    mention = datetime(2020, 1, 1)
    _patch_closes(monkeypatch, "2020-01-01", 100.0, 110.0)
    res = asyncio.run(stock._window_returns("AAPL", _ms(mention), 120.0, None))
    assert res["baseline"] == 100.0
    assert res["d7"] == pytest.approx(10.0)
    assert res["d30"] == pytest.approx(10.0)
    assert res["d90"] == pytest.approx(10.0)
    assert res["since"] == pytest.approx(20.0)  # current 120 vs baseline 100


def test_incomplete_windows_are_none(monkeypatch):
    mention = datetime.utcnow() - timedelta(days=10)
    _patch_closes(monkeypatch, mention.strftime("%Y-%m-%d"), 100.0, 110.0)
    res = asyncio.run(stock._window_returns("AAPL", _ms(mention), None, None))
    assert res["d7"] == pytest.approx(10.0)  # 7 days elapsed → scored
    assert res["d30"] is None                # window not complete yet
    assert res["d90"] is None
    assert res["since"] is None              # current_price not supplied


def test_missing_baseline_all_none(monkeypatch):
    async def _none(ticker, ref_date_str, db):
        return None
    monkeypatch.setattr(stock, "_get_reference_close", _none)
    res = asyncio.run(stock._window_returns("AAPL", _ms(datetime(2020, 1, 1)), 120.0, None))
    assert res == {"baseline": None, "d7": None, "d30": None, "d90": None, "since": None}
