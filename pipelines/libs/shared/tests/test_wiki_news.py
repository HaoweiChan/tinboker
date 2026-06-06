"""Tests for the news-article wiki path: render_news_article_page + ingest_news_article."""

from __future__ import annotations

import pytest
from shared.wiki_builder import (
    InMemoryWikiRepository,
    canonicalize_url,
    ingest_episode,
    ingest_news_article,
    news_slug,
    render_news_article_page,
)


def _article(**overrides):
    base = dict(
        url="https://example.com/tsmc-capex?utm_source=newsletter#top",
        title="TSMC raises 2026 capex guidance",
        source="Example News",
        date="2026-05-20",
        content_hash="hash-v1",
        paragraphs=[
            {"index": 0, "hash": "p0", "text": "TSMC reported strong demand today."},
            {"index": 1, "hash": "p1", "text": "The company raised capex guidance to $44B."},
        ],
        claims=[
            {
                "subject": "2330",
                "predicate": "raised capex guidance",
                "object": "$44 billion for 2026",
                "event_type": "guidance",
                "sentiment": "bull",
                "confidence": 0.85,
                "source_url": "https://example.com/tsmc-capex",
                "paragraph_index": 1,
                "paragraph_hash": "p1",
                "quote": "The company raised capex guidance to $44B.",
            }
        ],
        tags=["semiconductors"],
        entities=[
            {
                "slug": "2330",
                "symbol": "2330",
                "name": "台積電",
                "type": "company",
                "market": "TW",
                "sector": "Semiconductors",
                "aliases": ["TSMC", "Taiwan Semiconductor"],
            }
        ],
    )
    base.update(overrides)
    return base


def test_canonicalize_url_drops_tracking_and_fragment():
    a = canonicalize_url("https://Example.com/a/?utm_source=x&id=7#frag")
    b = canonicalize_url("https://example.com/a?id=7")
    assert a == b


def test_news_slug_is_deterministic():
    url = "https://example.com/story?utm_campaign=z"
    assert news_slug(url) == news_slug("https://example.com/story")
    assert news_slug(url).startswith("news-")


def test_render_news_article_page_shape():
    art = _article()
    page = render_news_article_page(
        url=art["url"],
        title=art["title"],
        source=art["source"],
        date=art["date"],
        content_hash=art["content_hash"],
        tickers=["2330"],
        entity_slugs=["2330"],
        tags=art["tags"],
        claims=art["claims"],
        paragraphs=art["paragraphs"],
    )
    assert page.kind == "news_article"
    assert page.slug == news_slug(art["url"])
    for key in ("url", "source", "date", "content_hash", "tickers", "event_types", "claims",
                "paragraphs", "tags"):
        assert key in page.frontmatter
    assert page.frontmatter["event_types"] == ["guidance"]
    # claim records carry the full akbp-shaped key set
    claim = page.frontmatter["claims"][0]
    for key in ("id", "subject", "predicate", "object", "event_type", "sentiment",
                "confidence", "source_url", "paragraph_index", "paragraph_hash", "quote",
                "status", "superseded_by"):
        assert key in claim
    assert "## Claims" in page.body
    assert "## Related" in page.body
    assert "[[entities/2330]]" in page.body


def test_ingest_news_article_idempotent():
    repo = InMemoryWikiRepository()
    art = _article()
    ingest_news_article(repository=repo, **art)
    ingest_news_article(repository=repo, **art)
    pages = repo.list_pages(kind="news_article")
    assert len(pages) == 1


def test_ingest_news_article_creates_entity_with_aliases_and_claim_index():
    repo = InMemoryWikiRepository()
    ingest_news_article(repository=repo, **_article())
    entity = repo.get_page("entity", "2330")
    assert entity is not None
    assert "## News Mentions" in entity.body
    assert set(["TSMC", "Taiwan Semiconductor"]).issubset(set(entity.frontmatter["aliases"]))
    assert len(entity.frontmatter["claim_index"]) == 1
    assert entity.frontmatter["claim_index"][0]["event_type"] == "guidance"


def test_ingest_news_article_enriches_existing_entity_append_only():
    repo = InMemoryWikiRepository()
    ingest_episode(
        podcast_name="Test Pod",
        episode_number=1,
        title="Episode about TSMC",
        date="2026-05-01",
        tickers=["2330"],
        tags=["semiconductors"],
        summary_text="A podcast discussing TSMC.",
        repository=repo,
    )
    ingest_news_article(repository=repo, **_article())
    entity = repo.get_page("entity", "2330")
    # both source sections coexist — append-only, nothing overwritten
    assert "## Episode Mentions" in entity.body
    assert "## News Mentions" in entity.body
    assert entity.frontmatter["claim_index"][0]["source_url"].startswith("https://example.com")


def test_ingest_news_article_claim_index_replaced_on_reingest():
    repo = InMemoryWikiRepository()
    ingest_news_article(repository=repo, **_article())
    ingest_news_article(repository=repo, **_article())  # same URL again
    entity = repo.get_page("entity", "2330")
    assert len(entity.frontmatter["claim_index"]) == 1  # not duplicated


def test_news_article_link_projection():
    repo = InMemoryWikiRepository()
    art = _article()
    ingest_news_article(repository=repo, **art)
    slug = news_slug(art["url"])
    links = repo.list_links(src=("news_article", slug))
    dsts = {(link.dst_kind, link.dst_slug) for link in links}
    assert ("entity", "2330") in dsts
    assert ("topic", "semiconductors") in dsts


def test_event_type_normalized_to_vocab():
    repo = InMemoryWikiRepository()
    art = _article()
    art["claims"][0]["event_type"] = "Merger & Acquisition"
    ingest_news_article(repository=repo, **art)
    page = repo.list_pages(kind="news_article")[0]
    assert page.frontmatter["claims"][0]["event_type"] == "m_and_a"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
