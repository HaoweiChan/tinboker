"""Post-hoc Threads copy: the story of what one episode said about one stock.

Like ``weekly_copy`` this is deliberately NOT a LangGraph node: it runs weeks after
ingest, when the backend's rotation has picked a mention whose price has since moved.
The backend owns the numbers (baseline close, latest close, the marked chart) and
appends the 「M/D 到 M/D 漲 N%」 line itself; this writes only the story, with the
clock stopped on the day the episode aired. See the prompt header for why the model
is forbidden from writing the return or grading the call.

Input is a ``material`` dict the router assembles from the episode doc:

    source, episode_title, ticker, name, mention_date, sentiment_label,
    thesis, reasons: [str], risks: [str], summary: <markdown>

Publishing is the backend's job (``social_formats.post_hoc``). Nothing here posts.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .content_builder.llm import invoke_json, load_prompt
from .content_builder.nodes.social_copy_writer import (
    # shared with the episode writer so the three prompts cannot drift on these
    _host_nicknames_for,
    _report_first_person,
    _summary_sections,
)

MAX_SECTIONS = 3
SECTION_CHARS = 1200
STANCE_ZH = {"BULLISH": "看多", "BEARISH": "看空", "NEUTRAL": "沒有明確方向"}


def sections_about(summary: str, ticker: str, name: str) -> list[dict[str, str]]:
    """The summary's ``##`` sections that mention the stock — by the pipeline's own
    ``(#ticker:2330)`` anchor first, by name as a fallback for older summaries."""
    anchor = f"#ticker:{ticker}"
    out = []
    for s in _summary_sections(summary):
        body = s.get("body") or ""
        if anchor in body or (name and name in body) or (name and name in (s.get("heading") or "")):
            # Strip the pipeline's link anchors: the model should read prose, not markup.
            clean = re.sub(r"\[([^\]]+)\]\(#[^)]+\)", r"\1", body)
            out.append({"heading": s["heading"], "body": clean[:SECTION_CHARS]})
    return out[:MAX_SECTIONS]


def _bullets(items: Any) -> str:
    lines = []
    for x in items or []:
        if isinstance(x, dict):
            t = " ".join(str(x.get(k) or "").strip() for k in ("title", "description") if x.get(k))
        else:
            t = str(x).strip()
        if t:
            lines.append(f"- {t}")
    return "\n".join(lines) or "（無）"


def build_messages(material: dict) -> list[dict[str, str]]:
    prompts = load_prompt("post_hoc_copy_writer")
    stance = (material.get("sentiment_label") or "").upper().replace("STRONG_", "")
    sections = sections_about(material.get("summary") or "", material["ticker"], material.get("name") or "")
    user = prompts["user"].format(
        source=material.get("source") or "Podcast",
        episode_title=material.get("episode_title") or "Episode",
        mention_date=material.get("mention_date") or "",
        host_nicknames=_host_nicknames_for(material.get("source") or ""),
        name=material.get("name") or material["ticker"],
        ticker=material["ticker"],
        stance=STANCE_ZH.get(stance, "沒有明確方向"),
        thesis=(material.get("thesis") or "").strip() or "（無）",
        reasons=_bullets(material.get("reasons")),
        risks=_bullets(material.get("risks")),
        sections=json.dumps(sections, ensure_ascii=False, indent=2) if sections else "（摘要裡沒有單獨講到這檔的段落，只能靠上面的結論和理由。）",
    )
    return [{"role": "system", "content": prompts["system"]},
            {"role": "user", "content": user}]


def postprocess(result: Any) -> dict[str, str]:
    post = (result.get("post") or "").strip() if isinstance(result, dict) else ""
    _report_first_person(post, [])
    return {"post": post}


def write_post_hoc_copy(material: dict) -> dict[str, str]:
    """One LLM call. Uses the episode writer's model role — same voice, same model."""
    return postprocess(invoke_json("social_copy_writer", build_messages(material)))
