"""Tests for the /api/wiki/news FastAPI routes (in-memory repository)."""

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.wiki_builder import (  # noqa: E402
    InMemoryWikiRepository,
    ingest_episode,
    ingest_news_article,
)
from src.routers import wiki  # noqa: E402


@pytest.fixture()
def client():
    repo = InMemoryWikiRepository()
    app = FastAPI()
    app.include_router(wiki.router)
    app.dependency_overrides[wiki.get_repo] = lambda: repo
    return TestClient(app), repo


def _ingest(repo, **overrides):
    base = dict(
        url="https://news.test/a",
        title="Article A",
        source="Test Source",
        date="2026-05-20",
        content_hash="hash-a",
        paragraphs=[{"index": 0, "hash": "p0", "text": "TSMC raised guidance."}],
        claims=[
            {
                "subject": "2330",
                "predicate": "raised guidance",
                "object": "$44B",
                "event_type": "guidance",
                "sentiment": "bull",
                "confidence": 0.8,
                "source_url": "https://news.test/a",
                "paragraph_index": 0,
                "paragraph_hash": "p0",
                "quote": "TSMC raised guidance.",
            }
        ],
        tags=["semiconductors"],
        entities=[{"slug": "2330", "symbol": "2330", "name": "台積電", "type": "company"}],
        repository=repo,
    )
    base.update(overrides)
    return ingest_news_article(**base)


def test_list_news_empty(client):
    c, _ = client
    body = c.get("/api/wiki/news").json()
    assert body["total"] == 0 and body["articles"] == []


def test_list_news_is_date_sorted_newest_first(client):
    c, repo = client
    _ingest(repo, url="https://news.test/old", date="2026-05-01", content_hash="h1")
    _ingest(repo, url="https://news.test/new", date="2026-05-20", content_hash="h2")
    articles = c.get("/api/wiki/news").json()["articles"]
    assert [a["date"] for a in articles] == ["2026-05-20", "2026-05-01"]


def test_news_detail_returns_claims_with_citations(client):
    c, repo = client
    page = _ingest(repo)
    detail = c.get(f"/api/wiki/news/{page.slug}").json()
    assert detail["claim_count"] == 1
    claim = detail["claims"][0]
    assert claim["source_url"] == "https://news.test/a"
    assert claim["paragraph_hash"] == "p0"
    assert claim["quote"] == "TSMC raised guidance."
    assert detail["paragraphs"][0]["hash"] == "p0"


def test_news_detail_404_for_missing_slug(client):
    c, _ = client
    assert c.get("/api/wiki/news/news-doesnotexist").status_code == 404


def test_news_filters(client):
    c, repo = client
    _ingest(repo, url="https://news.test/tsmc", content_hash="h1", date="2026-05-10")
    _ingest(
        repo,
        url="https://news.test/nvda",
        content_hash="h2",
        date="2026-05-15",
        source="Other Source",
        claims=[
            {
                "subject": "nvda",
                "predicate": "beat",
                "object": "estimates",
                "event_type": "earnings",
                "sentiment": "bull",
                "source_url": "https://news.test/nvda",
                "paragraph_index": 0,
                "quote": "NVIDIA beat estimates.",
            }
        ],
        entities=[{"slug": "nvda", "symbol": "NVDA", "name": "輝達", "type": "company"}],
    )
    assert c.get("/api/wiki/news", params={"ticker": "2330.TW"}).json()["total"] == 1
    assert c.get("/api/wiki/news", params={"event_type": "earnings"}).json()["total"] == 1
    assert c.get("/api/wiki/news", params={"source": "Other Source"}).json()["total"] == 1
    ranged = c.get(
        "/api/wiki/news", params={"date_from": "2026-05-12", "date_to": "2026-05-20"}
    ).json()
    assert ranged["total"] == 1 and ranged["articles"][0]["date"] == "2026-05-15"


def test_list_news_pagination(client):
    c, repo = client
    for i in range(5):
        _ingest(repo, url=f"https://news.test/{i}", content_hash=f"h{i}", date=f"2026-05-1{i}")
    paged = c.get("/api/wiki/news", params={"limit": 2, "offset": 2}).json()
    assert paged["total"] == 5 and len(paged["articles"]) == 2


def test_entity_page_reflects_both_podcast_and_news(client):
    c, repo = client
    ingest_episode(
        podcast_name="Pod",
        episode_number=1,
        title="Episode about TSMC",
        date="2026-05-01",
        tickers=["2330"],
        tags=["semiconductors"],
        summary_text="A podcast about TSMC.",
        repository=repo,
    )
    _ingest(repo)
    entity = c.get("/api/wiki/pages/entity/2330").json()
    assert "## Episode Mentions" in entity["body"]
    assert "## News Mentions" in entity["body"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
