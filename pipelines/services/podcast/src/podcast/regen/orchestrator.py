"""Host-driven re-expression of the content_builder graph for agent regeneration.

The content_builder LangGraph runs ``app.invoke()`` synchronously, calling
``invoke_json`` inline at each LLM node — it cannot pause to round-trip to the MCP
client. So this module re-expresses the same DAG as an explicit sequence: the
agent (MCP client) plays the 5 LLM roles via tool calls, and this orchestrator
runs the deterministic (non-LLM) glue between submissions, then persists the
result through the pipeline's existing write paths.

Prompt rendering and output parsing reuse each node's ``build_messages`` /
``postprocess`` (the same functions the live ``invoke_json`` path uses), so the
agent path is byte-identical to a real pipeline run for the same inputs.

Per-episode progress is held in a JSON "working draft" (in-memory + on disk under
``TINBOKER_REGEN_WORK_DIR``) so the agent never has to re-pass large blobs
(sentences, events, ticker insights) across tool calls. Nothing is written to
Firestore until ``commit``.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from src.pipeline.utils import extract_tags_and_tickers

from ..content_builder.nodes import (
    extractor,
    key_insights_extractor,
    marp_writer,
    ticker_extractor,
    writer,
)
from ..content_builder.nodes.clusterer import cluster_sentences
from ..content_builder.nodes.events_markdown import build_events_markdown
from ..content_builder.nodes.key_insights_extractor import is_placeholder_summary
from ..content_builder.nodes.markdown_transform import transform_to_markdown
from ..content_builder.nodes.marp_converter import convert_marp, convert_marp_ticker
from ..content_builder.nodes.social_cards_builder import build_social_cards

# --- Step model -------------------------------------------------------------
#
# Each step maps to one LLM role the agent fills. Two steps share the
# ``marp_writer`` prompt (episode slides vs. ticker slides). Steps run in
# dependency order; ``prereq`` names the step that must be submitted first.

STEP_EXTRACTOR = "extractor"
STEP_WRITER = "writer"
STEP_KEY_INSIGHTS = "key_insights"
STEP_TICKER = "ticker_extractor"
STEP_MARP = "marp_writer"
STEP_TICKER_MARP = "ticker_marp_writer"

REQUIRED_STEPS = [STEP_EXTRACTOR, STEP_WRITER, STEP_KEY_INSIGHTS, STEP_TICKER]
OPTIONAL_STEPS = [STEP_MARP, STEP_TICKER_MARP]
ALL_STEPS = REQUIRED_STEPS + OPTIONAL_STEPS

# Forgiving aliases so the agent can say "key_insights_extractor", "slides", etc.
_STEP_ALIASES = {
    "key_insights_extractor": STEP_KEY_INSIGHTS,
    "insights": STEP_KEY_INSIGHTS,
    "ticker": STEP_TICKER,
    "tickers": STEP_TICKER,
    "ticker_insights": STEP_TICKER,
    "marp": STEP_MARP,
    "slides": STEP_MARP,
    "marp_slides": STEP_MARP,
    "ticker_marp": STEP_TICKER_MARP,
    "ticker_slides": STEP_TICKER_MARP,
}

# step -> the prompt role shown to the agent (for display only)
_STEP_ROLE = {
    STEP_EXTRACTOR: "extractor",
    STEP_WRITER: "writer",
    STEP_KEY_INSIGHTS: "key_insights_extractor",
    STEP_TICKER: "ticker_extractor",
    STEP_MARP: "marp_writer",
    STEP_TICKER_MARP: "marp_writer",
}

# step -> step that must be completed first (None = no prerequisite)
_STEP_PREREQ = {
    STEP_EXTRACTOR: None,
    STEP_WRITER: STEP_EXTRACTOR,
    STEP_KEY_INSIGHTS: STEP_WRITER,
    STEP_TICKER: STEP_EXTRACTOR,
    STEP_MARP: STEP_EXTRACTOR,
    STEP_TICKER_MARP: STEP_TICKER,
}

# One-line guidance returned with each prompt so the agent knows what to produce.
_STEP_HINT = {
    STEP_EXTRACTOR: "Segment the transcript sentences into topics. Return {\"events\": [{section_topic, start_index, end_index}, ...]} covering every sentence index.",
    STEP_WRITER: "Write the zh-TW summary article. Return the structured JSON {title, executive_summary, sections, conclusion, stock_tickers, tags} — embed [label](#ticker:SYMBOL)/[label](#tag:TAG) links inline in the section prose.",
    STEP_KEY_INSIGHTS: "Extract 3-8 plain-text zh-TW key insights from the summary. Return {\"key_insights\": [...]} (most important first, no markdown/links).",
    STEP_TICKER: "Extract ticker sentiment. Return {\"ticker_recommendations\": [{ticker, sentiment, sentiment_score, time_horizon, bluf_thesis, reasons, risks}, ...]} (keep the legacy key name).",
    STEP_MARP: "Generate episode slide data. Return {title, slides:[{heading, bullet_points, start_time, slide_notes}, ...]}.",
    STEP_TICKER_MARP: "Generate ticker-insight slide data. Return {title, slides:[...]} as for marp_writer.",
}


class RegenError(Exception):
    """A user-actionable orchestration error (surfaced as an MCP error dict)."""


def _normalize_step(step: str) -> str:
    s = (step or "").strip().lower()
    s = _STEP_ALIASES.get(s, s)
    if s not in ALL_STEPS:
        raise RegenError(
            f"Unknown step '{step}'. Valid steps: {', '.join(ALL_STEPS)}"
        )
    return s


# --- Working-draft storage --------------------------------------------------

def _work_dir() -> Path:
    d = Path(os.getenv("TINBOKER_REGEN_WORK_DIR", Path(tempfile.gettempdir()) / "tinboker_regen"))
    d.mkdir(parents=True, exist_ok=True)
    return d


_SESSIONS: dict[str, dict[str, Any]] = {}


def _safe_name(episode_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", episode_id)[:200]


def _draft_path(episode_id: str) -> Path:
    return _work_dir() / f"{_safe_name(episode_id)}.json"


def _save(draft: dict[str, Any]) -> None:
    episode_id = draft["episode_id"]
    _SESSIONS[episode_id] = draft
    try:
        _draft_path(episode_id).write_text(
            json.dumps(draft, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass  # in-memory copy is still authoritative for this process


def _load(episode_id: str) -> dict[str, Any]:
    draft = _SESSIONS.get(episode_id)
    if draft is not None:
        return draft
    path = _draft_path(episode_id)
    if path.exists():
        draft = json.loads(path.read_text(encoding="utf-8"))
        _SESSIONS[episode_id] = draft
        return draft
    raise RegenError(
        f"No active regeneration for '{episode_id}'. Call start_regen first."
    )


# --- Firestore access (lazy: importing the module bootstraps GSM secrets) ----

def _firestore():
    from src.service.firestore_service import FirestoreService

    return FirestoreService()


def _episode_sentences(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return doc.get("sentences") or doc.get("transcript_sentences") or []


def _derive_sentences_from_transcript(
    transcript: str, duration_ms: Optional[int] = None, target_chars: int = 45
) -> list[dict[str, Any]]:
    """Build a sentence array from a plain transcript when none is stored inline.

    Many already-published episodes keep only the flat ``transcript`` text (no
    sentence-level array). ASR output here has no punctuation, so we group the
    whitespace-separated phrases into ~``target_chars`` chunks (readable,
    segmentable units) and — when the episode duration is known — spread
    proportional timestamps across it so the clusterer/events glue runs unchanged.
    The timestamps are approximate (linear in transcript position), so #time
    anchors derived from them are best-effort.
    """
    tokens = [u for u in re.split(r"\s+", (transcript or "").strip()) if u]
    chunks: list[str] = []
    buf = ""
    for tok in tokens:
        buf = f"{buf} {tok}".strip() if buf else tok
        if len(buf) >= target_chars:
            chunks.append(buf)
            buf = ""
    if buf:
        chunks.append(buf)

    n = len(chunks)
    # Always assign monotonic timestamps: the clusterer drops events without a
    # start/end, so derived sentences need *some* timing. Proportional to the real
    # duration when known, else a synthetic per-chunk interval (value is arbitrary
    # but ordered — callers should not surface #time anchors from synthetic times).
    span = float(duration_ms) if duration_ms else n * 1000.0
    out: list[dict[str, Any]] = []
    for i, content in enumerate(chunks):
        out.append({
            "index": i,
            "content": content,
            "start": int(i / n * span) if n else 0,
            "end": int((i + 1) / n * span) if n else 0,
        })
    return out


# --- Per-step prompt building + glue ----------------------------------------

def _build_messages(step: str, state: dict[str, Any]) -> list[dict[str, str]]:
    if step == STEP_EXTRACTOR:
        return extractor.build_messages(state)
    if step == STEP_WRITER:
        return writer.build_messages(state)
    if step == STEP_KEY_INSIGHTS:
        return key_insights_extractor.build_messages(state)
    if step == STEP_TICKER:
        return ticker_extractor.build_messages(state)
    if step == STEP_MARP:
        return marp_writer.build_messages(state)
    if step == STEP_TICKER_MARP:
        return marp_writer.build_messages_from_events(
            state.get("ticker_insights", {}),
            state.get("source", "Podcast"),
            state.get("episode_title", "Episode"),
        )
    raise RegenError(f"Unknown step '{step}'")


def _apply(step: str, output: Any, state: dict[str, Any]) -> list[str]:
    """Apply the agent's output for ``step`` and run the unblocked non-LLM glue.

    Returns a list of human-readable warnings (e.g. zero financial events).
    """
    warnings: list[str] = []

    if step == STEP_EXTRACTOR:
        state.update(extractor.postprocess(output, state))
        state.update(cluster_sentences(state))
        state.update(build_events_markdown(state))
        if not state.get("clustered_events"):
            warnings.append(
                "0 financial events after clustering — the clusterer keeps only "
                "topics whose section_topic contains a finance keyword. Re-run "
                "'extractor' with finance-specific zh-TW topic labels (e.g. 台積電, "
                "AI 供應鏈) if the episode is financial."
            )
    elif step == STEP_WRITER:
        state.update(writer.postprocess(output, state))
        state.update(transform_to_markdown(state))
        tt = extract_tags_and_tickers({"summary_text": state.get("markdown_report", "")})
        state["tags"] = tt["tags"]
        state["related_tickers"] = tt["tickers"]
        if not state.get("markdown_report", "").strip():
            warnings.append("writer produced an empty summary — check the returned JSON shape.")
    elif step == STEP_KEY_INSIGHTS:
        state.update(key_insights_extractor.postprocess(output, state))
    elif step == STEP_TICKER:
        state.update(ticker_extractor.postprocess(output, state))
    elif step == STEP_MARP:
        state.update(marp_writer.postprocess(output, state))
        state.update(convert_marp(state))
    elif step == STEP_TICKER_MARP:
        state["ticker_marp_slides"] = output
        state.update(convert_marp_ticker(state))
    else:  # pragma: no cover - guarded by _normalize_step
        raise RegenError(f"Unknown step '{step}'")

    return warnings


def _ready_steps(completed: list[str]) -> list[str]:
    """Steps whose prerequisite is met and which aren't done yet."""
    done = set(completed)
    return [
        s for s in ALL_STEPS
        if s not in done and (_STEP_PREREQ[s] is None or _STEP_PREREQ[s] in done)
    ]


