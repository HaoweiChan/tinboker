"""Canonical podcast RSS feed adapter.

The heavy pipeline and the episode watcher historically read episode metadata
from the third-party ``podcasttomp3.com`` mirror, which lags a show's real feed
by hours. This module parses the canonical podcast RSS (e.g. SoundOn) into the
SAME episode-dict shape the rest of the pipeline already consumes, so a new
episode is visible within minutes of publication instead of hours.

Episode dict shape — matches the podcasttomp3 ``/api/episodes`` contract the
downstream pipeline reads (see ``pipeline.steps.download`` for ``episodeUrl`` and
``pipeline.utils`` / ``orchestrator`` for ``title`` / ``episodeNumber`` /
``datePublished``)::

    {
        "title": str,
        "episodeUrl": str,          # MP3 enclosure URL (downloadable as-is)
        "episodeNumber": int | None,
        "datePublished": str | None,  # ISO-8601 UTC with trailing 'Z'
        "duration": str | None,       # itunes:duration (informational)
        "guid": str | None,
    }

Only ``title``, ``episodeUrl``, ``episodeNumber`` and ``datePublished`` are read
downstream; ``duration``/``guid`` are carried for parity/debuggability.
"""

from __future__ import annotations

import re
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Optional, Union
from xml.etree import ElementTree as ET

import requests

# iTunes podcast namespace (episode number, duration).
_ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"

# "EP670", "EP 670", "Ep.670" -> 670. Leading zeros tolerated.
_EP_NUM_RE = re.compile(r"EP\s*\.?\s*0*(\d+)", re.IGNORECASE)


def _text(elem: Optional[ET.Element]) -> Optional[str]:
    if elem is None:
        return None
    value = (elem.text or "").strip()
    return value or None


def _to_iso_z(pubdate: Optional[str]) -> Optional[str]:
    """RFC-2822 ``pubDate`` -> ISO-8601 UTC with trailing ``Z``.

    Produces the exact shape the feed ``datePublished`` uses elsewhere
    (e.g. ``2026-06-17T06:29:22.000Z``) so ``_parse_episode_date`` and
    ``_date_published_to_ms`` parse it unchanged.
    """
    if not pubdate:
        return None
    try:
        dt = parsedate_to_datetime(pubdate.strip())
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    else:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _episode_number(item: ET.Element, title: Optional[str]) -> Optional[int]:
    # Prefer the explicit <itunes:episode> tag when present.
    raw = _text(item.find(f"{{{_ITUNES_NS}}}episode"))
    if raw and raw.isdigit():
        return int(raw)
    # Fall back to parsing "EP671" from the title (the convention for these shows).
    if title:
        match = _EP_NUM_RE.search(title)
        if match:
            return int(match.group(1))
    return None


def parse_rss_episodes(xml: Union[bytes, str]) -> list[dict]:
    """Parse RSS XML into episode dicts (newest-first, as the feed orders them).

    Accepts bytes (preferred — honours the XML encoding declaration) or str.
    Items without a title or a playable enclosure URL are skipped.
    """
    root = ET.fromstring(xml)
    channel = root.find("channel")
    if channel is None:
        return []

    episodes: list[dict] = []
    for item in channel.findall("item"):
        title = _text(item.find("title"))
        enclosure = item.find("enclosure")
        episode_url = enclosure.get("url") if enclosure is not None else None
        if not title or not episode_url:
            continue
        episodes.append(
            {
                "title": title,
                "episodeUrl": episode_url,
                "episodeNumber": _episode_number(item, title),
                "datePublished": _to_iso_z(_text(item.find("pubDate"))),
                "duration": _text(item.find(f"{{{_ITUNES_NS}}}duration")),
                "guid": _text(item.find("guid")),
            }
        )
    return episodes


def fetch_episodes_from_rss(rss_url: str, *, timeout: int = 30) -> list[dict]:
    """Fetch and parse a podcast RSS feed. Returns ``[]`` on any error.

    This is a lightweight metadata-only fetch (the XML text); it never downloads
    audio. The heavy download/transcribe/summarize work runs only after a caller
    decides an episode is new.
    """
    try:
        resp = requests.get(rss_url, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching RSS feed {rss_url}: {e}")
        return []
    try:
        return parse_rss_episodes(resp.content)
    except ET.ParseError as e:
        print(f"Error parsing RSS feed {rss_url}: {e}")
        return []
