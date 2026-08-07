from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.data.sector_reasons import invalidate_reasons_cache, reason_for
from src.database import postgres
from src.database.models import TagRegistry
from src.tag_registry import KIND_SECTOR, TIER_TRENDING


def test_reason_for_reads_registry_and_invalidation_refreshes(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    TagRegistry.__table__.create(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    db.add(TagRegistry(
        slug="sector_hbm",
        display_zh="HBM",
        tier=TIER_TRENDING,
        kind=KIND_SECTOR,
        exposure_id="sector_hbm",
        members=[{"ticker": "6239", "reason": "old reason"}],
    ))
    db.commit()
    monkeypatch.setattr(postgres, "SessionLocal", session_factory)
    invalidate_reasons_cache()

    assert reason_for("sector_hbm", "6239.TW") == "old reason"

    row = db.query(TagRegistry).filter_by(exposure_id="sector_hbm").one()
    row.members = [{"ticker": "6239", "reason": "new reason"}]
    db.commit()
    assert reason_for("sector_hbm", "6239") == "old reason"

    invalidate_reasons_cache()
    assert reason_for("sector_hbm", "6239") == "new reason"
    db.close()
