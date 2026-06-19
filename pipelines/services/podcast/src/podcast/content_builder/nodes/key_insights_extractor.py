"""Key-insights extractor node.

Derives the episode's ``key_insights`` — 3–8 plain-text Traditional Chinese
takeaways — from the already-generated summary markdown (``markdown_report``).

The platform renders each string verbatim on episode cards and the detail page,
so :func:`sanitize_key_insights` strips any markdown, link/time markers, quotes,
and bullet glyphs that slip through the LLM. The two public helpers
(:func:`sanitize_key_insights`, :func:`extract_key_insights_from_markdown`) are
imported directly by the Firestore backfill script so live and backfill paths
produce identical output.
"""

from __future__ import annotations

import re
from typing import Any

from ..llm import invoke_json, load_prompt
from ..state import PipelineState

# A good item is a single self-contained takeaway (contract: ~15–40 chars). We keep
# generation lenient but drop anything longer than this hard cap — a paragraph is
# not a key insight and would blow out the card layout.
_MAX_ITEM_CHARS = 80
_MIN_ITEMS = 3
_MAX_ITEMS = 8

# [label](target) -> label  (covers [台積電](#ticker:2330), [x](#tag:y), [x](url))
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
# Inline anchor markers the summary uses, when they appear bare (not inside a link).
_INLINE_MARKER = re.compile(r"\(#(?:time|ticker|tag):[^)]*\)")
# Leading list markers: -, *, +, •, ‣, ·, or "1." / "1)" style ordinals.
_LEADING_BULLET = re.compile(r"^\s*(?:[-*+•‣·]|\d+[.)])\s+")
# Markdown emphasis / code / heading / blockquote glyphs to drop.
_EMPHASIS = re.compile(r"[`*_#>]+")
# Quotes to strip from the ends (ASCII + common CJK quotation marks).
_EDGE_QUOTES = "\"'`「」『』“”‘’《》〈〉"

# Signatures of the English placeholder summary the pipeline emits when no real
# summarizer is available (see summarize/placeholders.py). Extracting "insights"
# from one of these yields generic junk ("市場趨勢與分析"), so we treat a
# placeholder summary as having no key insights at all.
_PLACEHOLDER_MARKERS = (
    "placeholder summary",
    "placeholder content",
    "placeholder chart",
    "actual ai-generated summary",
    "actual summary will be generated",
    "real summary generation pending",
    "summary generation will be implemented",
)

_GENERIC_HEADINGS = {
    "摘要",
    "重點",
    "結論",
    "市場趨勢",
    "投資觀點",
    "風險",
    "ticker insights",
    "key insights",
    "podcast episode summary",
}


def is_placeholder_summary(markdown: str) -> bool:
    """True if ``markdown`` is the pipeline's placeholder summary, not real content."""
    if not markdown:
        return False
    low = markdown.lower()
    return any(marker in low for marker in _PLACEHOLDER_MARKERS)


def _clean_item(raw: Any) -> str:
    """Normalize one raw insight string to plain text, or '' to drop it."""
    if not isinstance(raw, str):
        return ""
    text = raw.replace("\r", " ").replace("\n", " ")
    text = _MD_LINK.sub(r"\1", text)        # unwrap markdown links to their label
    text = _INLINE_MARKER.sub("", text)     # remove any bare (#time:/#ticker:/#tag:)
    text = _LEADING_BULLET.sub("", text)    # remove a leading list marker
    text = _EMPHASIS.sub("", text)          # strip emphasis/code/heading/quote glyphs
    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip(_EDGE_QUOTES).strip()
    # A trailing bullet glyph or stray separator left after stripping.
    text = text.rstrip("•‣·-—–").strip()
    return text


