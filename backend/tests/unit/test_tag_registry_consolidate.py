"""consolidate_tag_registry() merges duplicate case/separator tag rows (ai/AI,
ai_chip/aichip) onto one canonical normalized row, carrying admin 'hidden' curation,
and drops CJK-only slugs that normalize to an empty key."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import TagRegistry
from src.tag_registry import (
    KIND_TAG,
    TIER_HIDDEN,
    TIER_TRENDING,
    consolidate_tag_registry,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    TagRegistry.__table__.create(bind=engine)
    db = sessionmaker(bind=engine)()
    yield db
    db.close()


def _tag(slug, display, tier=TIER_TRENDING):
    return TagRegistry(slug=slug, display_zh=display, tier=tier, kind=KIND_TAG)


def test_consolidate_merges_case_and_separator_dups(session):
    session.add_all([
        _tag("ai", "AI"),                       # canonical, trending, has episodes
        _tag("AI", "AI"),                       # case dup -> drop
        _tag("ai_chip", "AI 晶片", TIER_HIDDEN),  # separator variant, admin-hidden
        _tag("aichip", "aichip"),               # canonical spelling but English placeholder
        _tag("半導體", "半導體"),                  # CJK-only slug -> normalizes to "" -> junk
        _tag("memory", "記憶體"),                 # already canonical, untouched
    ])
    session.commit()

    removed = consolidate_tag_registry(session)
    assert removed == 3  # AI, ai_chip(merged), 半導體

    rows = {r.slug: r for r in session.query(TagRegistry).all()}
    assert set(rows) == {"ai", "aichip", "memory"}
    # ai/AI collapsed, stays trending
    assert rows["ai"].tier == TIER_TRENDING
    # ai_chip(hidden) + aichip merged -> survivor 'aichip', hidden carried, real label kept
    assert rows["aichip"].tier == TIER_HIDDEN
    assert rows["aichip"].display_zh == "AI 晶片"
    # idempotent
    assert consolidate_tag_registry(session) == 0
