"""Unit tests for the canonical RSS feed adapter.

The adapter must emit episode dicts in the SAME shape the downstream pipeline
reads from the podcasttomp3 mirror (``title`` / ``episodeUrl`` /
``episodeNumber`` / ``datePublished``), and its ``datePublished`` must parse
with the orchestrator's own date parser unchanged.
"""

from __future__ import annotations

from src.podcast.orchestrator import _parse_episode_date
from src.service.rss_feed import parse_rss_episodes

_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>Gooaye</title>
    <item>
      <title>EP671 | \xf0\x9f\x8c\xbc</title>
      <pubDate>Wed, 17 Jun 2026 06:29:22 GMT</pubDate>
      <itunes:episode>671</itunes:episode>
      <itunes:duration>3046</itunes:duration>
      <guid>abc-671</guid>
      <enclosure url="https://rss.soundon.fm/ep671.mp3" type="audio/mpeg" length="1"/>
    </item>
    <item>
      <title>EP670 no itunes number</title>
      <pubDate>Sat, 13 Jun 2026 07:07:21 GMT</pubDate>
      <enclosure url="https://rss.soundon.fm/ep670.mp3" type="audio/mpeg"/>
    </item>
    <item>
      <title>Trailer without audio</title>
      <pubDate>Fri, 12 Jun 2026 00:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""


def test_parses_core_fields_and_orders_newest_first():
    eps = parse_rss_episodes(_RSS)
    # The enclosure-less item is skipped.
    assert len(eps) == 2
    first = eps[0]
    assert first["title"] == "EP671 | 🌼"
    assert first["episodeUrl"] == "https://rss.soundon.fm/ep671.mp3"
    assert first["episodeNumber"] == 671  # from <itunes:episode>
    assert first["datePublished"] == "2026-06-17T06:29:22.000Z"
    assert first["duration"] == "3046"
    assert first["guid"] == "abc-671"


def test_episode_number_falls_back_to_title():
    eps = parse_rss_episodes(_RSS)
    # Second item has no <itunes:episode>; number is parsed from "EP670 ...".
    assert eps[1]["episodeNumber"] == 670


def test_date_published_is_consumable_by_orchestrator_parser():
    eps = parse_rss_episodes(_RSS)
    dt = _parse_episode_date(eps[0]["datePublished"])
    assert dt is not None
    assert (dt.year, dt.month, dt.day, dt.hour) == (2026, 6, 17, 6)


def test_empty_or_channelless_feed_returns_empty():
    assert parse_rss_episodes(b"<rss><foo/></rss>") == []
