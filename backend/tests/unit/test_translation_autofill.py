"""Unit tests for market-data ticker name autofill (translation_autofill).

Verifies the discovery → autofill path fills zh-TW/English names from FinMind/Massive
without clobbering approved rows or re-calling the API for already-named stubs.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import StockTranslation
from src.services.translation_autofill import autofill_names_for_rows, _needs_name


class _FakeService:
    """Stands in for FinMindAPIService / MassiveAPIService.get_ticker_details."""

    def __init__(self, names: dict[str, str]):
        self.names = names
        self.calls: list[str] = []

    def get_ticker_details(self, ticker: str):
        self.calls.append(ticker)
        name = self.names.get(ticker)
        # Real services echo the bare symbol as `name` when unresolved.
        return {"ticker": ticker, "name": name or ticker}


class _FakeDC:
    def __init__(self, tw: dict[str, str], us: dict[str, str]):
        self.finmind_service = _FakeService(tw)
        self.massive_service = _FakeService(us)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    StockTranslation.__table__.create(bind=engine)
    db = sessionmaker(bind=engine)()
    yield db
    db.close()


def _add(db, **kw):
    row = StockTranslation(**kw)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_autofills_tw_and_us_names(session):
    _add(session, ticker="2330", market="TW", translation_status="pending")
    _add(session, ticker="AAPL", market="US", translation_status="pending")
    dc = _FakeDC(tw={"2330": "台積電"}, us={"AAPL": "Apple Inc."})

    filled = autofill_names_for_rows(session, session.query(StockTranslation).all(), dc=dc)
    assert filled == 2

    tw = session.query(StockTranslation).filter_by(ticker="2330").one()
    assert tw.name_zh_tw == "台積電" and tw.name_en is None
    assert tw.translation_status == "auto"

    us = session.query(StockTranslation).filter_by(ticker="AAPL").one()
    assert us.name_en == "Apple Inc." and us.name_zh_tw is None
    assert us.translation_status == "auto"


def test_does_not_touch_approved_rows(session):
    _add(session, ticker="2317", market="TW", translation_status="approved")
    dc = _FakeDC(tw={"2317": "鴻海"}, us={})

    filled = autofill_names_for_rows(session, session.query(StockTranslation).all(), dc=dc)
    assert filled == 0
    row = session.query(StockTranslation).filter_by(ticker="2317").one()
    assert row.name_zh_tw is None and row.translation_status == "approved"
    assert dc.finmind_service.calls == []  # skipped before any lookup


def test_skips_already_named_rows_without_api_call(session):
    _add(session, ticker="2454", market="TW", name_zh_tw="聯發科", translation_status="auto")
    dc = _FakeDC(tw={"2454": "聯發科"}, us={})

    filled = autofill_names_for_rows(session, session.query(StockTranslation).all(), dc=dc)
    assert filled == 0
    assert dc.finmind_service.calls == []  # no redundant network call


def test_unresolved_ticker_stays_pending(session):
    _add(session, ticker="999999", market="TW", translation_status="pending")
    dc = _FakeDC(tw={}, us={})  # FinMind echoes the symbol → treated as a miss

    filled = autofill_names_for_rows(session, session.query(StockTranslation).all(), dc=dc)
    assert filled == 0
    row = session.query(StockTranslation).filter_by(ticker="999999").one()
    assert row.name_zh_tw is None and row.translation_status == "pending"


def test_needs_name_logic():
    def mk(**kw):
        return StockTranslation(**kw)
    assert _needs_name(mk(ticker="T", market="TW", translation_status="pending")) is True
    assert _needs_name(mk(ticker="T", market="US", translation_status="pending")) is True
    assert _needs_name(mk(ticker="T", market="TW", name_zh_tw="x", translation_status="auto")) is False
    assert _needs_name(mk(ticker="T", market="TW", translation_status="approved")) is False
    # Markets without a FinMind/Massive name source are left to the agent.
    assert _needs_name(mk(ticker="T", market="JP", translation_status="pending")) is False
