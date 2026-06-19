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

from ..llm import invoke_json, load_prompt
from ..state import PipelineState
from .social_cards_builder import cards_from_marp_slides

# Comment thread length cap, and how much real text to feed per topic / for the post.
MAX_TOPICS = 10
SECTION_BODY_CHARS = 1200
OVERVIEW_CHARS = 1000

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
    )


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

    user_msg = prompts["user"].format(
        source=state.get("source") or "Podcast",
        episode_title=state.get("episode_title") or "Episode",
        overview=overview,
        sections=json.dumps(slim, ensure_ascii=False, indent=2),
    )
    return [
        {"role": "system", "content": prompts["system"]},
        {"role": "user", "content": user_msg},
    ]


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
    return {"social_thread": {"post": post, "comments": comments}}


def write_social_copy(state: PipelineState) -> dict[str, Any]:
    """Generate the human-tone Threads post + per-section comments."""
    result = invoke_json("social_copy_writer", build_messages(state))
    return postprocess(result, state)
