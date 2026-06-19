"""Unit tests for the trending_tickers aggregation.

Covers spec § 5 invariants: rolling 30d/90d/all_time counts, sentiment_label
derived from the average score, podcaster/episode tallies, and ordering.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.podcast.exporters.trending_tickers import (
    aggregate_trending,
    market_collision_doc_ids,
    touched_ticker_markets,
    validate_trending_document,
)

_NOW = datetime(2026, 5, 14, 0, 0, tzinfo=timezone.utc)


def _insight(
    ticker: str,
    score: float,
    days_ago: int,
    podcaster: str,
    episode_id: str,
    market: str | None = None,
):
    launch = _NOW - timedelta(days=days_ago)
    row = {
        "ticker": ticker,
        "sentiment_score": score,
        "podcaster": podcaster,
        "podcast_launch_time": launch.isoformat().replace("+00:00", "Z"),
        "episode_id": episode_id,
    }
    if market:
        row["market"] = market
    return row


def test_rolling_windows_count_correctly():
    rows = [
        _insight("NVDA", 0.85, days_ago=5, podcaster="股癌", episode_id="e1"),
        _insight("NVDA", 0.80, days_ago=40, podcaster="股癌", episode_id="e2"),
        _insight("NVDA", 0.75, days_ago=200, podcaster="M觀點", episode_id="e3"),
    ]
    docs = aggregate_trending(rows, now=_NOW)
    assert docs["NVDA"]["count_30d"] == 1
    assert docs["NVDA"]["count_90d"] == 2
    assert docs["NVDA"]["count_all_time"] == 3


def test_sentiment_label_uses_average_across_mentions():
    rows = [
        _insight("AMD", 0.95, days_ago=10, podcaster="股癌", episode_id="e1"),
        _insight("AMD", 0.65, days_ago=20, podcaster="股癌", episode_id="e2"),
    ]
    docs = aggregate_trending(rows, now=_NOW)
    # avg = 0.80 → STRONG_BULLISH per spec § 4.2
    assert docs["AMD"]["sentiment_label"] == "STRONG_BULLISH"
    assert docs["AMD"]["sentiment_score"] == 0.80


def test_top_podcasters_sorted_desc_by_count():
    rows = [
        _insight("TSM", 0.7, days_ago=1, podcaster="股癌", episode_id="e1"),
        _insight("TSM", 0.7, days_ago=2, podcaster="股癌", episode_id="e2"),
        _insight("TSM", 0.7, days_ago=3, podcaster="股癌", episode_id="e3"),
        _insight("TSM", 0.7, days_ago=4, podcaster="M觀點", episode_id="e4"),
        _insight("TSM", 0.7, days_ago=5, podcaster="財經一路發", episode_id="e5"),
    ]
    docs = aggregate_trending(rows, now=_NOW, top_n=3)
    podcasters = docs["TSM"]["top_podcasters"]
    assert podcasters[0] == {"name": "股癌", "count": 3}
    assert podcasters[1]["count"] == 1
    assert podcasters[2]["count"] == 1
    assert len(podcasters) == 3


def test_top_episodes_most_recent_first():
    rows = [
        _insight("MSFT", 0.7, days_ago=10, podcaster="股癌", episode_id="old"),
        _insight("MSFT", 0.7, days_ago=2, podcaster="股癌", episode_id="recent"),
        _insight("MSFT", 0.7, days_ago=5, podcaster="股癌", episode_id="middle"),
    ]
    docs = aggregate_trending(rows, now=_NOW, top_n=2)
    ids = [ep["episode_id"] for ep in docs["MSFT"]["top_episodes"]]
    assert ids == ["recent", "middle"]


def test_last_mentioned_is_max_launch_time():
    rows = [
        _insight("AAPL", 0.5, days_ago=30, podcaster="股癌", episode_id="e1"),
        _insight("AAPL", 0.5, days_ago=2, podcaster="股癌", episode_id="e2"),
    ]
    docs = aggregate_trending(rows, now=_NOW)
    expected = (_NOW - timedelta(days=2)).isoformat().replace("+00:00", "Z")
    assert docs["AAPL"]["last_mentioned"] == expected


def test_skips_rows_without_ticker():
    rows = [
        {"sentiment_score": 0.7, "podcaster": "x", "podcast_launch_time": _NOW.isoformat()},
        _insight("GOOG", 0.7, days_ago=1, podcaster="x", episode_id="e1"),
    ]
    docs = aggregate_trending(rows, now=_NOW)
    assert set(docs) == {"GOOG"}


def test_aggregates_by_ticker_and_market_metadata():
    rows = [
        _insight("TSM", 0.7, 1, "股癌", "us", market="US"),
        _insight("2330", 0.8, 1, "股癌", "tw", market="TW"),
    ]
    docs = aggregate_trending(rows, now=_NOW)
    assert docs["TSM"]["market"] == "US"
    assert docs["2330.TW"]["ticker"] == "2330"
    assert docs["2330.TW"]["market"] == "TW"


def test_collision_keeps_us_doc_id_exact_and_suffixes_non_us():
    rows = [
        _insight("ABC", 0.7, 1, "股癌", "us", market="US"),
        _insight("ABC", 0.6, 1, "股癌", "tw", market="TW"),
    ]
    docs = aggregate_trending(rows, now=_NOW)
    assert "ABC" in docs
    assert docs["ABC"]["market"] == "US"
    assert docs["ABC.TW"]["ticker"] == "ABC"
    assert docs["ABC.TW"]["market"] == "TW"


def test_non_us_doc_id_is_always_suffixed_even_without_collision():
    docs = aggregate_trending(
        [_insight("2330", 0.8, 1, "股癌", "tw", market="TW")],
        now=_NOW,
    )
    assert set(docs) == {"2330.TW"}


def test_market_validation_rejects_unknown_market_tokens():
    rows = [
        _insight("X1", 0.6, 1, "股癌", "unknown"),
    ]
    try:
        market_collision_doc_ids(rows)
    except ValueError as exc:
        assert "unknown market" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected collision validation failure")


def test_touched_ticker_markets_infers_legacy_market_shape():
    rows = [
        _insight("NVDA", 0.7, 1, "股癌", "e1"),
        _insight("2330", 0.6, 1, "股癌", "e2"),
    ]
    assert touched_ticker_markets(rows) == {("NVDA", "US"), ("2330", "TW")}


def test_invalid_trending_document_is_rejected_before_write():
    assert validate_trending_document("NVDA", {"ticker": "NVDA", "market": "US"})
    assert validate_trending_document("2330.TW", {"ticker": "2330", "market": "TW"})
    assert not validate_trending_document("2330", {"ticker": "2330", "market": "TW"})
    assert not validate_trending_document("X1", {"ticker": "X1"})
