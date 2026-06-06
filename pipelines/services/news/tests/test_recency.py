"""Tests for the recency window + cap in fetch_feeds and the load_feeds path gate."""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

from news.feeds import load_feeds
from news.pipeline.steps.fetch_feeds import _cutoff_date, fetch_feeds


def _entry(link: str, *, days_ago: int | None = None) -> dict:
    e: dict = {"link": link, "title": link}
    if days_ago is not None:
        e["published_parsed"] = time.gmtime(time.time() - days_ago * 86400)
    return e


def test_cutoff_date_disabled_for_missing_or_zero():
    assert _cutoff_date(None) is None
    assert _cutoff_date(0) is None
    assert _cutoff_date("nope") is None
    assert _cutoff_date(30) is not None


def test_fetch_feeds_filters_old_entries_by_lookback():
    entries = [_entry("https://x/new", days_ago=3), _entry("https://x/old", days_ago=90)]
    feeds = [{"name": "F", "url": "u", "lookback_days": 30}]
    out = fetch_feeds(feeds, parse=lambda url: SimpleNamespace(entries=entries))
    assert [e.url for e in out] == ["https://x/new"]


def test_fetch_feeds_keeps_undated_entries_within_window():
    entries = [_entry("https://x/nodate")]  # no published date
    feeds = [{"name": "F", "url": "u", "lookback_days": 30}]
    out = fetch_feeds(feeds, parse=lambda url: SimpleNamespace(entries=entries))
    assert [e.url for e in out] == ["https://x/nodate"]


def test_fetch_feeds_caps_at_max_episodes():
    entries = [_entry(f"https://x/{i}", days_ago=1) for i in range(10)]
    feeds = [{"name": "F", "url": "u", "max_episodes": 3}]
    out = fetch_feeds(feeds, parse=lambda url: SimpleNamespace(entries=entries))
    assert len(out) == 3


def test_load_feeds_explicit_path_reads_file_without_platform(tmp_path, monkeypatch):
    # Even with the platform env set, an explicit path must read the file (no network).
    monkeypatch.setenv("TINBOKER_PLATFORM_API_URL", "https://api.example.com")
    p = tmp_path / "feeds.json"
    p.write_text(
        json.dumps({"feeds": [{"name": "Local", "url": "https://local/rss"}]}),
        encoding="utf-8",
    )
    feeds = load_feeds(str(p))
    assert [f["url"] for f in feeds] == ["https://local/rss"]