def _prompt_payload(step: str, state: dict[str, Any]) -> dict[str, Any]:
    messages = _build_messages(step, state)
    return {
        "step": step,
        "role": _STEP_ROLE[step],
        "instructions": _STEP_HINT[step],
        "system": messages[0]["content"],
        "user": messages[1]["content"],
        "messages": messages,
    }


# --- Final payload assembly + persistence -----------------------------------

def _assemble(draft: dict[str, Any]) -> dict[str, Any]:
    """Collect only the outputs whose producing step was completed.

    Field-level gating means committing never clobbers an episode field the agent
    didn't actually regenerate (Firestore merge leaves untouched fields alone).
    """
    completed = set(draft["completed"])
    state = draft["state"]
    payload: dict[str, Any] = {}

    if STEP_WRITER in completed:
        payload["summary_content"] = state.get("markdown_report", "")
        payload["tags"] = state.get("tags", [])
        payload["related_tickers"] = state.get("related_tickers", [])
    if STEP_KEY_INSIGHTS in completed:
        payload["key_insights"] = state.get("key_insights", [])
    if STEP_EXTRACTOR in completed:
        payload["events_markdown"] = state.get("events_markdown", "")
    if STEP_TICKER in completed:
        payload["ticker_insights"] = state.get("ticker_insights")
    if STEP_MARP in completed:
        payload["marp_markdown"] = state.get("marp_markdown", "")
        if STEP_KEY_INSIGHTS in completed:
            payload["social_cards"] = build_social_cards(state).get("social_cards", [])
    if STEP_TICKER_MARP in completed:
        payload["ticker_marp_markdown"] = state.get("ticker_marp_markdown", "")

    return payload


