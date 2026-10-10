"""News drafting integration: real CLI gates, in-memory wiki, zero paid calls."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from news import drafts
from news.pipeline.article import Article
from news.pipeline.steps.fetch_feeds import fetch_feeds
from news.pipeline.steps.wiki_write import wiki_write
from podcast.content_builder import news_drafts
from shared.wiki_builder import InMemoryWikiRepository, ingest_news_article


@pytest.mark.parametrize("raw,verified", [
    ("Fri, 09 Oct 2026 08:00:00 GMT", True),
    ("2026-10-09T08:00:00+08:00", True),
    ("2026-10-09T08:00:00", False),
    ("2026-10-09", False),
    (None, False),
])
def test_feed_provenance_persists(raw, verified):
    entries = fetch_feeds(
        [{"url": "feed", "region": "US"}],
        parse=lambda _: SimpleNamespace(entries=[{
            "link": "https://example.com/a", "published": raw,
            "updated": "2026-10-09T08:00:00Z",
        }]),
    )
    repo = InMemoryWikiRepository()
    wiki_write(Article.from_feed_entry(entries[0]), repo)
    fm = repo.list_pages(kind="news_article")[0].frontmatter
    assert fm["language"] == "en"
    assert fm["publication_verified"] is verified
    assert bool(fm["published_at"]) is verified


@pytest.fixture
def lane(monkeypatch, tmp_path):
    monkeypatch.setenv("NEWS_THREADS_DRAFTS_ENABLED", "true")
    monkeypatch.setenv("NEWS_THREADS_DRAFTS_CACHE_DIR", str(tmp_path))
    repo = InMemoryWikiRepository()
    page = ingest_news_article(
        url="https://example.com/a", title="Company investment", source="Feed",
        date="2026-10-10", content_hash="hash", claims=[], tags=[],
        paragraphs=[{"index": 0, "text": "A specific investment announcement " * 5}],
        repository=repo, language="en", publication_verified=True,
        published_at=datetime.now(timezone.utc).isoformat(),
    )
    entries = [SimpleNamespace(url="https://example.com/a")]
    state = {"remaining_today": 2, "already_posted_ids": [],
             "already_posted_urls": [], "already_posted_hashes": []}
    request = Mock(side_effect=lambda body=None: state if body is None else {"status": "created"})
    monkeypatch.setattr(drafts, "news_drafts_request", request)
    jev = Mock(return_value={"answers": {key: {"type": "noul", "noul": .9}
                                        for key in news_drafts.QUESTIONS}})
    writer = Mock(return_value={"draft": {"post": "企業宣布新的投資計畫", "evidence_ids": ["0"]}})
    monkeypatch.setattr(news_drafts, "jev", jev)
    monkeypatch.setattr(news_drafts, "write", writer)
    return repo, entries, state, request, jev, writer, page


def test_daily_cap_avoids_paid_calls(lane):
    repo, entries, state, request, jev, writer, _ = lane
    state["remaining_today"] = 0
    assert drafts.stage_news_draft(repo, entries) is None
    jev.assert_not_called()
    writer.assert_not_called()
    assert request.call_count == 1


@pytest.mark.parametrize("key,value", [("already_posted_ids", None),
                                        ("already_posted_urls", "https://example.com/a")])
def test_already_drafted_skipped(lane, key, value):
    repo, entries, state, request, jev, writer, page = lane
    state[key] = [value or page.slug]
    assert drafts.stage_news_draft(repo, entries) is None
    jev.assert_not_called()
    writer.assert_not_called()
    assert request.call_count == 1


def test_selected_draft_handoff(lane):
    repo, entries, _, request, jev, writer, page = lane
    assert drafts.stage_news_draft(repo, entries) == {"status": "created"}
    assert jev.call_count == writer.call_count == 1
    body = request.call_args.args[0]
    assert body["article_id"] == page.slug
    assert body["comment"] == "https://example.com/a"
    assert body["text"] == "企業宣布新的投資計畫"


def test_history_unavailable_skips(lane):
    repo, entries, _, request, jev, writer, _ = lane
    request.side_effect = None
    request.return_value = None
    assert drafts.stage_news_draft(repo, entries) is None
    jev.assert_not_called()
    writer.assert_not_called()
