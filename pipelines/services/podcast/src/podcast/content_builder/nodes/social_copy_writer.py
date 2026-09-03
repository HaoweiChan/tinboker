"""Social copy writer node: turns an episode's SUMMARY into human-tone Threads copy.

Produces ``social_thread = {post, comments: [{heading, text}, ...]}`` — one
grand-summary post plus one short, conversational comment per *summary section*
(the ``##`` blocks of the episode summary, which carry the real paragraph content),
not per marp card title. The downstream Threads publisher prefers this human copy
over the mechanical ``【title】 + bullets`` fallback.

Runs after ``build_social_cards`` (the cards still drive the carousel images), and
is also exposed as an optional regen step so the copy can be re-authored or
hand-edited per episode. When the summary has no sectioned structure it falls back
to the theme cards, then to ``key_insights``.
"""

from __future__ import annotations

import json
import re
from typing import Any

from shared.platform_client import social_enabled_for

from ..llm import invoke_json, load_prompt
from ..state import PipelineState
from .social_cards_builder import cards_from_marp_slides

# How many sections the writer gets to choose from, and how many comments it may keep.
#
# These used to be one number: one comment per section, up to ten. With the link comment
# on top that published eleven replies under a single post, and nobody had ever chosen
# eleven — it was the section count leaking into the output.
#
# Measured before cutting it, over 74 posts with insights (Spearman, controlling for
# post age, since newer posts happened to carry longer chains):
#
#     chain length vs views            +0.07  (p 0.52)
#     chain length vs likes            +0.18  (p 0.12)
#     chain length vs external replies +0.04  (p 0.77)
#
# At n=74 a rho of 0.23 would be needed for significance, so this rules out a large
# effect and not a small one. What it does establish is that a longer chain does not
# measurably grow the root post's reach, which is where discovery happens.
#
# The tail is NOT unread, and it would be convenient to pretend otherwise: per-reply
# insights over 30 posts put replies 6-11 at 5-7% of the root post's views each, about
# what replies 2-5 get. Cutting to four costs the median post ~180 reply-views. That is
# the deliberate trade — a little tail reach for a thread that does not read as a wall.
# references/platform.md wants "20 讚 + 4 則以上深度留言"; four clears that.
MAX_TOPICS = 10
MAX_COMMENTS = 4
SECTION_BODY_CHARS = 1200
OVERVIEW_CHARS = 1000

# Host nicknames the writer may use instead of the generic "主持人"/"他" — keyed by a
# substring match against the episode's podcast_name (state["source"]). Passed to the
# LLM as a *user*-message value (never baked into the system prompt as an example —
# see test_prompt_has_no_hardcoded_host_name) so an unlisted show never inherits a
# name that isn't its own. Extend as new shows are added.
_HOST_NICKNAMES: dict[str, tuple[str, ...]] = {
    "股癌": ("孟恭", "癌大", "股癌"),
    "游庭皓": ("皓哥",),
    "財經皓角": ("皓哥",),
}
_NO_HOST_NICKNAME = "（未提供，不要編造，一律用「主持人」或「他」）"

# A level-2 markdown heading marks a summary section. The summary appends a
# ``(#time:NNN)`` anchor to headings — strip it for a clean comment heading.
_SECTION_RE = re.compile(r"^\s{0,3}##\s+(.+?)\s*$")
_TIME_TAIL_RE = re.compile(r"\s*[（(]?\s*#?\s*time\s*[:：]\s*\d+\s*[)）]?\s*$", re.IGNORECASE)


def _cards_for_copy(state: PipelineState) -> list[dict[str, Any]]:
    """The cards to fall back on when the summary has no ``##`` structure."""
    cards = state.get("social_cards")
    if cards:
        return cards
    return cards_from_marp_slides(
        state.get("marp_slides") or {},
        state.get("key_insights") or [],
        state.get("episode_title") or "",
        show_name=(state.get("source") or state.get("podcast_name") or "").strip(),
    )


def _host_nicknames_for(source: str) -> str:
    """A comma-separated nickname list for the given podcast name, or the no-nickname marker."""
    for key, names in _HOST_NICKNAMES.items():
        if key in (source or ""):
            return "、".join(names)
    return _NO_HOST_NICKNAME


def _clean_heading(heading: str) -> str:
    return _TIME_TAIL_RE.sub("", heading or "").strip()


def _summary_sections(summary: str) -> list[dict[str, str]]:
    """Split a markdown summary into its ``##`` sections → ``[{heading, body}, ...]``."""
    sections: list[dict[str, Any]] = []
    cur: dict[str, Any] | None = None
    for line in (summary or "").splitlines():
        m = _SECTION_RE.match(line)
        if m:
            if cur is not None:
                sections.append(cur)
            cur = {"heading": _clean_heading(m.group(1)), "body": []}
        elif cur is not None:
            cur["body"].append(line)
    if cur is not None:
        sections.append(cur)

    out: list[dict[str, str]] = []
    for s in sections:
        body = "\n".join(s["body"]).strip()
        if s["heading"] or body:
            out.append({"heading": s["heading"], "body": body})
    return out