def _doc_update(payload: dict[str, Any]) -> dict[str, Any]:
    """The episode-doc merge update — everything except the ticker subcollection."""
    return {k: v for k, v in payload.items() if k != "ticker_insights"}


# --- Public API (the MCP tools are thin wrappers over these) ----------------

def find_candidates(
    podcast_name: Optional[str] = None,
    limit: int = 20,
    only_placeholder: bool = False,
) -> dict[str, Any]:
    """Episodes that have a transcript but missing/placeholder generated content."""
    fs = _firestore()
    if podcast_name:
        rows = fs.query_collection(
            "episodes", filters=[("podcast_name", "==", podcast_name)], limit=limit * 4
        )
    else:
        rows = fs.query_collection(
            "episodes", order_by="created_time", direction="DESCENDING", limit=limit * 4
        )

    out: list[dict[str, Any]] = []
    for d in rows:
        sentences = _episode_sentences(d)
        if not sentences:
            continue
        summary = d.get("summary_content") or ""
        placeholder = (not summary.strip()) or is_placeholder_summary(summary)
        if only_placeholder and not placeholder:
            continue
        out.append({
            "episode_id": d.get("episode_id") or d.get("id"),
            "podcast_name": d.get("podcast_name"),
            "episode_title": d.get("episode_title") or d.get("title"),
            "sentence_count": len(sentences),
            "has_summary": bool(summary.strip()),
            "is_placeholder": placeholder,
            "key_insight_count": len(d.get("key_insights") or []),
            "ticker_count": len(d.get("related_tickers") or []),
        })
        if len(out) >= limit:
            break
    return {"count": len(out), "candidates": out}


