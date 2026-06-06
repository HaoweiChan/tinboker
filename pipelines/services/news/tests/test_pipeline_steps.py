"""Unit tests for news pipeline steps 1-3: fetch_feeds, dedup, extract."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from news.pipeline.article import Article, FeedEntry
from news.pipeline.steps.dedup import dedup, is_duplicate
from news.pipeline.steps.extract import extract, paragraph_hash, split_paragraphs
from news.pipeline.steps.fetch_feeds import fetch_feeds
from shared.wiki_builder import InMemoryWikiRepository, news_slug


# --- fetch_feeds ---------------------------------------------------------
def test_fetch_feeds_parses_entries():
    entries = [
        {
            "link": "https://example.com/story-a",
            "title": "Story A",
            "summary": "Summary of A",
            "published_parsed": time.struct_time((2026, 5, 20, 9, 0, 0, 0, 0, 0)),
        }
    ]
    feeds = [{"name": "Test Feed", "url": "https://feed.example.com/rss"}]
    out = fetch_feeds(feeds, parse=lambda url: SimpleNamespace(entries=entries))
    assert len(out) == 1
    assert out[0].url == "https://example.com/story-a"
    assert out[0].source == "Test Feed"
    assert out[0].published == "2026-05-20"


def test_fetch_feeds_skips_a_failing_feed():
    def parse(url: str):
        if "bad" in url:
            raise RuntimeError("unreachable")
        return SimpleNamespace(entries=[{"link": "https://example.com/ok", "title": "OK"}])

    feeds = [
        {"name": "Bad", "url": "https://bad.example.com/rss"},
        {"name": "Good", "url": "https://good.example.com/rss"},
    ]
    out = fetch_feeds(feeds, parse=parse)
    assert [e.url for e in out] == ["https://example.com/ok"]


def test_fetch_feeds_dedupes_repeated_links():
    entries = [{"link": "https://example.com/dup", "title": "Dup"}] * 3
    out = fetch_feeds(
        [{"name": "F", "url": "u"}], parse=lambda url: SimpleNamespace(entries=entries)
    )
    assert len(out) == 1


# --- dedup ---------------------------------------------------------------
def test_dedup_slug_deterministic_and_collapses_tracking_variants():
    repo = InMemoryWikiRepository()
    e1 = FeedEntry(url="https://example.com/x?utm_source=news", title="X", source="S")
    e2 = FeedEntry(url="https://example.com/x", title="X", source="S")
    articles = dedup([e1, e2], repo)
    assert len(articles) == 1
    assert articles[0].slug == news_slug("https://example.com/x")


def test_dedup_records_existing_content_hash():
    repo = InMemoryWikiRepository()
    from shared.wiki_builder import ingest_news_article

    ingest_news_article(
        repository=repo,
        url="https://example.com/seen",
        title="Seen",
        source="S",
        date="2026-05-01",
        content_hash="hash-abc",
        paragraphs=[],
        claims=[],
        tags=[],
        entities=[],
    )
    articles = dedup([FeedEntry(url="https://example.com/seen", title="Seen", source="S")], repo)
    assert articles[0].existing_content_hash == "hash-abc"


# --- extract -------------------------------------------------------------
def test_paragraph_hash_stable_across_whitespace():
    assert paragraph_hash("hello world") == paragraph_hash("  hello world  ")


def test_split_paragraphs_indexes_and_hashes():
    text = (
        "First paragraph with more than enough length here.\n\n"
        "Second paragraph that is also clearly long enough."
    )
    paras = split_paragraphs(text)
    assert [p.index for p in paras] == [0, 1]
    assert all(p.hash and len(p.hash) == 16 for p in paras)


def test_extract_uses_trafilatura_when_available():
    art = Article(url="https://example.com/a", title="A", source="S")
    extract(
        art,
        fetch=lambda url: "<html>raw</html>",
        extractor=lambda d: (
            "Extracted paragraph one is comfortably long.\n\n"
            "Extracted paragraph two is also long enough."
        ),
    )
    assert len(art.paragraphs) == 2
    assert art.content_hash


def test_extract_falls_back_to_rss_when_fetch_fails():
    art = Article(
        url="https://example.com/a",
        title="A",
        source="S",
        rss_content="<p>This is the RSS body paragraph carrying the article text.</p>",
    )
    extract(art, fetch=lambda url: None)
    assert len(art.paragraphs) == 1
    assert "RSS body" in art.paragraphs[0].text


def test_extract_content_hash_is_stable():
    def run() -> str:
        art = Article(url="https://example.com/a", title="A", source="S")
        extract(
            art,
            fetch=lambda u: "x",
            extractor=lambda d: "A stable paragraph used for hashing checks.",
        )
        return art.content_hash

    assert run() == run()


def test_is_duplicate_detects_unchanged_article():
    art = Article(
        url="https://example.com/a",
        title="A",
        source="S",
        rss_content="<p>Body paragraph long enough to be kept by the splitter.</p>",
    )
    extract(art, fetch=lambda url: None)
    art.existing_content_hash = art.content_hash
    assert is_duplicate(art)
    art.existing_content_hash = "something-else"
    assert not is_duplicate(art)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