def _summary_overview(summary: str) -> str:
    """The intro text before the first ``##`` section (drops the leading ``#`` title)."""
    lines: list[str] = []
    for line in (summary or "").splitlines():
        if _SECTION_RE.match(line):
            break
        lines.append(line)
    text = "\n".join(lines).strip()
    return re.sub(r"^#+\s+", "", text).strip()


def _topics_for_copy(state: PipelineState) -> list[dict[str, str]]:
    """The per-comment topics, best source first: the summary's ``##`` sections →
    theme cards → key_insights. Each topic is ``{heading, body}``."""
    sections = _summary_sections(state.get("markdown_report") or "")
    if sections:
        return sections

    themes = [
        c for c in _cards_for_copy(state)
        if isinstance(c, dict) and c.get("kind") == "theme"
    ]
    if themes:
        return [
            {
                "heading": (c.get("title") or "").strip(),
                "body": "\n".join(f"- {b}" for b in (c.get("bullets") or []) if b),
            }
            for c in themes
        ]

    return [
        {"heading": str(k).strip(), "body": str(k).strip()}
        for k in (state.get("key_insights") or [])
        if k and str(k).strip()
    ]


def build_messages(state: PipelineState) -> list[dict[str, str]]:
    """Render the social_copy_writer chat messages from the episode's SUMMARY.

    Comments are written one-per-summary-section (each section's real paragraph),
    not from the short marp card titles — so the copy reflects the actual episode
    content. Falls back to theme cards / key_insights when the summary has no
    sectioned structure.
    """
    prompts = load_prompt("social_copy_writer")
    summary = (state.get("markdown_report") or "").strip()

    topics = _topics_for_copy(state)[:MAX_TOPICS]
    slim = [
        {"heading": t["heading"], "body": (t.get("body") or "")[:SECTION_BODY_CHARS]}
        for t in topics
    ]

    overview = _summary_overview(summary) or summary
    overview = overview[:OVERVIEW_CHARS] if overview else "（無摘要，請從下方各段重點抓主軸）"

    source = state.get("source") or "Podcast"
    user_msg = prompts["user"].format(
        source=source,
        episode_title=state.get("episode_title") or "Episode",
        host_nicknames=_host_nicknames_for(source),
        overview=overview,
        sections=json.dumps(slim, ensure_ascii=False, indent=2),
    )
    return [
        {"role": "system", "content": prompts["system"]},
        {"role": "user", "content": user_msg},
    ]


# The account is openly automated, so it does not get a first person: "我聽完覺得" from a
# thing that never listened is the one claim in a post that is definitely false. The
# prompt forbids it; this only reports slips, because the mechanical fix ("我覺得X" → "X")
# breaks grammar often enough that a wrong edit would be worse than a visible warning.
_FIRST_PERSON = re.compile(r"我")


def _report_first_person(post: str, comments: list[dict[str, str]]) -> None:
    hits = []
    if _FIRST_PERSON.search(post or ""):
        hits.append("post")
    hits += [f"comment {i}" for i, c in enumerate(comments, 1)
             if _FIRST_PERSON.search(c.get("text") or "")]
    if hits:
        print(f"  ⚠ first person slipped into {', '.join(hits)} — the prompt forbids 我")


def postprocess(result: Any, state: PipelineState) -> dict[str, Any]:
    """Normalise the LLM/agent output into a clean ``social_thread`` dict."""
    post = ""
    comments: list[dict[str, str]] = []
    if isinstance(result, dict):
        post = (result.get("post") or "").strip()
        for item in result.get("comments") or []:
            if isinstance(item, dict):
                text = (item.get("text") or "").strip()
                heading = (item.get("heading") or "").strip()
            else:
                text, heading = str(item).strip(), ""
            if text:
                comments.append({"heading": heading, "text": text})
    comments = comments[:MAX_COMMENTS]
    _report_first_person(post, comments)
    return {"social_thread": {"post": post, "comments": comments}}


def write_social_copy(state: PipelineState) -> dict[str, Any]:
    """Generate the human-tone Threads post + per-section comments.

    Skipped entirely — no LLM call — for shows whose platform-side publishing switch is
    off, since nothing would ever post the copy.
    """
    if not social_enabled_for(state.get("source")):
        print(f"  ⏸ Social copy skipped: publishing is off for {state.get('source')}")
        return {"social_thread": {"post": "", "comments": []}}
    result = invoke_json("social_copy_writer", build_messages(state))
    return postprocess(result, state)