def start(podcast_name: str, episode_id: str) -> dict[str, Any]:
    """Load a transcribed episode and open a working draft; return the first prompt."""
    fs = _firestore()
    doc = fs.get_document("episodes", episode_id)
    if not doc:
        raise RegenError(f"Episode '{episode_id}' not found.")
    if doc.get("podcast_name") != podcast_name:
        raise RegenError(
            f"Episode '{episode_id}' belongs to '{doc.get('podcast_name')}', not '{podcast_name}'."
        )

    transcript = doc.get("transcript") or ""
    sentences = _episode_sentences(doc)
    derived_sentences = False
    if not sentences and transcript.strip():
        # Already-published episodes often keep only the flat transcript text.
        sentences = _derive_sentences_from_transcript(transcript, doc.get("spotify_duration_ms"))
        derived_sentences = True
    if not sentences:
        raise RegenError(
            f"Episode '{episode_id}' has no stored transcript. "
            "Transcription is out of scope — run the normal pipeline (Whisper) first."
        )

    episode_title = doc.get("episode_title") or doc.get("title") or "Episode"
    source = doc.get("podcast_name") or "Podcast"

    draft = {
        "episode_id": episode_id,
        "podcast_name": podcast_name,
        "episode_title": episode_title,
        "source": source,
        "created_time": doc.get("created_time") if isinstance(doc.get("created_time"), str) else None,
        "state": {
            "sentences": sentences,
            "source": source,
            "episode_title": episode_title,
            "transcript": transcript,
        },
        "completed": [],
        "current_content": {
            "summary_content": doc.get("summary_content") or "",
            "key_insights": doc.get("key_insights") or [],
            "related_tickers": doc.get("related_tickers") or [],
            "tags": doc.get("tags") or [],
        },
        "started_at_unix": int(time.time()),
    }
    _save(draft)

    return {
        "episode_id": episode_id,
        "podcast_name": podcast_name,
        "episode_title": episode_title,
        "source": source,
        "sentence_count": len(sentences),
        "derived_sentences": derived_sentences,
        "transcript_preview": (transcript[:600] + "…") if len(transcript) > 600 else transcript,
        "current_content": draft["current_content"],
        "step_order": {"required": REQUIRED_STEPS, "optional": OPTIONAL_STEPS},
        "next_prompt": _prompt_payload(STEP_EXTRACTOR, draft["state"]),
        "note": "Read each prompt, GENERATE the output yourself, then submit_role(...). "
                "Fetch any step's prompt with get_role_prompt."
                + (" NOTE: this episode had no sentence-level transcript, so sentences "
                   "were derived from the flat transcript with approximate timestamps — "
                   "#time anchors are best-effort." if derived_sentences else ""),
    }


