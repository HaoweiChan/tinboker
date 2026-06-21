"""Unit tests for the unified topic registry's sector helpers.

sync_sectors() indexes pipeline-universe sectors into the shared tag_registry so admins
can curate their visibility alongside tags. New sectors default to VISIBLE (trending) so a
first sync never empties the live board; existing rows refresh display/visuals but keep
their curated tier. hidden_sector_exposure_ids() / trending_slugs() back the board gate and
the tag-only trending cloud respectively.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import TagRegistry
from src.tag_registry import (
    KIND_SECTOR,
    KIND_TAG,
    TIER_HIDDEN,
    TIER_TRENDING,
    hidden_sector_exposure_ids,
    hidden_tag_slugs,
    sync_sectors,
    trending_slugs,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    TagRegistry.__table__.create(bind=engine)
    db = sessionmaker(bind=engine)()
    yield db
    db.close()


def _sector(exposure_id, display_name, icon_id="cpu", color_hex="#3B82F6"):
    return {
        "exposure_id": exposure_id,
        "display_name": display_name,
        "icon_id": icon_id,
        "color_hex": color_hex,
        "count": 5,
    }


def test_sync_inserts_new_sectors_as_visible(session):
    sectors = [
        _sector("sector_semiconductor", "半導體"),
        _sector("theme_ai_server", "AI 伺服器"),
    ]
    new_count = sync_sectors(session, sectors)
    assert new_count == 2

    rows = session.query(TagRegistry).filter(TagRegistry.kind == KIND_SECTOR).all()
    assert len(rows) == 2
    for r in rows:
        assert r.tier == TIER_TRENDING  # visible by default
        assert r.exposure_id == r.slug
        assert r.icon_id and r.color_hex


def test_resync_refreshes_visuals_but_preserves_curated_tier(session):
    sync_sectors(session, [_sector("sector_semiconductor", "半導體", icon_id="cpu")])
    # Admin hides it.
    row = session.query(TagRegistry).filter_by(exposure_id="sector_semiconductor").one()
    row.tier = TIER_HIDDEN
    session.commit()

    # Re-sync with refreshed display name + visuals.
    new_count = sync_sectors(session, [_sector("sector_semiconductor", "半導體業", icon_id="circuit-board")])
    assert new_count == 0  # not a new row

    row = session.query(TagRegistry).filter_by(exposure_id="sector_semiconductor").one()
    assert row.tier == TIER_HIDDEN          # curation preserved
    assert row.display_zh == "半導體業"      # display refreshed
    assert row.icon_id == "circuit-board"   # visual refreshed


def test_hidden_sector_exposure_ids_returns_only_hidden(session):
    sync_sectors(session, [
        _sector("sector_a", "A"),
        _sector("sector_b", "B"),
    ])
    session.query(TagRegistry).filter_by(exposure_id="sector_b").one().tier = TIER_HIDDEN
    session.commit()

    assert hidden_sector_exposure_ids(session) == {"sector_b"}


def test_trending_slugs_excludes_sectors(session):
    session.add(TagRegistry(slug="ai", display_zh="AI", tier=TIER_TRENDING, kind=KIND_TAG))
    session.commit()
    sync_sectors(session, [_sector("sector_semiconductor", "半導體")])  # trending, but a sector

    slugs = trending_slugs(session)
    assert "ai" in slugs
    assert "sector_semiconductor" not in slugs


def test_hidden_tag_slugs_normalized_and_tag_only(session):
    # A hidden tag (mixed spelling) → normalized; a visible tag and a hidden sector excluded.
    session.add(TagRegistry(slug="Supply_Chain", display_zh="供應鏈", tier=TIER_HIDDEN, kind=KIND_TAG))
    session.add(TagRegistry(slug="ai", display_zh="AI", tier=TIER_TRENDING, kind=KIND_TAG))
    session.commit()
    sync_sectors(session, [_sector("sector_semiconductor", "半導體")])
    session.query(TagRegistry).filter_by(exposure_id="sector_semiconductor").one().tier = TIER_HIDDEN
    session.commit()

    hidden = hidden_tag_slugs(session)
    assert "supplychain" in hidden          # normalized (strips case + underscore)
    assert "ai" not in hidden               # visible tag not hidden
    assert "sectorsemiconductor" not in hidden  # sectors are not tag-kind
