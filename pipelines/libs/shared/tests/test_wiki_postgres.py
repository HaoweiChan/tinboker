"""Postgres WikiRepository integration tests.

Skipped unless ``WIKI_TEST_DATABASE_URL`` (or ``WIKI_DATABASE_URL``) points at a
reachable Postgres. The schema is created/dropped per test session.
"""

import os
import uuid

import pytest

DB_URL = os.environ.get("WIKI_TEST_DATABASE_URL") or os.environ.get("WIKI_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL, reason="set WIKI_TEST_DATABASE_URL to run Postgres wiki tests"
)


@pytest.fixture()
def repo():
    from shared.wiki_builder.postgres_repo import PostgresWikiRepository, metadata

    r = PostgresWikiRepository(DB_URL)
    metadata.drop_all(r.engine)
    r.init_schema()
    yield r
    metadata.drop_all(r.engine)


def test_postgres_crud_and_links(repo):
    from shared.wiki_builder import WikiPage, ingest_episode

    assert repo.health()["status"] == "healthy"
    ep = ingest_episode(
        podcast_name="Gooaye", episode_number=int(str(uuid.uuid4().int)[:6]),
        title="EP", date="2026-05-12", tickers=["TSM", "2330"], tags=["ai-bubble"],
        summary_text="sum",
        ticker_recommendations={
            "ticker_recommendations": [
                {"ticker": "TSM", "sentiment": "bull", "sentiment_score": 9, "bluf_thesis": "great"}
            ]
        },
        repository=repo,
    )
    assert repo.get_page("episode", ep.slug) is not None
    kinds = {(p.kind, p.slug) for p in repo.list_pages()}
    assert ("entity", "tsm") in kinds and ("topic", "ai-bubble") in kinds
    assert [(link.dst_kind, link.dst_slug) for link in repo.list_links(src=("episode", ep.slug))]
    matching = repo.list_pages(kind="episode", frontmatter_filter={"tickers": "TSM"})
    assert [p.slug for p in matching] == [ep.slug]
    assert "## Ticker History" in repo.get_page("entity", "tsm").body

    # update preserves created_at
    before = repo.get_page("episode", ep.slug)
    after = repo.upsert_page(WikiPage(kind="episode", slug=ep.slug, title="EP!", body="# EP!\n"))
    assert after.created_at == before.created_at and after.title == "EP!"

    # delete cascades links
    assert repo.delete_page("episode", ep.slug) is True
    assert repo.list_links(src=("episode", ep.slug)) == []