def get_prompt(episode_id: str, step: str) -> dict[str, Any]:
    """Return the rendered system+user prompt for ``step`` (the agent fulfills it)."""
    step = _normalize_step(step)
    draft = _load(episode_id)
    prereq = _STEP_PREREQ[step]
    if prereq and prereq not in draft["completed"]:
        raise RegenError(
            f"Step '{step}' needs '{prereq}' first. Submit '{prereq}' before requesting this prompt."
        )
    return _prompt_payload(step, draft["state"])


def submit(episode_id: str, step: str, output_json: Any) -> dict[str, Any]:
    """Store the agent's output for ``step``, run the glue, return what's next."""
    step = _normalize_step(step)
    draft = _load(episode_id)
    prereq = _STEP_PREREQ[step]
    if prereq and prereq not in draft["completed"]:
        raise RegenError(f"Step '{step}' needs '{prereq}' first.")

    if isinstance(output_json, str):
        try:
            output_json = json.loads(output_json)
        except json.JSONDecodeError as exc:
            raise RegenError(f"output_json is not valid JSON: {exc}") from exc

    warnings = _apply(step, output_json, draft["state"])
    if step not in draft["completed"]:
        draft["completed"].append(step)
    _save(draft)

    ready = _ready_steps(draft["completed"])
    next_prompt = None
    # Suggest the next required step first, else the next ready (optional) one.
    suggest = next((s for s in REQUIRED_STEPS if s in ready), None) or (ready[0] if ready else None)
    if suggest:
        next_prompt = _prompt_payload(suggest, draft["state"])

    required_done = all(s in draft["completed"] for s in REQUIRED_STEPS)
    return {
        "stored": step,
        "completed": draft["completed"],
        "ready_steps": ready,
        "required_done": required_done,
        "warnings": warnings,
        "next_prompt": next_prompt,
        "hint": "All required steps done — call preview_regen then commit_regen."
                if required_done else "Continue with next_prompt, or fetch another ready step.",
    }


def preview(episode_id: str) -> dict[str, Any]:
    """Assemble the final payload that commit would write — without writing."""
    draft = _load(episode_id)
    payload = _assemble(draft)
    ticker_payload = payload.get("ticker_insights")
    ticker_count = 0
    if ticker_payload is not None:
        from src.podcast.exporters.ticker_insights import iter_insight_tickers

        ticker_count = len(set(iter_insight_tickers(ticker_payload)))
    return {
        "episode_id": episode_id,
        "completed": draft["completed"],
        "will_write_fields": sorted(_doc_update(payload).keys()),
        "summary_content": payload.get("summary_content", ""),
        "key_insights": payload.get("key_insights", []),
        "tags": payload.get("tags", []),
        "related_tickers": payload.get("related_tickers", []),
        "ticker_insight_count": ticker_count,
        "marp_chars": len(payload.get("marp_markdown", "")),
        "ticker_marp_chars": len(payload.get("ticker_marp_markdown", "")),
        "social_card_count": len(payload.get("social_cards", []) or []),
    }


