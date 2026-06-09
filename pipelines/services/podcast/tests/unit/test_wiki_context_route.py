"""Tests for the Phase 3 /api/wiki/context token-budgeted endpoint."""

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


def _news(repo, *, url, date, text, tags=("semiconductors",), phash="np0"):
    return ingest_news_article(
        repository=repo,
        url=url,
        title=f"News {url}",
        source="Test Source",
        date=date,
        content_hash=url,
        paragraphs=[{"index": 0, "hash": phash, "text": text}],
        claims=[
            {
                "subject": "2330",
                "predicate": "reported",
                "object": "results",
                "event_type": "earnings",
                "sentiment": "bull",
                "confidence": 0.9,
                "source_url": url,
                "paragraph_index": 0,
                "paragraph_hash": phash,
                "quote": text,
            }
        ],
        tags=list(tags),
        entities=[{"slug": "2330", "symbol": "2330", "name": "TSMC", "type": "company"}],
    )


def test_context_404_for_unknown_topic(client):
    c, _ = client
    assert c.get("/api/wiki/context", params={"topic": "no-such-topic-xyz"}).status_code == 404


def test_context_gathers_news_and_episode_excerpts(client):
    c, repo = client
    ingest_episode(
        podcast_name="Pod",
        episode_number=1,
        title="TSMC episode",
        date="2026-05-01",
        tickers=["2330"],
        tags=["semiconductors"],
        summary_text="A summary about TSMC capacity, yields and demand outlook.",
        repository=repo,
    )
    _news(repo, url="https://n/1", date="2026-05-10",
          text="TSMC reported record revenue for the quarter on strong AI demand.")

    body = c.get("/api/wiki/context", params={"topic": "semiconductors", "tokens": 5000}).json()
    kinds = {e["page_kind"] for e in body["excerpts"]}
    assert "news_article" in kinds and "episode" in kinds
    assert body["tokens_used"] > 0
    assert body["omitted"]["count"] == 0
    news_excerpt = next(e for e in body["excerpts"] if e["page_kind"] == "news_article")
    assert news_excerpt["paragraph_hash"] == "np0"
    assert news_excerpt["source_url"] == "https://n/1"
    assert "tokens" in news_excerpt


def test_context_respects_token_budget_and_reports_omitted(client):
    c, repo = client
    long_text = "A reasonably long paragraph about semiconductors and chip demand. " * 3
    for i in range(4):
        _news(repo, url=f"https://n/{i}", date=f"2026-05-1{i}", text=long_text, phash=f"np{i}")

    tiny = c.get("/api/wiki/context", params={"topic": "semiconductors", "tokens": 100}).json()
    assert tiny["omitted"]["count"] >= 1
    assert tiny["omitted"]["reason"] == "token budget exceeded"
    assert tiny["tokens_used"] <= 100


def test_context_resolves_a_ticker_to_its_entity(client):
    c, repo = client
    _news(repo, url="https://n/1", date="2026-05-10",
          text="TSMC paragraph text carrying the article content for context.", tags=["chips"])
    body = c.get("/api/wiki/context", params={"topic": "2330.TW"}).json()
    assert any(t["kind"] == "entity" and t["slug"] == "2330" for t in body["resolved_targets"])
    assert len(body["excerpts"]) >= 1


def test_context_excerpts_ranked_newest_first(client):
    c, repo = client
    _news(repo, url="https://n/old", date="2026-05-01", text="Older article paragraph text.",
          phash="hold")
    _news(repo, url="https://n/new", date="2026-05-20", text="Newer article paragraph text.",
          phash="hnew")
    body = c.get("/api/wiki/context", params={"topic": "semiconductors", "tokens": 5000}).json()
    assert body["excerpts"][0]["date"] == "2026-05-20"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
