"""Pick the 30 seconds of an episode worth clipping, and write the post that frames it.

The account posted one hand-picked 股癌 excerpt in Sep 2026 and it outperformed the
carousels, so the question became whether the pick can be automated. Two tries that do
NOT work, both measured on real episodes:

  * the timestamp the post already has (``mention_start_s`` — where a stock came up).
    On 財經一路發 9/3 that lands on the host reading a list of names: 外資買友達、兆豐金、
    國票金、華航… Correct, and nothing to listen to.
  * the chapter anchor. Chapters are 5-8 minutes and their headline content often starts
    well after the anchor.

Both fail for the same reason: neither looks at what is being SAID. So this module picks
on content, in three stages that each do what they are good at:

  1. a stance prefilter (free) — sentences where the host states something rather than
     reports it. Cuts an episode to a handful of windows.
  2. ``clip_filter`` (a decisions model) — is the question this passage answers one this
     audience actually asks? Measured over 13 real windows: 股癌's off-topic windows
     (遠距離戀愛, 東京電玩展, 交換名片) scored 0.02-0.11 against 0.73-0.89 for every
     market window. Decisive, and well under a cent an episode.
  3. the copy writer — reads the finalists, PICKS one, and writes the post. It is the
     only stage that can judge "is there a line here worth quoting", because that
     judgment IS producing the sentence, and a decisions model never generates text
     (measured: asked to score "quotable", it put every window in 0.79-0.90 and gave a
     hotel-booking story the highest score in the set). It picks rather than takes the
     top-ranked window because stance density ranks the CHATTIEST passage first: on
     兆華 EP1189 that put generic "be patient" advice above the host saying he hoped
     TSMC would not rise so the ADR premium would widen.

Stage 2 fails CLOSED: no ``CLIP_FILTER_MODEL``, or a dead endpoint, means no clip. A clip
is an optional format and posting an off-topic one is worse than posting none.

Rendering the video and publishing it are not here. This returns where the clip is and
what to say about it.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from .content_builder.llm import decide, invoke_json, is_decisions_model, load_prompt
from .content_builder.nodes.social_copy_writer import _HOST_NICKNAMES, _report_first_person

logger = logging.getLogger(__name__)

ROLE = "clip_filter"

# Willy's cap: a clip may not run past 30 seconds. It binds, so a window ends on the last
# sentence boundary that still FITS rather than the first one past some minimum —
# overrunning to finish a sentence is the thing the cap exists to prevent.
MAX_CLIP_S = 30
MIN_CLIP_S = 12
# Start a few seconds before the marker sentence so the clip does not open mid-thought.
LEAD_MS = 5000
MAX_CANDIDATES = 4
# Off-topic windows measured at <=0.11 and market windows at >=0.73, so anything in
# between is a genuinely unsure case and we would rather skip it.
RELEVANT_FLOOR = 0.70

# Where a host STATES something rather than reports it. Deliberately dumb and free: it
# only has to cut a 40-minute episode down to a few windows for the stages that cost
# money. It over-selects — every one of 股癌's travel anecdotes matches — which is fine,
# because being wrong here is cheap and being wrong later is not.
STANCE_MARKERS = (
    "我覺得", "我認為", "我會", "我建議", "我一直", "我的看法", "其實我",
    "說實話", "老實說", "講白", "坦白說", "說穿了", "本質上",
    "千萬", "不要", "別再", "最重要", "關鍵是", "重點是", "問題是",
    "你如果", "如果你", "很多人", "大部分的人", "錯了", "沒有用", "根本",
)

_SENTENCE_RE = re.compile(r"^(?P<text>.*?)\s*\(#time:(?P<ms>\d+)\)\s*$")


def parse_sentences(markdown: str) -> list[tuple[int, str]]:
    """``sentences_markdown_content`` → ``[(start_ms, text), ...]`` in episode order."""
    out: list[tuple[int, str]] = []
    for line in (markdown or "").split("\n"):
        m = _SENTENCE_RE.match(line.strip())
        if m and m.group("text").strip():
            out.append((int(m.group("ms")), m.group("text").strip()))
    return out


def _has_stance(text: str) -> bool:
    return any(k in text for k in STANCE_MARKERS)


def window_at(rows: list[tuple[int, str]], marker_ms: int) -> Optional[dict[str, Any]]:
    """The sentence-aligned window around ``marker_ms``, never longer than the cap."""
    starts = [t for t, _ in rows]
    if not starts:
        return None
    begin = max([t for t in starts if t <= marker_ms - LEAD_MS] or [starts[0]])
    fits = [t for t in starts if begin < t <= begin + MAX_CLIP_S * 1000]
    end = fits[-1] if fits else begin + MAX_CLIP_S * 1000
    if end - begin < MIN_CLIP_S * 1000:
        # One very long sentence, or the episode ends here: take the cap and let the
        # renderer cut mid-sentence rather than publish four seconds of audio.
        end = begin + MAX_CLIP_S * 1000
    text = " ".join(t for ts, t in rows if begin <= ts < end)
    return {"start_ms": begin, "end_ms": end, "text": text}


def stance_windows(rows: list[tuple[int, str]], limit: int = MAX_CANDIDATES) -> list[dict[str, Any]]:
    """Candidate windows, densest in stance markers first, never overlapping."""
    scored = []
    for t0, text in rows:
        if not _has_stance(text):
            continue
        w = window_at(rows, t0 + LEAD_MS)       # t0 itself opens the window
        if not w:
            continue
        hits = sum(1 for ts, s in rows if w["start_ms"] <= ts < w["end_ms"] and _has_stance(s))
        scored.append({**w, "stance_hits": hits})
    scored.sort(key=lambda w: (-w["stance_hits"], w["start_ms"]))

    kept: list[dict[str, Any]] = []
    for w in scored:
        if any(abs(w["start_ms"] - k["start_ms"]) < MAX_CLIP_S * 1000 for k in kept):
            continue
        kept.append(w)
        if len(kept) >= limit:
            break
    return kept


def relevant_score(text: str) -> Optional[float]:
    """How likely this passage answers a question the audience actually asks.

    None when the filter is not configured or the call failed — the caller treats that as
    "no clip", never as "post it anyway"."""
    if not is_decisions_model(ROLE):
        logger.info("clip filter not configured (%s) — no clip", ROLE)
        return None
    try:
        answers = decide(ROLE, text, {"relevant": {
            "type": "noul", "instructions": load_prompt("clip_copy_writer")["noul_instructions"]}})
        return float(answers["relevant"]["noul"])
    except Exception as e:  # noqa: BLE001 — a dead filter skips the clip, nothing more
        logger.warning("clip filter failed: %r", e)
        return None


def on_topic_windows(sentences_markdown: str) -> list[dict[str, Any]]:
    """Every candidate window that clears the relevance floor, in candidate order.

    Empty when the filter is down — fail closed, never "post it unfiltered"."""
    out = []
    for w in stance_windows(parse_sentences(sentences_markdown)):
        score = relevant_score(w["text"])
        if score is None:
            return []
        if score >= RELEVANT_FLOOR:
            out.append({**w, "relevant": score})
    return out


# ── the post ────────────────────────────────────────────────────────────────

def speaker_for(source: str) -> str:
    """Fallback only — the backend owns the speaker table and passes ``speaker``."""
    for key, names in _HOST_NICKNAMES.items():
        if key in (source or ""):
            return names[0]
    runs = re.findall(r"[一-鿿]+", source or "")
    return max(runs, key=len) if runs else ((source or "").strip() or "他")


def build_messages(material: dict) -> list[dict[str, str]]:
    prompts = load_prompt("clip_copy_writer")
    speaker = material.get("speaker") or speaker_for(material.get("source") or "")
    blocks = []
    for i, w in enumerate(material["windows"], start=1):
        blocks.append(f"[{i}] {round((w['end_ms'] - w['start_ms']) / 1000)}秒\n{w['text'].strip()}")
    user = prompts["user"].format(
        source=material.get("source") or "Podcast",
        episode_title=material.get("episode_title") or "Episode",
        air_date=material.get("air_date") or "",
        speaker=speaker,
        count=len(blocks),
        passages="\n\n".join(blocks),
    )
    return [{"role": "system", "content": prompts["system"]},
            {"role": "user", "content": user}]


def postprocess(result: Any, count: int) -> dict[str, Any]:
    """``{"choice": n|null, "post": str}`` → a 1-based index and the post, or no choice.

    Anything unparseable is "no clip": the writer declining and the writer misbehaving
    should both end with nothing posted."""
    if not isinstance(result, dict):
        return {"choice": None, "post": ""}
    post = (result.get("post") or "").strip()
    try:
        choice = int(result["choice"])
    except (KeyError, TypeError, ValueError):
        choice = 0
    if not post or not 1 <= choice <= count:
        return {"choice": None, "post": ""}
    _report_first_person(post, [])
    return {"choice": choice, "post": post}


def write_clip_copy(material: dict) -> dict[str, Any]:
    """One LLM call, on the episode writer's model role — same voice, same model."""
    return postprocess(invoke_json("social_copy_writer", build_messages(material)),
                       len(material["windows"]))


def clip_for_episode(doc: dict) -> Optional[dict[str, Any]]:
    """Pick and write in one call: ``{start_ms, end_ms, text, relevant, post}`` or None.

    None means "this episode has no clip today" — the common case by design, and the
    reason the caller must not treat it as an error."""
    windows = on_topic_windows(doc.get("sentences_markdown_content") or "")
    if not windows:
        return None
    copy = write_clip_copy({
        "windows": windows,
        "source": doc.get("podcast_name"),
        "episode_title": doc.get("episode_title") or doc.get("title"),
        "air_date": doc.get("spotify_release_date") or "",
        "speaker": doc.get("speaker"),
    })
    if not copy["choice"]:
        # None of them carried a line worth quoting; that IS the quality test.
        logger.info("clip writer picked nothing for %s — no clip", doc.get("id"))
        return None
    return {**windows[copy["choice"] - 1], "post": copy["post"]}
