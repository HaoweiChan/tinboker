"""Unit tests for apply_known_name_corrections.

These rows had an approved zh name belonging to a different company (the English
name disambiguates). The correction is self-deactivating: it only fires while the
row still holds the exact known-wrong value, so it is idempotent and never
overwrites a later human edit.
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
    db.refresh(row)
    return row


def test_fixes_wrong_zh_name(session):
    _add(session, ticker="6285", market="TW", name_en="WNC Corporation",
         name_zh_tw="合勤控", translation_status="approved")
    _add(session, ticker="6147", market="TW", name_en="Chipbond Technology",
         name_zh_tw="精材", translation_status="approved")
    _add(session, ticker="3661", market="TW", name_en="Alchip Technologies",
         name_zh_tw="譜瑞-KY", translation_status="approved")
    _add(session, ticker="3023", market="TW", name_en="SINBON Electronics",
         name_zh_tw="新漢", translation_status="approved")
    _add(session, ticker="2745", market="TW", name_en="(TW stock)",
         name_zh_tw="上銀", translation_status="approved")
    _add(session, ticker="6472", market="TW", name_en="(TW stock)",
         name_zh_tw="閎暉", translation_status="approved")

    fixed = TranslationService(session).apply_known_name_corrections()
    assert fixed == 6
    assert session.query(StockTranslation).filter_by(ticker="6285").one().name_zh_tw == "啟碁"
    assert session.query(StockTranslation).filter_by(ticker="6147").one().name_zh_tw == "頎邦"
    assert session.query(StockTranslation).filter_by(ticker="3661").one().name_zh_tw == "世芯-KY"
    assert session.query(StockTranslation).filter_by(ticker="3023").one().name_zh_tw == "信邦"
    assert session.query(StockTranslation).filter_by(ticker="2745").one().name_zh_tw == "五福"
    assert session.query(StockTranslation).filter_by(ticker="6472").one().name_zh_tw == "保瑞"


def test_idempotent_and_does_not_overwrite_human_edit(session):
    # Already-correct row: no change.
    _add(session, ticker="6285", market="TW", name_en="WNC Corporation",
         name_zh_tw="啟碁", translation_status="approved")
    # A human later set some other value: must NOT be clobbered (only the exact
    # known-wrong "合勤控" triggers a fix).
    _add(session, ticker="6147", market="TW", name_en="Chipbond Technology",
         name_zh_tw="頎邦科技", translation_status="approved")

    svc = TranslationService(session)
    assert svc.apply_known_name_corrections() == 0
    # Re-running stays a no-op.
    assert svc.apply_known_name_corrections() == 0
    assert session.query(StockTranslation).filter_by(ticker="6285").one().name_zh_tw == "啟碁"
    assert session.query(StockTranslation).filter_by(ticker="6147").one().name_zh_tw == "頎邦科技"
