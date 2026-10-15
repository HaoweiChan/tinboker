"""Persist source publishing preferences through create and the insert-only seed."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.data.content_sources_seed import PODCAST_SOURCES
from src.database.models import ContentSource
from src.schemas.content_source import ContentSourceCreate, ContentSourceUpdate
from src.services.content_source_service import ContentSourceService, slugify


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    ContentSource.__table__.create(bind=engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def money_seed():
    return next(source for source in PODCAST_SOURCES if source["name"] == "鈔錢部署｜盧燕俐")


@pytest.mark.parametrize("enabled", [False, True])
def test_create_persists_social_preference(db, enabled):
    service = ContentSourceService(db)
    source = service.create(ContentSourceCreate(**(money_seed() | {"social_enabled": enabled})))
    db.expire_all()
    assert db.get(ContentSource, source.id).social_enabled is enabled


def test_seed_round_trip_preserves_disabled_social_and_operator_edits(db):
    service = ContentSourceService(db)
    assert service.seed_from_config([money_seed()]) == 1
    db.expire_all()
    source = service.get_by_type_slug("podcast", slugify(money_seed()["name"]))
    assert source.social_enabled is False
    service.update(source.id, ContentSourceUpdate(social_enabled=True), updated_by="operator")
    assert service.seed_from_config([money_seed()]) == 0
    db.expire_all()
    assert db.get(ContentSource, source.id).social_enabled is True

