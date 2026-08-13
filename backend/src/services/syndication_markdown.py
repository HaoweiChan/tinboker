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

from src.services.markdown_blocks import (  # noqa: E402 — patterns shared with the tokenizer
    _BULLET, _EM, _HR, _LINK, _ORDERED, _STRONG,
)

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


SUMMARY_SUFFIX = "摘要"


def podcast_short_name(podcast_name: str) -> str:
    """The name readers on syndication sites actually search for.

    Feed names carry a Latin prefix the audience does not use — "Gooaye 股癌" is 股癌 to
    every reader and every vocus tag. Matching that name is what puts a post on the right
    tag page, so it is the name used in titles and tags rather than the raw feed name.

    ponytail: longest CJK run, which covers every podcast currently ingested. A feed whose
    real name is genuinely Latin falls through to the full name, which is also right. If a
    feed ever needs a hand-picked name, add a display column rather than growing this.
    """
    runs = re.findall(r"[\u4e00-\u9fff]+", podcast_name or "")
    return max(runs, key=len) if runs else (podcast_name or "").strip()


def syndication_title(podcast_name: str, episode_title: str) -> str:
    """Title for an off-site copy: the podcast name leads.

    Every 股癌 summary on vocus is titled this way ("股癌EP686 —— 學習筆記",
    "股癌 EP686 聽後心得：…") because a tag page is a wall of episode numbers otherwise —
    a bare "EP684 | 🔦" is the one entry that does not say whose episode it summarises.
    """
    short = podcast_short_name(podcast_name)
    title = (episode_title or "").strip()
    if short and not title.startswith(short):
        title = f"{short} {title}".strip()
    # Say what the post is. An episode title alone ("EP684 | 🔦") reads as a repost of the
    # episode rather than a write-up of it; the tag page is full of 筆記/心得/整理 suffixes
    # for the same reason.
    return title if title.endswith(SUMMARY_SUFFIX) else f"{title} {SUMMARY_SUFFIX}".strip()


def attribution_markdown(episode_id: str, site_url: str | None = None,
                         podcast_name: str | None = None) -> str:
    """Trailing attribution line. Full text goes to several sites, so each copy has to
    say which one is the original — vocus also accepts a real ``canonicalURL``, and the
    publisher sets both. It also names the podcast: a reader who arrives from a tag page
    should not have to infer whose episode this summarises."""
    base = (site_url or settings.site_url).rstrip("/")
    url = episode_url(episode_id, base)
    short = podcast_short_name(podcast_name or "")
    # No spaces around 《》 — CJK punctuation carries its own spacing, and the padded form
    # reads as a typo to a Chinese reader.
    subject = f"《{short}》" if short else " podcast "
    return (f"\n\n---\n\n本文是 [TinBoker]({base}) 為{subject}整理的重點摘要，"
            f"原文與可點擊的逐段時間軸在 [{url}]({url})。")


# vocus's 摘要 field caps at 150 characters; Substack's subtitle is shorter in practice.
EXCERPT_LIMIT = 150


def _plain_text(markdown_line: str) -> str:
    """Markdown inline syntax stripped down to the words, for a plain-text field."""
    out = _LINKED_TIME.sub(lambda m: m.group(1), markdown_line)
    out = _BARE_TIME.sub("", out)
    out = _LINK.sub(r"\1", out)                       # [label](url) -> label
    out = _STRONG.sub(lambda m: m.group(1) or m.group(2), out)
    out = _EM.sub(lambda m: m.group(1) or m.group(2), out)
    return " ".join(out.split())


def syndication_excerpt(content: str, limit: int = EXCERPT_LIMIT) -> str:
    """The summary's opening paragraph, as plain text, for a platform's excerpt field.

    Episodes carry no ``summary_excerpt`` — it is None on every episode checked — and the
    publishers used to fall back to the title, which spends the one field a reader skims
    on text they have already read. The summary's first paragraph is written as a lead
    and is the right thing to put there.

    Cut on a sentence boundary when one is near the limit, so the excerpt does not end
    mid-clause.
    """
    for raw in (content or "").replace("\r\n", "\n").split("\n\n"):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(">") or _HR.match(line):
            continue
        if _BULLET.match(line) or _ORDERED.match(line):
            continue
        text = _plain_text(line)
        if not text:
            continue
        if len(text) <= limit:
            return text
        window = text[:limit]
        cut = max(window.rfind("。"), window.rfind("！"), window.rfind("？"))
        if cut >= limit // 2:
            return window[: cut + 1]
        return window[: limit - 1].rstrip() + "…"
    return ""


def to_syndication_markdown(content: str, episode_id: str, site_url: str | None = None,
                            podcast_name: str | None = None) -> str:
    """Markers resolved, attribution appended. Empty in, empty out — a blank summary
    must not produce a lone attribution line with nothing above it."""
    body = rewrite_markers(content, site_url)
    if not body.strip():
        return ""
    return body.rstrip() + attribution_markdown(episode_id, site_url, podcast_name)
