"""Unit tests for bootstrap-only sector registry helpers."""

import logging

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
    sector_redirects,
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


def _sector(exposure_id, display_name, members=None):
    return {
        "exposure_id": exposure_id,
        "display_name": display_name,
        "icon_id": "cpu",
        "color_hex": "#3B82F6",
        "description": "seed description",
        "exposure_type": "theme",
        "members": members or [{"ticker": "2330", "name": "台積電", "market": "TW"}],
        "aliases": [display_name],
        "group": None,
    }


def test_sync_bootstraps_empty_registry_from_fixture(session, monkeypatch):
    monkeypatch.setattr(
        "src.tag_registry._seed_sector_redirects",
        lambda: {"sector_old": "sector_new"},
    )

    new_count = sync_sectors(session, [_sector("sector_new", "New")])

    rows = {
        row.exposure_id: row
        for row in session.query(TagRegistry).filter(TagRegistry.kind == KIND_SECTOR).all()
    }
    assert new_count == 1
    assert rows["sector_new"].tier == TIER_TRENDING
    assert rows["sector_new"].members == [{"ticker": "2330", "name": "台積電", "market": "TW"}]
    assert rows["sector_old"].tier == TIER_HIDDEN
    assert rows["sector_old"].redirect_to == "sector_new"
    assert sector_redirects(session) == {"sector_old": "sector_new"}


def test_sync_non_empty_registry_writes_nothing(session, caplog):
    session.add(TagRegistry(
        slug="sector_existing",
        display_zh="Original",
        tier=TIER_HIDDEN,
        kind=KIND_SECTOR,
        exposure_id="sector_existing",
        description="admin description",
        updated_by="admin:owner@example.com",
    ))
    session.commit()

    with caplog.at_level(logging.INFO):
        new_count = sync_sectors(session, [_sector("sector_new", "New")])

    rows = session.query(TagRegistry).filter(TagRegistry.kind == KIND_SECTOR).all()
    assert new_count == 0
    assert len(rows) == 1
    assert rows[0].exposure_id == "sector_existing"
    assert rows[0].description == "admin description"
    assert "taxonomy managed in DB; seed sync skipped" in caplog.text


def test_hidden_sector_exposure_ids_returns_only_hidden(session):
    session.add(TagRegistry(
        slug="sector_a", display_zh="A", tier=TIER_TRENDING,
        kind=KIND_SECTOR, exposure_id="sector_a",
    ))
    session.add(TagRegistry(
        slug="sector_b", display_zh="B", tier=TIER_HIDDEN,
        kind=KIND_SECTOR, exposure_id="sector_b",
    ))
    session.commit()

    assert hidden_sector_exposure_ids(session) == {"sector_b"}


def test_trending_slugs_excludes_sectors(session):
    session.add(TagRegistry(slug="ai", display_zh="AI", tier=TIER_TRENDING, kind=KIND_TAG))
    session.add(TagRegistry(
        slug="sector_semiconductor",
        display_zh="半導體",
        tier=TIER_TRENDING,
        kind=KIND_SECTOR,
        exposure_id="sector_semiconductor",
    ))
    session.commit()

    slugs = trending_slugs(session)
    assert "ai" in slugs
    assert "sector_semiconductor" not in slugs


def test_canonical_tag_slugs_gates_junk():
    from src.tag_registry import canonical_tag_slugs

    vocab = canonical_tag_slugs()
    assert len(vocab) > 100
    assert "twstocks" in vocab
    assert "taiwanstocks" not in vocab
    assert "000660" not in vocab


def test_hidden_tag_slugs_normalized_and_tag_only(session):
    session.add(TagRegistry(slug="Supply_Chain", display_zh="供應鏈", tier=TIER_HIDDEN, kind=KIND_TAG))
    session.add(TagRegistry(slug="ai", display_zh="AI", tier=TIER_TRENDING, kind=KIND_TAG))
    session.add(TagRegistry(
        slug="sector_semiconductor",
        display_zh="半導體",
        tier=TIER_HIDDEN,
        kind=KIND_SECTOR,
        exposure_id="sector_semiconductor",
    ))
    session.commit()

    hidden = hidden_tag_slugs(session)
    assert "supplychain" in hidden
    assert "ai" not in hidden
    assert "sectorsemiconductor" not in hidden


def test_served_ids_allowlist_excludes_deleted_and_redirects(session):
    """TKB-009: a DELETEd registry row must not resurrect on the board — allowlist
    serves only present, non-hidden, non-redirect rows."""
    from src.tag_registry import served_sector_exposure_ids
    sync_sectors(session, [
        _sector("sector_a", "A"),
        _sector("sector_b", "B"),
    ])
    rows = {r.exposure_id: r for r in session.query(TagRegistry).all()}
    rows["sector_b"].tier = TIER_HIDDEN
    session.add(TagRegistry(
        slug="sector_old", display_zh="舊", kind=KIND_SECTOR,
        exposure_id="sector_old", tier="trending", redirect_to="sector_a",
    ))
    session.commit()

    served = served_sector_exposure_ids(session)
    assert served == {"sector_a"}  # hidden + redirect stub excluded
    # 'sector_memory'-style deleted/absent ids are excluded by construction:
    assert "sector_memory" not in served


def test_served_ids_none_on_empty_registry(session):
    """Bootstrap window: empty registry → None, callers fall back to blocklist."""
    from src.tag_registry import served_sector_exposure_ids
    assert served_sector_exposure_ids(session) is None
