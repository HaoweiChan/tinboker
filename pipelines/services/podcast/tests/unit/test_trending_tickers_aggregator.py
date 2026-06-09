"""Unit tests for the trending_tickers aggregation.

Covers spec § 5 invariants: rolling 30d/90d/all_time counts, sentiment_label
derived from the average score, podcaster/episode tallies, and ordering.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.podcast.exporters.trending_tickers import aggregate_trending

_NOW = datetime(2026, 5, 14, 0, 0, tzinfo=timezone.utc)


def _insight(ticker: str, score: float, days_ago: int, podcaster: str, episode_id: str):
    launch = _NOW - timedelta(days=days_ago)
    return {
        "ticker": ticker,
        "sentiment_score": score,
        "podcaster": podcaster,
        "podcast_launch_time": launch.isoformat().replace("+00:00", "Z"),
        "episode_id": episode_id,
    }


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
