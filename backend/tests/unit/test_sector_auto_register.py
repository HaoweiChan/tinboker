"""auto_register_sectors(): exposures the episodes use but the registry lacks get a
trending sector row; existing rows (any tier) and redirect sources are untouched."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import TagRegistry
from src.tag_registry import KIND_SECTOR, TIER_HIDDEN, TIER_TRENDING, auto_register_sectors


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    TagRegistry.__table__.create(bind=engine)
    db = sessionmaker(bind=engine)()
    yield db
    db.close()


def test_registers_unknown_exposures_and_leaves_known_alone(session, monkeypatch):
    monkeypatch.setattr("src.tag_registry._seed_sector_redirects", lambda: {"sector_old_memory": "sector_memory"})
    session.add(TagRegistry(slug="sector_mlcc", display_zh="被動元件 MLCC", tier=TIER_HIDDEN, kind=KIND_SECTOR, exposure_id="sector_mlcc"))
    session.commit()

    added = auto_register_sectors(session, [
        {"exposure_id": "sector_mlcc", "display_name": "被動元件 MLCC", "exposure_type": "theme"},   # known (hidden) → untouched
        {"exposure_id": "sector_memory", "display_name": "記憶體", "exposure_type": "industry", "icon_id": "memory-stick", "color_hex": "#EF4444"},
        {"exposure_id": "sector_old_memory", "display_name": "舊記憶體", "exposure_type": "industry"},  # redirect source → skipped
        {"exposure_id": "", "display_name": "junk"},
    ])
    assert added == 1

    rows = {r.exposure_id: r for r in session.query(TagRegistry).all()}
    assert rows["sector_mlcc"].tier == TIER_HIDDEN
    mem = rows["sector_memory"]
    assert (mem.tier, mem.kind, mem.display_zh, mem.exposure_type, mem.icon_id, mem.color_hex) == (
        TIER_TRENDING, KIND_SECTOR, "記憶體", "industry", "memory-stick", "#EF4444")
    assert "sector_old_memory" not in rows

    # Idempotent: a second pass inserts nothing.
    assert auto_register_sectors(session, [{"exposure_id": "sector_memory", "display_name": "記憶體"}]) == 0
