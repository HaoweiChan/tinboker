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
    _HOST_NICKNAMES,
    _report_first_person,
    _summary_sections,
)

MAX_EVIDENCE_CHARS = 16000
MAX_SECTIONS = 3
SECTION_CHARS = 1200
STANCE_ZH = {"BULLISH": "看多", "BEARISH": "看空", "NEUTRAL": "沒有明確方向"}

# The last paragraph of the user message: what the post is FOR decides tense and ending.
#   post_hoc — weeks later, the backend appends the price line, so the story stops on air day.
#   today    — the episode came out today; nothing follows the story, so it ends on the
#              host's own last judgment. Same voice rules otherwise.
CLOSINGS = {
    "post_hoc": "把那天他對這檔的想法講成一個 10~16 行的故事。稱呼一律用「{speaker}」和「他」，不要出現「主持人」。"
                "時間停在播出那天，用過去式，不要寫之後的事，不要寫漲跌幅，不要評斷對錯。",
    "today": "這集是今天播出的。把他這集對這檔的想法講成一個 10~16 行的故事，用現在式：「{speaker}這集講到{name}」"
             "「他在意的是」。稱呼一律用「{speaker}」和「他」，不要出現「主持人」。不要寫漲跌幅、目標價，不要評斷對錯。"
             "最後一行停在他落在哪個判斷、或他還沒想通的地方——後面不會再接任何東西，所以不要留半句給系統補。",
}

def speaker_for(source: str) -> str:
    """Fallback only. The backend owns the speaker table
    (content_source_service.speaker_for) and passes ``material["speaker"]``; this covers
    a direct call with nothing passed — the episode writer's nickname, else the show's
    CJK name."""
    src = source or ""
    for key, names in _HOST_NICKNAMES.items():
        if key in src:
            return names[0]
    runs = re.findall(r"[\u4e00-\u9fff]+", src)   # "Gooaye 股癌" → 股癌, like podcast_short_name
    return max(runs, key=len) if runs else (src.strip() or "他")


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
            out.append({"heading": s["heading"], "body": clean})
    return out


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
    stance = (material.get("sentiment_label") or "").strip().upper().removeprefix("STRONG_")
    sections = sections_about(material.get("summary") or "", material["ticker"], material.get("name") or "")
    if material.get("mode") == "today":
        sections = [{**s, "body": s["body"][:SECTION_CHARS]} for s in sections[:MAX_SECTIONS]]
    speaker = material.get("speaker") or speaker_for(material.get("source") or "")
    name = material.get("name") or material["ticker"]
    closing = CLOSINGS.get(material.get("mode") or "post_hoc", CLOSINGS["post_hoc"]).format(speaker=speaker, name=name)
    user = prompts["user"].format(
        source=material.get("source") or "Podcast",
        episode_title=material.get("episode_title") or "Episode",
        mention_date=material.get("mention_date") or "",
        speaker=speaker,
        name=name,
        closing=closing,
        mode=material.get("mode") or "post_hoc",
        full_summary=(material.get("summary") or "") if material.get("mode") != "today" else "（今天模式不附全文）",
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
    retrospective = (material.get("mode") or "post_hoc") == "post_hoc"
    sections = sections_about(material.get("summary") or "", material["ticker"], material.get("name") or "")
    expected = {
        "BULLISH": "bullish", "STRONG_BULLISH": "bullish",
        "BEARISH": "bearish", "STRONG_BEARISH": "bearish",
    }.get((material.get("sentiment_label") or "").strip().upper())
    if retrospective and (not expected or not sections or
                          len(material.get("summary") or "") > MAX_EVIDENCE_CHARS):
        return {"post": ""}
    result = invoke_json("social_copy_writer", build_messages(material))
    if retrospective:
        if not isinstance(result, dict):
            return {"post": ""}
        quote = result.get("supporting_quote")
        if (result.get("source_stance") != expected or result.get("post_stance") != expected
                or result.get("has_conflicting_evidence") is not False
                or not isinstance(quote, str) or len(quote.strip()) < 8
                or not any(quote.strip() in section["body"] for section in sections)):
            return {"post": ""}
    return postprocess(result)
