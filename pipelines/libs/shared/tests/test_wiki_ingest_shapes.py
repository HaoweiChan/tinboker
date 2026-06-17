"""Regression tests for shape-tolerant ``ticker_insights`` handling in
``shared.wiki_builder.ingest.ingest_episode``.

The summarizer emits ``ticker_insights`` as either a bare ``list`` of row dicts
or a ``{"ticker_insights"|"ticker_recommendations": [...]}`` wrapper. A bare list
used to crash the wiki ingest with ``'list' object has no attribute 'get'``
(seen on Gooaye 股癌 EP671 / ``Gooaye_6a770ffa1bab6927``) — every other pipeline
step tolerated it, so the episode persisted everywhere except the wiki.
"""

from shared.wiki_builder import InMemoryWikiRepository, ingest_episode


def _rec(ticker: str, sentiment: str = "bull") -> dict:
    return {
        "ticker": ticker,
        "sentiment": sentiment,
        "sentiment_score": 7,
        "time_horizon": "中期",
        "bluf_thesis": f"thesis for {ticker}",
    }


def _ingest(repo: InMemoryWikiRepository, ticker_insights):
    return ingest_episode(
        podcast_name="股癌",
        episode_number=671,
        title="EP671",
        date="2026-06-17",
        tickers=["2330.TW", "NVDA"],
        tags=["半導體"],
        summary_text="s",
        ticker_insights=ticker_insights,
        repository=repo,
    )


def _ticker_history_present(repo: InMemoryWikiRepository, slug: str) -> bool:
    page = repo.get_page("entity", slug)
    return page is not None and "## Ticker History" in page.body


def test_ingest_episode_accepts_bare_list():
    """EP671 repro: ticker_insights as a bare list must not raise and must still
    populate per-entity Ticker History rows."""
    repo = InMemoryWikiRepository()
    page = _ingest(repo, [_rec("2330.TW"), _rec("NVDA", "bear")])
    assert page.kind == "episode"
    assert _ticker_history_present(repo, "2330")
    assert _ticker_history_present(repo, "nvda")


def test_ingest_episode_accepts_wrapper_dict():
    repo = InMemoryWikiRepository()
    _ingest(repo, {"ticker_insights": [_rec("2330.TW")]})
    assert _ticker_history_present(repo, "2330")


def test_ingest_episode_accepts_legacy_recommendations_key():
    repo = InMemoryWikiRepository()
    _ingest(repo, {"ticker_recommendations": [_rec("2330.TW")]})
    assert _ticker_history_present(repo, "2330")


def test_ingest_episode_tolerates_none_and_junk_shapes():
    """None, empty, and non-dict rows must be ignored without raising."""
    for payload in (None, [], {}, "garbage", [None, "x", 3], {"ticker_insights": None}):
        repo = InMemoryWikiRepository()
        page = _ingest(repo, payload)
        assert page.kind == "episode"
        # No insight rows -> no Ticker History section.
        assert not _ticker_history_present(repo, "2330")
