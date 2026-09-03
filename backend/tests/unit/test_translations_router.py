"""Cross-market lookup, so a wrong-market request stops minting a duplicate row.

`GET /translations/{ticker}?market=` auto-created a pending row whenever the caller
guessed the market wrong. That is what put phantom TW rows on Korean codes (000660,
005930) and phantom US rows on Taiwanese ones (2330, 2454, 3443, 3661) — 6 of the 9
duplicated symbols in production. Every consumer then had to tie-break them, and
`shared.tickers.prime_tickers` once resolved that tie the wrong way, relabelling
SK Hynix as Taiwanese.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import StockTranslation
from src.services.translation_service import TranslationService


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
    return row


def test_finds_the_row_under_a_different_market(session):
    _add(session, ticker="000660", market="KR", name_en="SK Hynix",
         name_zh_tw="SK海力士", translation_status="approved")
    found = TranslationService(session).get_any_market("000660")
    assert found is not None and found.market == "KR"


def test_lowercase_input_still_matches(session):
    _add(session, ticker="NVDA", market="US", name_zh_tw="輝達",
         translation_status="approved")
    assert TranslationService(session).get_any_market("nvda").market == "US"


def test_an_approved_row_wins_over_a_pending_stub(session):
    """Otherwise the stub that caused the problem shadows the curated row."""
    _add(session, ticker="2330", market="US", name_en=None, name_zh_tw=None,
         translation_status="pending")
    _add(session, ticker="2330", market="TW", name_en="TSMC", name_zh_tw="台積電",
         translation_status="approved")
    found = TranslationService(session).get_any_market("2330")
    assert (found.market, found.name_zh_tw) == ("TW", "台積電")


def test_an_unknown_symbol_returns_none(session):
    """Genuinely new symbols must still reach the auto-create path."""
    assert TranslationService(session).get_any_market("ZZZZ") is None
