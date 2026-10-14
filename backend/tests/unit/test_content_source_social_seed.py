"""Persist source publishing preferences and repair only the affected seed row."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.data.content_sources_seed import PODCAST_SOURCES
from src.database.models import ContentSource
from src.schemas.content_source import ContentSourceCreate, ContentSourceUpdate
from src.services.content_source_service import ContentSourceService


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    ContentSource.__table__.create(bind=engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def manny_seed():
    return next(source for source in PODCAST_SOURCES if source["name"] == "曼報")


@pytest.mark.parametrize("enabled", [False, True])
def test_create_persists_social_preference(db, enabled):
    service = ContentSourceService(db)
    source = service.create(ContentSourceCreate(**(manny_seed() | {"social_enabled": enabled})))
    db.expire_all()
    assert db.get(ContentSource, source.id).social_enabled is enabled


def test_seed_round_trip_preserves_disabled_social_and_operator_edits(db):
    service = ContentSourceService(db)
    assert service.seed_from_config([manny_seed()]) == 1
    db.expire_all()
    source = service.get_by_type_slug("podcast", "曼報")
    assert source.social_enabled is False
    service.update(source.id, ContentSourceUpdate(social_enabled=True), updated_by="operator")
    assert service.seed_from_config([manny_seed()]) == 0
    assert service.repair_manny_seed_social_setting() == 0
    db.expire_all()
    assert db.get(ContentSource, source.id).social_enabled is True


def test_repair_corrects_existing_bug_once(db):
    service = ContentSourceService(db)
    source = service.create(
        ContentSourceCreate(**(manny_seed() | {"social_enabled": True})),
        updated_by="startup_seed",
    )
    assert service.repair_manny_seed_social_setting() == 1
    db.expire_all()
    assert db.get(ContentSource, source.id).social_enabled is False
    assert source.last_updated_by == "startup_seed_social_repair"
    assert service.repair_manny_seed_social_setting() == 0


@pytest.mark.parametrize("changes", [
    {"name": "Other show"},
    {"feed_url": "https://example.com/feed"},
    {"slug": "other-show"},
    {"source_type": "news"},
])
def test_repair_leaves_other_sources_unchanged(db, changes):
    service = ContentSourceService(db)
    source = service.create(
        ContentSourceCreate(**(manny_seed() | {"social_enabled": True} | changes)),
        updated_by="startup_seed",
    )
    assert service.repair_manny_seed_social_setting() == 0
    db.expire_all()
    assert db.get(ContentSource, source.id).social_enabled is True
