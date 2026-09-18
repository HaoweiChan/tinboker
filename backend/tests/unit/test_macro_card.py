"""Macro card: FRED CSV parsing, the lazy refresh, the series window, and the drawing."""
from datetime import datetime, timedelta

import pytest

from src.services import macro_data as md
from src.services.macro_card import macro_card_svg

CSV = "observation_date,DGS10\n2026-09-10,4.80\n2026-09-11,.\n2026-09-12,4.94\n2026-09-15,5.00\n"


@pytest.fixture
def macro_db(temp_db):
    from src.database import postgres as pg
    from src.database.models import MacroDaily
    MacroDaily.__table__.create(bind=pg.engine, checkfirst=True)


def test_parse_skips_freds_missing_day_marker():
    assert md.parse_fred_csv(CSV) == [("2026-09-10", 4.80), ("2026-09-12", 4.94), ("2026-09-15", 5.00)]
    assert md.parse_fred_csv("observation_date,X\n") == []


@pytest.mark.asyncio
async def test_ensure_fresh_pulls_once_then_waits_and_a_refetch_replaces_the_window(macro_db, monkeypatch):
    calls = []

    async def fake_fetch(fred_id, since):
        calls.append(fred_id)
        return md.parse_fred_csv(CSV) if len(calls) == 1 else [("2026-09-15", 5.02), ("2026-09-16", 5.05)]
    monkeypatch.setattr(md, "fetch_fred", fake_fetch)

    await md.ensure_fresh("US10Y")
    await md.ensure_fresh("US10Y")                       # fresh → no second call
    assert calls == ["DGS10"]
    assert md.points("US10Y", 2) == [("2026-09-12", 4.94), ("2026-09-15", 5.00)]

    await md.ensure_fresh("US10Y", now=datetime.utcnow() + timedelta(hours=md.STALE_HOURS + 1))
    assert len(calls) == 2
    assert md.points("US10Y", 10) == [("2026-09-15", 5.02), ("2026-09-16", 5.05)]   # revised, no duplicates


@pytest.mark.asyncio
async def test_a_failed_fetch_keeps_what_is_stored(macro_db, monkeypatch):
    async def ok(fred_id, since):
        return md.parse_fred_csv(CSV)

    async def boom(fred_id, since):
        raise RuntimeError("fred down")
    monkeypatch.setattr(md, "fetch_fred", ok)
    await md.ensure_fresh("WTI")
    monkeypatch.setattr(md, "fetch_fred", boom)
    await md.ensure_fresh("WTI", now=datetime.utcnow() + timedelta(days=2))
    assert len(md.points("WTI", 10)) == 3


def _pts(n=30):
    return [(f"2026-08-{d:02d}", 4.5 + d * 0.01) for d in range(1, n + 1)]


def test_card_marks_one_named_episode_and_prints_the_claim_under_the_axis():
    svg = macro_card_svg("美債10年期殖利率", "US10Y", "%", _pts(), "個交易日", "FRED DGS10",
                         event={"date": "2026-08-20", "label": "皓哥 8/20"},
                         claim="財政部擴大回購長債，殖利率反而衝到4.94%，市場在重新定價長期高利率")
    assert svg.count('stroke-dasharray="6 5"') == 1 and "<circle" in svg
    assert svg.count("皓哥 8/20") == 2                     # on the marker and heading the claim
    assert "財政部擴大回購長債" in svg and "30個交易日" in svg and "FRED DGS10" in svg


def test_card_without_event_or_claim_draws_neither_and_needs_two_points():
    svg = macro_card_svg("WTI原油", "WTI", " 美元/桶", _pts(), "個交易日", "FRED DCOILWTICO")
    assert 'stroke-dasharray="6 5"' not in svg and "的說法" not in svg
    with pytest.raises(ValueError):
        macro_card_svg("WTI原油", "WTI", "", _pts(1), "個交易日", "FRED")


def test_every_registered_series_has_a_known_frequency():
    assert all(m["freq"] in md.DEFAULT_POINTS and m["fred"] for m in md.SERIES.values())