def sanitize_key_insights(items: Any) -> list[str]:
    """Clean, de-duplicate, and cap a raw list of insight strings.

    Returns plain-text items only — safe for verbatim rendering. Order is
    preserved (most-important-first is the model's responsibility); duplicates
    and over-long entries are dropped, and the list is capped at 8.
    """
    if not isinstance(items, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in items:
        cleaned = _clean_item(raw)
        if not cleaned or len(cleaned) > _MAX_ITEM_CHARS:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
        if len(out) >= _MAX_ITEMS:
            break
    return out


def _fallback_candidates_from_markdown(markdown: str) -> list[str]:
    """Extract deterministic plain-text fallback candidates from summary markdown."""
    candidates: list[str] = []

    def add(raw: str) -> None:
        cleaned = _clean_item(raw)
        if not cleaned or len(cleaned) > _MAX_ITEM_CHARS:
            return
        if cleaned.lower() in _GENERIC_HEADINGS:
            return
        if cleaned not in candidates:
            candidates.append(cleaned)

    for line in markdown.splitlines():
        add(line)

    plain = _clean_item(markdown)
    for sentence in re.split(r"(?<=[。！？!?])\s+|[。！？!?]\s*", plain):
        add(sentence)
    return candidates


def ensure_key_insights(
    items: Any,
    *,
    markdown: str = "",
    source: str = "Podcast",
    episode_title: str = "Episode",
) -> list[str]:
    """Return 3–8 plain-text insights for a real processed summary.

    Empty/placeholder summaries still return ``[]`` because they are not
    considered processed content. Real summaries get deterministic fallbacks so
    episode list cards never lose their required insight bullets when the LLM
    response is sparse or malformed.
    """
    insights = sanitize_key_insights(items)
    if len(insights) >= _MIN_ITEMS:
        return insights[:_MAX_ITEMS]
    if not markdown or not markdown.strip() or is_placeholder_summary(markdown):
        return insights

    for candidate in _fallback_candidates_from_markdown(markdown):
        if candidate not in insights:
            insights.append(candidate)
        if len(insights) >= _MIN_ITEMS:
            return insights[:_MAX_ITEMS]

    fallback_items = [
        f"{episode_title}整理本集核心市場脈絡",
        f"{source}本集聚焦產業趨勢、資金動向與投資風險",
        "後續可觀察主持人提到的催化因素與不確定性",
    ]
    for candidate in sanitize_key_insights(fallback_items):
        if candidate not in insights:
            insights.append(candidate)
        if len(insights) >= _MIN_ITEMS:
            break
    return insights[:_MAX_ITEMS]


def build_messages(state: PipelineState) -> list[dict[str, str]]:
    """Render the key-insights chat messages from ``markdown_report`` (no LLM call)."""
    prompts = load_prompt("key_insights_extractor")
    user_msg = prompts["user"].format(
        markdown=state.get("markdown_report", ""),
        source=state.get("source", "Podcast"),
        episode_title=state.get("episode_title", "Episode"),
    )
    return [
        {"role": "system", "content": prompts["system"]},
        {"role": "user", "content": user_msg},
    ]


def postprocess(result: Any, state: PipelineState) -> dict[str, Any]:
    """Sanitize the model's reply into a ``{"key_insights": [...]}`` state update."""
    raw = result.get("key_insights")
    if raw is None:
        raw = result.get("insights")  # tolerate the alternate key some models emit
    return {
        "key_insights": ensure_key_insights(
            raw,
            markdown=state.get("markdown_report", ""),
            source=state.get("source", "Podcast"),
            episode_title=state.get("episode_title", "Episode"),
        )
    }


def extract_key_insights_from_markdown(
    markdown: str,
    source: str = "Podcast",
    episode_title: str = "Episode",
) -> list[str]:
    """Generate sanitized ``key_insights`` from an episode summary markdown.

    Best-effort: returns ``[]`` on empty/placeholder input. For real summaries,
    sparse or failed LLM output is completed from deterministic markdown
    fallbacks so processed episodes keep the required 3–8 item contract.
    """
    if not markdown or not markdown.strip():
        return []
    if is_placeholder_summary(markdown):
        return []

    state: PipelineState = {
        "markdown_report": markdown,
        "source": source,
        "episode_title": episode_title,
    }
    try:
        result = invoke_json("key_insights_extractor", build_messages(state))
    except Exception as exc:  # noqa: BLE001 — one optional field must not abort the run
        print(f"  ⚠ key_insights extraction failed: {exc}")
        return ensure_key_insights(
            [],
            markdown=markdown,
            source=source,
            episode_title=episode_title,
        )

    return postprocess(result, state)["key_insights"]


def extract_key_insights(state: PipelineState) -> dict[str, Any]:
    """LangGraph node: derive ``key_insights`` from ``markdown_report``."""
    insights = extract_key_insights_from_markdown(
        markdown=state.get("markdown_report", ""),
        source=state.get("source", "Podcast"),
        episode_title=state.get("episode_title", "Episode"),
    )
    return {"key_insights": insights}
