"""Step 1 — fetch RSS feeds and yield candidate articles.

``feedparser`` is injectable (``parse``) so tests run fully offline.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

from ..article import FeedEntry


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


def _entry_content(entry: Any) -> str:
    """The richest article body the feed itself carries (content:encoded)."""
    content = entry.get("content")
    if content and isinstance(content, list) and content[0].get("value"):
        return str(content[0]["value"]).strip()
    return ""


def _default_parse(url: str) -> Any:
    import feedparser

    return feedparser.parse(url)


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
        try:
            parsed = parse(url)
        except Exception as exc:  # noqa: BLE001 — one bad feed must not abort the run
            print(f"  ⚠ feed fetch failed ({name}): {exc}")
            continue
        for entry in list(getattr(parsed, "entries", []) or [])[:max_per_feed]:
            link = str(entry.get("link") or "").strip()
            if not link or link in seen:
                continue
            seen.add(link)
            entries.append(
                FeedEntry(
                    url=link,
                    title=str(entry.get("title") or "").strip(),
                    source=name,
                    published=_parse_date(entry),
                    rss_summary=str(entry.get("summary") or "").strip(),
                    rss_content=_entry_content(entry),
                )
            )
    return entries
