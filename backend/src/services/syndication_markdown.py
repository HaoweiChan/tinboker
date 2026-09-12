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
from datetime import date, datetime, timezone

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


# ── structured off-site copy (2026-09-13) ─────────────────────────────────────
# What goes to vocus/Substack is no longer the summary verbatim under "<show> <title> 摘要".
# Reviewed against the live salon: the episode's own title (an in-joke, an emoji) gave a
# stranger no reason to click; the summary opened with a "本文深入探討…" lead that repeats
# the article it introduces; and a backfilled 2022 episode carried a 2026 publish date with
# "目前" in the text. The copy now leads with one concrete claim, states the air date, and
# marks anything older than HISTORIC_AFTER_DAYS as a look-back.

from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")
HOOK_MAX = 36
HISTORIC_AFTER_DAYS = 30
_EP_LABEL = re.compile(r"(?i)\b(ep\s?\.?\s?\d+[a-z]?)\b|(\d{4}[./]\d{1,2}[./]\d{1,2})|(?<!\d)(\d{1,2}/\d{1,2})(?!\d)")
_GENERIC_H1_TAIL = re.compile(r"[：:].*?(全解析|全面剖析|深度解析|完整解析|解析|剖析|總覽|全攻略)\s*$")
_BOILERPLATE_LEAD = re.compile(r"^(本文|本集|本篇|這集|這一集|這期)")
_BOILERPLATE_VERB = re.compile(r"深入|剖析|探討|全面|解析|盤點|聚焦")
_H1 = re.compile(r"^#\s+.*$", re.M)


def episode_label(episode_title: str) -> str:
    """The short handle a listener uses for the episode: "EP696", "Ep170", "2026/9/11"."""
    m = _EP_LABEL.search(episode_title or "")
    if m:
        token = next(g for g in m.groups() if g)
        return re.sub(r"(?i)^ep\s?\.?\s?", "EP", token) if token.lower().startswith("ep") else token
    return (episode_title or "").strip()[:12]


def _clip_hook(text: str, limit: int = HOOK_MAX) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    window = text[:limit]
    cut = max(window.rfind(c) for c in "，、；：,;:")
    return window[:cut] if cut >= limit // 2 else window.rstrip() + "…"


def hook_from(key_insights: list[str], summary: str) -> str:
    """One concrete claim to lead the title with, or "" when the episode offers none."""
    for k in key_insights or []:
        k = (k or "").strip()
        if len(k) >= 8:
            return _clip_hook(k)
    m = _H1.search(summary or "")
    if m:
        h1 = _plain_text(m.group(0).lstrip("# ").strip())
        h1 = _GENERIC_H1_TAIL.sub("", h1).strip()
        if len(h1) >= 8:
            return _clip_hook(h1)
    return ""


def hook_title(podcast_name: str, episode_title: str, key_insights: list[str], summary: str,
               historic: bool = False) -> str:
    """"<claim>｜<show> <EP label>", falling back to the legacy "<show> <title> 摘要"."""
    hook = hook_from(key_insights, summary)
    if not hook:
        title = syndication_title(podcast_name, episode_title)
    else:
        title = f"{hook}｜{' '.join(x for x in (podcast_short_name(podcast_name), episode_label(episode_title)) if x)}"
    return f"【歷史回顧】{title}" if historic else title


def strip_boilerplate(summary: str) -> str:
    """Drop the H1 (the post has its own title) and a lead paragraph that only announces
    what the article is about to do."""
    text = (summary or "").replace("\r\n", "\n")
    text = _H1.sub("", text, count=1).lstrip("\n")
    paras = text.split("\n\n")
    for i, para in enumerate(paras):
        line = para.strip()
        if not line:
            continue
        plain = _plain_text(line)
        if _BOILERPLATE_LEAD.match(plain) and _BOILERPLATE_VERB.search(plain) and not line.startswith("#"):
            del paras[i]
        break
    return "\n\n".join(paras).strip()


def released_date(released_at_ms: int | None) -> date | None:
    if not released_at_ms:
        return None
    return datetime.fromtimestamp(released_at_ms / 1000, tz=timezone.utc).astimezone(TAIPEI).date()


def is_historic(released_at_ms: int | None, on: date | None = None) -> bool:
    """True when the episode aired more than HISTORIC_AFTER_DAYS before the copy goes out.
    Unknown air date counts as historic: it is the case that embarrassed us."""
    rel = released_date(released_at_ms)
    if rel is None:
        return True
    return ((on or date.today()) - rel).days > HISTORIC_AFTER_DAYS


def build_syndication_body(*, episode_id: str, podcast_name: str, episode_title: str, summary: str,
                           key_insights: list[str], released_at_ms: int | None,
                           ticker_lines: list[str] | None = None, spotify_url: str | None = None,
                           site_url: str | None = None, synced_on: date | None = None) -> str:
    """The off-site article body. Markers already resolved; no attribution (the publisher
    appends its own canonical line). Empty summary and no insights → ""."""
    base = (site_url or settings.site_url).rstrip("/")
    synced_on = synced_on or date.today()
    short = podcast_short_name(podcast_name)
    rel = released_date(released_at_ms)
    historic = is_historic(released_at_ms, synced_on)
    parts: list[str] = []
    head = f"原節目：{short} {(episode_title or '').strip()}".strip()
    head += f"（{rel.isoformat()} 播出）" if rel else "（播出日期不明）"
    head += f"・整理：{synced_on.isoformat()}"
    parts.append(head)
    if historic:
        when = rel.strftime("%Y 年 %-m 月") if rel else "較早"
        parts.append(f"> 本篇是 {when} 播出節目的整理。文中的「目前」「近期」「即將」都指節目當時，不是現在；"
                     f"當時提到的持股、利率與預測，不能直接當作今天的判斷。")
    insights = [k.strip() for k in (key_insights or []) if (k or "").strip()][:3]
    if insights:
        parts += ["## 30 秒讀完", "\n".join(f"- {k}" for k in insights)]
    if ticker_lines:
        parts += ["## 這集講到的股票", "\n".join(f"- {line}" for line in ticker_lines)]
    body = rewrite_markers(strip_boilerplate(summary), base).strip()
    if body:
        parts += ["## 精選段落", body]
    if not insights and not body:
        return ""
    when = f"在 {rel.isoformat()} 的節目裡" if rel else "在節目裡"
    parts += ["## 適用範圍",
              f"以上是主持人{when}講的內容整理，屬第三方公開言論，不代表 TinBoker 的看法，也不構成投資建議；"
              f"節目中提到的個人操作僅供參考。"]
    steps = []
    if spotify_url:
        steps.append(f"- 聽原話：{spotify_url}")
    steps.append(f"- 逐段時間軸，以及這集提到的每一檔股票的觀點與之後走勢：{episode_url(episode_id, base)}")
    parts += ["## 下一步", "\n".join(steps)]
    return "\n\n".join(parts)