def commit(
    episode_id: str,
    render_cards: bool = False,
    notify_platform: bool = True,
) -> dict[str, Any]:
    """Persist the regenerated content through the pipeline's existing write paths."""
    draft = _load(episode_id)
    payload = _assemble(draft)
    if not _doc_update(payload) and not payload.get("ticker_insights"):
        raise RegenError("Nothing to commit — no steps have been submitted yet.")

    report: dict[str, Any] = {"episode_id": episode_id, "warnings": []}
    fs = _firestore()

    # 1. Episode-doc merge (summary_content, key_insights, tags, related_tickers,
    #    marp/events markdown, social_cards) — same fields the debug PATCH writes.
    doc_update = _doc_update(payload)
    if doc_update:
        fs.set_document("episodes", episode_id, doc_update, merge=True)
        report["episode_fields_written"] = sorted(doc_update.keys())

    # 2. Rich ticker sentiment -> ticker_insights/{episode_id}/tickers/{ticker}.
    if payload.get("ticker_insights"):
        try:
            from src.podcast.exporters.ticker_insights import (
                build_episode_insight_docs,
                write_episode_insights,
            )

            docs = build_episode_insight_docs(
                raw_payload=payload["ticker_insights"],
                episode_id=episode_id,
                podcaster=draft["podcast_name"],
                podcast_launch_time=draft.get("created_time"),
            )
            report["ticker_insights_written"] = (
                write_episode_insights(fs.db, episode_id=episode_id, docs=docs) if docs else 0
            )
        except Exception as exc:  # noqa: BLE001 — best-effort, never abort the commit
            report["warnings"].append(f"ticker_insights export failed: {exc}")

    # 3. Bust the platform's Redis cache for the user-visible fields by replaying
    #    them through the backend's existing PATCH (the debug editor's write path).
    cached = {
        k: payload[k]
        for k in ("summary_content", "key_insights", "related_tickers", "tags")
        if k in payload
    }
    if notify_platform and cached:
        base = os.getenv("TINBOKER_PLATFORM_API_URL")
        if base:
            try:
                import httpx

                resp = httpx.patch(
                    f"{base.rstrip('/')}/api/podcast/{draft['podcast_name']}/episodes/{episode_id}",
                    json=cached,
                    timeout=20.0,
                )
                report["platform_notified"] = resp.status_code
                if resp.status_code >= 400:
                    report["warnings"].append(
                        f"platform PATCH returned {resp.status_code}: {resp.text[:200]}"
                    )
            except Exception as exc:  # noqa: BLE001
                report["warnings"].append(f"platform notify failed (cache may be stale): {exc}")
        else:
            report["warnings"].append(
                "TINBOKER_PLATFORM_API_URL not set — skipped cache invalidation "
                "(platform reads may be stale until the episode's TTL expires)."
            )

    # 4. PNG social-card rendering stays in the normal pipeline (needs marp_service
    #    + GCS). The slide *markdown* is saved above; we don't half-render here.
    if render_cards:
        report["warnings"].append(
            "render_cards is not performed by the regen MCP — slide markdown was "
            "saved (marp_markdown/social_cards), but PNG rendering + upload runs in "
            "the normal pipeline's social_cards step."
        )

    report["committed"] = True
    return report


def discard(episode_id: str) -> dict[str, Any]:
    """Drop the working draft (in-memory + on disk)."""
    had_session = _SESSIONS.pop(episode_id, None) is not None
    path = _draft_path(episode_id)
    file_existed = path.exists()
    if file_existed:
        try:
            path.unlink()
        except OSError:
            pass
    return {"episode_id": episode_id, "discarded": had_session or file_existed}
