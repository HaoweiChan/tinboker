"""End-to-end pipeline test: feeds → wiki, with HTTP + LLM fully mocked."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from news.orchestrator import run
from shared.wiki_builder import InMemoryWikiRepository

_FIXTURES = [
    {"link": "https://news.test/tsmc", "title": "TSMC guidance update"},
    {"link": "https://news.test/nvda", "title": "NVIDIA earnings beat"},
    {"link": "https://news.test/aapl", "title": "Apple product launch"},
]

_ARTICLE_TEXT = {
    "https://news.test/tsmc": "TSMC raised its 2026 capital expenditure guidance to a record level.",
    "https://news.test/nvda": "NVIDIA reported quarterly earnings that beat analyst expectations.",
    "https://news.test/aapl": "Apple unveiled a brand new product line at its developer event.",
}


def _feeds_file(tmp_path) -> str:
    path = tmp_path / "feeds.json"
    path.write_text(
        json.dumps({"feeds": [{"name": "Test Feed", "url": "https://feed.test/rss"}]}),
        encoding="utf-8",
    )
    return str(path)


def _fake_parse(url: str):
    return SimpleNamespace(entries=_FIXTURES)


def _fake_fetch(url: str) -> str:
    return url  # the "downloaded" payload — _fake_extract maps it back


def _fake_extract(downloaded: str) -> str:
    return _ARTICLE_TEXT[downloaded]


def _fake_llm(system: str, user: str) -> dict:
    if "company-name mentions" in system:  # disambiguation prompt
        return {"resolutions": []}
    if "TSMC" in user:
        subject, event_type = "TSMC", "guidance"
    elif "NVIDIA" in user:
        subject, event_type = "NVIDIA", "earnings"
    else:
        subject, event_type = "Apple", "product"
    return {
        "summary": f"{subject} news summary.",
        "tags": ["semiconductors"],
        "entities": [],
        "claims": [
            {
                "subject": subject,
                "predicate": "did",
                "object": "something notable",
                "event_type": event_type,
                "sentiment": "bull",
                "confidence": 0.8,
                "paragraph_index": 0,
                "quote": user[:60],
            }
        ],
    }


def test_pipeline_ingests_fixture_articles_end_to_end(tmp_path):
    repo = InMemoryWikiRepository()
    summary = run(
        feeds_path=_feeds_file(tmp_path),
        repository=repo,
        parse=_fake_parse,
        fetch=_fake_fetch,
        extractor=_fake_extract,
        llm=_fake_llm,
    )
    assert summary.feed_entries == 3
    assert summary.ingested == 3
    assert summary.failed == 0
    assert len(repo.list_pages(kind="news_article")) == 3
    # shared entity pages gained a News Mentions section
    for slug in ("2330", "nvda", "aapl"):
        entity = repo.get_page("entity", slug)
        assert entity is not None, f"entity/{slug} missing"
        assert "## News Mentions" in entity.body


def test_pipeline_is_best_effort_when_one_article_fails(tmp_path):
    repo = InMemoryWikiRepository()

    def flaky_llm(system: str, user: str) -> dict:
        if "Apple" in user and "company-name mentions" not in system:
            raise RuntimeError("LLM unavailable for this article")
        return _fake_llm(system, user)

    summary = run(
        feeds_path=_feeds_file(tmp_path),
        repository=repo,
        parse=_fake_parse,
        fetch=_fake_fetch,
        extractor=_fake_extract,
        llm=flaky_llm,
    )
    assert summary.ingested == 2
    assert summary.failed == 1
    assert len(repo.list_pages(kind="news_article")) == 2


def test_pipeline_skips_unchanged_articles_on_rerun(tmp_path):
    repo = InMemoryWikiRepository()
    feeds = _feeds_file(tmp_path)
    common = dict(
        repository=repo,
        parse=_fake_parse,
        fetch=_fake_fetch,
        extractor=_fake_extract,
        llm=_fake_llm,
    )
    first = run(feeds_path=feeds, **common)
    second = run(feeds_path=feeds, **common)
    assert first.ingested == 3
    assert second.ingested == 0
    assert second.skipped == 3
    assert len(repo.list_pages(kind="news_article")) == 3


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
