"""Make an episode summary portable off tinboker.com.

The content pipeline writes three in-house markers that only resolve on our own site
(``frontend/src/components/episode/SummaryMarkdown.tsx`` renders them):

    [label](#ticker:SYMBOL)   -> a stock page link
    [label](#tag:ID)          -> a topic page link
    (#time:MILLISECONDS)      -> a badge that seeks the audio player

Anywhere else those are literal junk, so every syndication target (方格子, Substack)
needs them resolved first. This module is that shared step; the platform-specific
rendering lives next to each publisher.

**This mirrors ``frontend/src/utils/syndicationMarkdown.ts``**, which does the same job
for the admin "複製站外版" clipboard button. Two implementations exist because one runs
in the browser and one in the publisher; ``tests/unit/test_syndication_markdown.py`` and
``frontend/scripts/validate-syndication.ts`` deliberately assert the same cases, so a
change to the marker grammar that lands in only one of them fails a check.
"""

from __future__ import annotations

import re

from src.config import settings

# Matches the on-site renderer: sub-second values are the legacy writer-LLM's ordinal
# placeholders (1, 2, 3…), not real offsets, and must not become bogus 0:00 badges.
_REAL_MARKER_MIN_MS = 1000

_LINKED_TIME = re.compile(r"\[([^\]]*)\]\(#time:(\d+)\)")
_BARE_TIME = re.compile(r"\s*\(#time:(\d+)\)")
_TICKER = re.compile(r"\]\(#ticker:([^)]+)\)")
_TAG = re.compile(r"\]\(#tag:([^)]+)\)")

# CJK spacing cleanup, ported from frontend/src/utils/summaryParser.ts. The pipeline pads
# markers with ASCII spaces, which read as odd gaps in Chinese prose. Latin labels (AI,
# HBM) keep their spaces — that CJK<->Latin gap is correct typography.
_CJK = r"一-鿿　-〿＀-￯"
_LEADING = re.compile(rf"([{_CJK}])[ \t]+(\[[{_CJK}])")
_TRAILING = re.compile(rf"([{_CJK}]\]\([^)]*\))[ \t]+([{_CJK}])")
_BETWEEN = re.compile(rf"([{_CJK}])[ \t]+(?=[{_CJK}])")


def is_real_time_marker(ms: int) -> bool:
    return ms == 0 or ms >= _REAL_MARKER_MIN_MS


def format_timestamp(ms: int) -> str:
    total = round(ms / 1000)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    mm = f"{m:02d}" if h else str(m)
    return f"{h}:{mm}:{s:02d}" if h else f"{mm}:{s:02d}"


def _normalize_cjk_spacing(text: str) -> str:
    text = _LEADING.sub(r"\1\2", text)
    text = _TRAILING.sub(r"\1\2", text)
    return _BETWEEN.sub(r"\1", text)


def rewrite_markers(content: str, site_url: str | None = None) -> str:
    """Resolve the in-house markers into plain, portable markdown.

    Ticker/tag markers become absolute URLs (which also earns the backlink); timestamps
    flatten to plain text because off-site there is no player to seek.
    """
    if not content:
        return ""
    base = (site_url or settings.site_url).rstrip("/")

    def _linked_time(m: re.Match) -> str:
        return m.group(1) if is_real_time_marker(int(m.group(2))) else ""

    def _bare_time(m: re.Match) -> str:
        ms = int(m.group(1))
        return f" ({format_timestamp(ms)})" if is_real_time_marker(ms) else ""

    out = _LINKED_TIME.sub(_linked_time, content)
    out = _BARE_TIME.sub(_bare_time, out)
    out = _TICKER.sub(lambda m: f"]({base}/stock/{m.group(1).strip().upper()})", out)
    out = _TAG.sub(lambda m: f"]({base}/topics/{m.group(1).strip()})", out)
    return _normalize_cjk_spacing(out)


def episode_url(episode_id: str, site_url: str | None = None) -> str:
    return f"{(site_url or settings.site_url).rstrip('/')}/episode/{episode_id}"


def attribution_markdown(episode_id: str, site_url: str | None = None) -> str:
    """Trailing attribution line. Full text goes to several sites, so each copy has to
    say which one is the original — vocus also accepts a real ``canonicalURL``, and the
    publisher sets both."""
    base = (site_url or settings.site_url).rstrip("/")
    url = episode_url(episode_id, base)
    return f"\n\n---\n\n本文為 [TinBoker]({base}) 的 podcast 重點整理，原文與可點擊的逐段時間軸在 [{url}]({url})。"


def to_syndication_markdown(content: str, episode_id: str, site_url: str | None = None) -> str:
    """Markers resolved, attribution appended. Empty in, empty out — a blank summary
    must not produce a lone attribution line with nothing above it."""
    body = rewrite_markers(content, site_url)
    if not body.strip():
        return ""
    return body.rstrip() + attribution_markdown(episode_id, site_url)
