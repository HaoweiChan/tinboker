"""Phase 2 — contradiction detection in ingest_news_article."""

from __future__ import annotations

import pytest
from shared.wiki_builder import (
    InMemoryWikiRepository,
    ingest_episode,
    ingest_news_article,
    news_slug,
)


def _ingest(
    repo,
    *,
    url,
    date,
    obj,
    conf,
    checker=None,
    predicate="set capex guidance",
    sentiment="bull",
    subject="2330",
):
    return ingest_news_article(
        repository=repo,
        url=url,
        title=f"Article {url}",
        source="Test Source",
        date=date,
        content_hash=url,
        paragraphs=[{"index": 0, "hash": "p0", "text": "Article body text."}],
        claims=[
            {
                "subject": subject,
                "predicate": predicate,
                "object": obj,
                "event_type": "guidance",
                "sentiment": sentiment,
                "confidence": conf,
                "source_url": url,
                "paragraph_index": 0,
                "paragraph_hash": "p0",
                "quote": "supporting quote",
            }
        ],
        tags=["semiconductors"],
        entities=[{"slug": subject, "symbol": subject, "name": "TSMC", "type": "company"}],
        conflict_checker=checker,
    )


def test_conflict_detected_supersedes_older_claim():
    repo = InMemoryWikiRepository()
    _ingest(repo, url="https://n/1", date="2026-05-01", obj="$40B for 2026", conf=0.7,
            checker=lambda a, b: True)
    _ingest(repo, url="https://n/2", date="2026-05-10", obj="$44B for 2026", conf=0.9,
            checker=lambda a, b: True)

    entity = repo.get_page("entity", "2330")
    conflicts = entity.frontmatter.get("conflicts") or []
    assert len(conflicts) == 1
    assert conflicts[0]["type"] == "news_vs_news"
    assert conflicts[0]["resolution"] == "superseded"

    art1 = repo.get_page("news_article", news_slug("https://n/1"))
    art2 = repo.get_page("news_article", news_slug("https://n/2"))
    assert art1.frontmatter["claims"][0]["status"] == "superseded"
    assert art1.frontmatter["claims"][0]["superseded_by"]
    assert art2.frontmatter["claims"][0]["status"] == "active"

    statuses = {r["source_slug"]: r["status"] for r in entity.frontmatter["claim_index"]}
    assert statuses[news_slug("https://n/1")] == "superseded"


def test_older_claim_contested_when_newer_has_lower_confidence():
    repo = InMemoryWikiRepository()
    _ingest(repo, url="https://n/1", date="2026-05-01", obj="$40B", conf=0.9,
            checker=lambda a, b: True)
    _ingest(repo, url="https://n/2", date="2026-05-10", obj="$44B", conf=0.5,
            checker=lambda a, b: True)

    entity = repo.get_page("entity", "2330")
    assert entity.frontmatter["conflicts"][0]["resolution"] == "contested"
    art1 = repo.get_page("news_article", news_slug("https://n/1"))
    assert art1.frontmatter["claims"][0]["status"] == "contested"


def test_no_conflict_when_objects_match():
    repo = InMemoryWikiRepository()
    _ingest(repo, url="https://n/1", date="2026-05-01", obj="$44B", conf=0.7,
            checker=lambda a, b: True)
    _ingest(repo, url="https://n/2", date="2026-05-10", obj="$44B", conf=0.9,
            checker=lambda a, b: True)
    assert not (repo.get_page("entity", "2330").frontmatter.get("conflicts"))


def test_no_conflict_when_checker_declines():
    repo = InMemoryWikiRepository()
    _ingest(repo, url="https://n/1", date="2026-05-01", obj="$40B", conf=0.7,
            checker=lambda a, b: False)
    _ingest(repo, url="https://n/2", date="2026-05-10", obj="$44B", conf=0.9,
            checker=lambda a, b: False)
    entity = repo.get_page("entity", "2330")
    assert not entity.frontmatter.get("conflicts")
    art1 = repo.get_page("news_article", news_slug("https://n/1"))
    assert art1.frontmatter["claims"][0]["status"] == "active"


def test_no_conflict_detection_without_checker():
    repo = InMemoryWikiRepository()
    _ingest(repo, url="https://n/1", date="2026-05-01", obj="$40B", conf=0.7, checker=None)
    _ingest(repo, url="https://n/2", date="2026-05-10", obj="$44B", conf=0.9, checker=None)
    entity = repo.get_page("entity", "2330")
    assert not entity.frontmatter.get("conflicts")
    art1 = repo.get_page("news_article", news_slug("https://n/1"))
    assert art1.frontmatter["claims"][0]["status"] == "active"


def test_sentiment_conflict_news_vs_podcast():
    repo = InMemoryWikiRepository()
    ingest_episode(
        podcast_name="Pod",
        episode_number=1,
        title="Bullish on TSMC",
        date="2026-05-01",
        tickers=["2330"],
        tags=["semiconductors"],
        summary_text="A bullish take.",
        ticker_insights={
            "ticker_insights": [{"ticker": "2330", "sentiment": "bullish"}]
        },
        repository=repo,
    )
    _ingest(repo, url="https://n/1", date="2026-05-10", obj="weak outlook", conf=0.8,
            sentiment="bear", checker=lambda a, b: True)

    conflicts = repo.get_page("entity", "2330").frontmatter.get("conflicts") or []
    assert any(c["type"] == "sentiment" for c in conflicts)
    sentiment_conflict = next(c for c in conflicts if c["type"] == "sentiment")
    assert sentiment_conflict["news"]["sentiment"] == "bear"
    assert sentiment_conflict["podcast"]["sentiment"] == "bull"


def test_reingest_does_not_duplicate_conflicts():
    repo = InMemoryWikiRepository()
    _ingest(repo, url="https://n/1", date="2026-05-01", obj="$40B", conf=0.7,
            checker=lambda a, b: True)
    _ingest(repo, url="https://n/2", date="2026-05-10", obj="$44B", conf=0.9,
            checker=lambda a, b: True)
    _ingest(repo, url="https://n/2", date="2026-05-10", obj="$44B", conf=0.9,
            checker=lambda a, b: True)  # re-ingest article 2
    conflicts = repo.get_page("entity", "2330").frontmatter.get("conflicts") or []
    assert len(conflicts) == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
