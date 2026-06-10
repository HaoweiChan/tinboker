"""Tests for pipeline Step 5b (wiki ingest) — best-effort, repository-backed."""

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import shared.wiki_builder.ingest as wb_ingest  # noqa: E402
from shared.wiki_builder import InMemoryWikiRepository  # noqa: E402
from src.pipeline.steps.wiki_ingest import ingest_into_wiki  # noqa: E402


def _episode_data(**overrides):
    data = dict(
        api_data={"title": "EP 1 | Test", "episodeNumber": 1},
        podcast_name="Test Pod",
        summary_result={
            "summary_text": "Summary.",
            "events_markdown": "- 2026-05-12: thing",
            "ticker_insights": {
                "ticker_insights": [
                    {
                        "ticker": "TSM",
                        "sentiment": "bullish",
                        "sentiment_score": 8,
                        "bluf_thesis": "good",
                    }
                ]
            },
        },
        gcs_urls={"mp3_url": "gs://b/a.mp3", "transcript_url": "gs://b/a.json"},
        spotify_metadata={"release_date": "2026-05-12"},
        created_time=datetime(2026, 5, 12),
        tickers=["TSM"],
        tags=["ai-bubble"],
    )
    data.update(overrides)
    return SimpleNamespace(**data)


def test_ingest_writes_episode_and_entity_pages(monkeypatch):
    repo = InMemoryWikiRepository()
    monkeypatch.setattr(wb_ingest, "get_repository", lambda: repo)

    ingest_into_wiki(SimpleNamespace(rerun_from=None), SimpleNamespace(), _episode_data())

    assert {(p.kind, p.slug) for p in repo.list_pages()} == {
        ("episode", "test-pod_ep1"),
        ("entity", "tsm"),
        ("topic", "ai-bubble"),
    }
    assert "## Ticker History" in repo.get_page("entity", "tsm").body


def test_skipped_when_rerun_from_is_later_step(monkeypatch):
    repo = InMemoryWikiRepository()
    monkeypatch.setattr(wb_ingest, "get_repository", lambda: repo)

    for stage in ("upload", "validate", "firestore"):
        ingest_into_wiki(SimpleNamespace(rerun_from=stage), SimpleNamespace(), _episode_data())
    assert repo.list_pages() == []


def test_no_summary_is_a_noop(monkeypatch):
    repo = InMemoryWikiRepository()
    monkeypatch.setattr(wb_ingest, "get_repository", lambda: repo)
    episode_data = _episode_data(summary_result=None)
    ingest_into_wiki(SimpleNamespace(rerun_from=None), SimpleNamespace(), episode_data)
    assert repo.list_pages() == []


def test_repository_failure_is_non_fatal(monkeypatch):
    class Boom(InMemoryWikiRepository):
        def upsert_page(self, page):
            raise RuntimeError("db down")

    monkeypatch.setattr(wb_ingest, "get_repository", lambda: Boom())
    # must not raise
    ingest_into_wiki(SimpleNamespace(rerun_from=None), SimpleNamespace(), _episode_data())


def test_runs_with_null_repository(monkeypatch):
    # default factory with WIKI_DATABASE_URL unset -> NullWikiRepository, no error
    monkeypatch.delenv("WIKI_DATABASE_URL", raising=False)
    ingest_into_wiki(SimpleNamespace(rerun_from=None), SimpleNamespace(), _episode_data())
