"""Step 1 — fetch RSS feeds and yield candidate articles.

``feedparser`` is injectable (``parse``) so tests run fully offline.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit

from ..article import FeedEntry


def _cutoff_date(lookback_days: Any) -> str | None:
    """YYYY-MM-DD cutoff (today − lookback_days) for the recency window, or None to disable."""
    try:
        days = int(lookback_days)
    except (TypeError, ValueError):
        return None
    if days <= 0:
        return None
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")


def _parse_date(entry: Any) -> str:
    """Best-effort YYYY-MM-DD from a feedparser entry's struct_time fields."""
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                return datetime(*parsed[:6]).strftime("%Y-%m-%d")
            except (TypeError, ValueError):
                continue
    return ""


def _published_timestamp(entry: Any) -> str:
    """Only a raw published date with an explicit timezone proves publication time."""
    raw = entry.get("published")
    if not isinstance(raw, str):
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(raw)
        except (ValueError, TypeError, OverflowError):
            return ""
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return ""
    return parsed.astimezone(timezone.utc).isoformat()


def _entry_content(entry: Any) -> str:
    """The richest article body the feed itself carries (content:encoded)."""
    content = entry.get("content")
    if content and isinstance(content, list) and content[0].get("value"):
        return str(content[0]["value"]).strip()
    return ""


def _entry_image(entry: Any, article_url: str) -> str:
    """Prefer RSS media images over image enclosures; ignore audio/video media."""
    for media in [*(entry.get("media_content") or []), *(entry.get("enclosures") or [])]:
        url = str(media.get("url") or media.get("href") or "").strip()
        content_type = str(media.get("type") or "").lower()
        medium = str(media.get("medium") or "").lower()
        try:
            image_path = urlsplit(url).path.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
            if url and (content_type.startswith("image/") or medium == "image"
                        or (not content_type and not medium and image_path)):
                return urljoin(article_url, url)
        except ValueError:
            continue
    return ""


FEED_TIMEOUT_S = 20
_USER_AGENT = "Mozilla/5.0 (compatible; TinBokerNews/1.0; +https://tinboker.com)"


def _default_parse(url: str) -> Any:
    """Download with a deadline, then parse the bytes. ``feedparser.parse(url)`` opens
    the URL with no timeout at all: one feed that stopped answering held every run
    until systemd killed it at 30 minutes, from 2026-08-15 until this was written."""
    import urllib.request

    import feedparser

    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=FEED_TIMEOUT_S) as response:  # noqa: S310 — operator-configured feeds
        return feedparser.parse(response.read())


def fetch_feeds(
    feeds: list[dict[str, Any]],
    *,
    parse: Callable[[str], Any] | None = None,
    max_per_feed: int = 50,
) -> list[FeedEntry]:
    """Parse each feed and return de-duplicated :class:`FeedEntry` records.

    A single unreachable or malformed feed is logged and skipped — the run is
    best-effort across feeds.
    """
    parse = parse or _default_parse
    entries: list[FeedEntry] = []
    seen: set[str] = set()
    for feed in feeds:
        name = str(feed.get("name") or feed.get("url") or "unknown")
        url = str(feed.get("url") or "")
        if not url:
            continue
        cutoff = _cutoff_date(feed.get("lookback_days"))
        cap = feed.get("max_episodes") or max_per_feed
        try:
            parsed = parse(url)
        except Exception as exc:  # noqa: BLE001 — one bad feed must not abort the run
            print(f"  ⚠ feed fetch failed ({name}): {exc}")
            continue
        kept = 0
        for entry in getattr(parsed, "entries", []) or []:
            if kept >= cap:
                break
            link = str(entry.get("link") or "").strip()
            if not link or link in seen:
                continue
            published = _parse_date(entry)
            # Skip entries older than the recency window; undated entries are kept.
            if cutoff and published and published < cutoff:
                continue
            seen.add(link)
            published_at = _published_timestamp(entry)
            language = feed.get("language") or {"US": "en", "TW": "zh-TW"}.get(feed.get("region"), "")
            entries.append(
                FeedEntry(
                    url=link,
                    title=str(entry.get("title") or "").strip(),
                    source=name,
                    published=published,
                    language=language,
                    published_at=published_at,
                    publication_verified=bool(published_at),
                    image_url=_entry_image(entry, link),
                    rss_summary=str(entry.get("summary") or "").strip(),
                    rss_content=_entry_content(entry),
                )
            )
            kept += 1
    return entries
