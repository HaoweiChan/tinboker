"""Tests for the Phase 2 /api/wiki/claims + /api/wiki/contradictions routes."""

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.wiki_builder import InMemoryWikiRepository, ingest_news_article  # noqa: E402
from src.routers import wiki  # noqa: E402


@pytest.fixture()
def client():
    repo = InMemoryWikiRepository()
    app = FastAPI()
    app.include_router(wiki.router)
    app.dependency_overrides[wiki.get_repo] = lambda: repo
    return TestClient(app), repo


def _news(repo, *, url, date, subject, symbol, name, predicate, obj, event_type,
          conf=0.8, checker=None):
    return ingest_news_article(
        repository=repo,
        url=url,
        title=f"Article {url}",
        source="Test Source",
        date=date,
        content_hash=url,
        paragraphs=[{"index": 0, "hash": "p0", "text": "Body text."}],
        claims=[
            {
                "subject": subject,
                "predicate": predicate,
                "object": obj,
                "event_type": event_type,
                "sentiment": "bull",
                "confidence": conf,
                "source_url": url,
                "paragraph_index": 0,
                "paragraph_hash": "p0",
                "quote": "supporting quote",
            }
        ],
        tags=["markets"],
        entities=[{"slug": subject, "symbol": symbol, "name": name, "type": "company"}],
        conflict_checker=checker,
    )


def test_list_claims_flattens_across_articles(client):
    c, repo = client
    _news(repo, url="https://n/1", date="2026-05-01", subject="2330", symbol="2330",
          name="TSMC", predicate="raised guidance", obj="$40B", event_type="guidance")
    _news(repo, url="https://n/2", date="2026-05-05", subject="nvda", symbol="NVDA",
          name="NVIDIA", predicate="beat earnings", obj="Q1 results", event_type="earnings")
    body = c.get("/api/wiki/claims").json()
    assert body["total"] == 2
    assert body["claims"][0]["article_date"] == "2026-05-05"  # newest first


def test_claims_filters_by_ticker_event_type_and_date(client):
    c, repo = client
    _news(repo, url="https://n/1", date="2026-05-01", subject="2330", symbol="2330",
          name="TSMC", predicate="raised guidance", obj="$40B", event_type="guidance")
    _news(repo, url="https://n/2", date="2026-05-15", subject="nvda", symbol="NVDA",
          name="NVIDIA", predicate="beat earnings", obj="Q1 results", event_type="earnings")
    assert c.get("/api/wiki/claims", params={"ticker": "2330.TW"}).json()["total"] == 1
    assert c.get("/api/wiki/claims", params={"event_type": "earnings"}).json()["total"] == 1
    assert c.get("/api/wiki/claims", params={"date_from": "2026-05-10"}).json()["total"] == 1


def test_claims_status_filter_reflects_supersession(client):
    c, repo = client
    _news(repo, url="https://n/1", date="2026-05-01", subject="2330", symbol="2330",
          name="TSMC", predicate="set capex guidance", obj="$40B", event_type="guidance",
          conf=0.7, checker=lambda a, b: True)
    _news(repo, url="https://n/2", date="2026-05-10", subject="2330", symbol="2330",
          name="TSMC", predicate="set capex guidance", obj="$44B", event_type="guidance",
          conf=0.9, checker=lambda a, b: True)
    assert c.get("/api/wiki/claims", params={"status": "superseded"}).json()["total"] == 1
    assert c.get("/api/wiki/claims", params={"status": "active"}).json()["total"] == 1


def test_contradictions_listing_and_ticker_filter(client):
    c, repo = client
    _news(repo, url="https://n/1", date="2026-05-01", subject="2330", symbol="2330",
          name="TSMC", predicate="set capex guidance", obj="$40B", event_type="guidance",
          conf=0.7, checker=lambda a, b: True)
    _news(repo, url="https://n/2", date="2026-05-10", subject="2330", symbol="2330",
          name="TSMC", predicate="set capex guidance", obj="$44B", event_type="guidance",
          conf=0.9, checker=lambda a, b: True)
    body = c.get("/api/wiki/contradictions").json()
    assert body["total"] == 1
    assert body["contradictions"][0]["entity_slug"] == "2330"
    assert body["contradictions"][0]["type"] == "news_vs_news"
    assert c.get("/api/wiki/contradictions", params={"ticker": "NVDA"}).json()["total"] == 0
    assert c.get("/api/wiki/contradictions", params={"ticker": "2330.TW"}).json()["total"] == 1


def test_contradictions_empty(client):
    c, _ = client
    assert c.get("/api/wiki/contradictions").json()["total"] == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
