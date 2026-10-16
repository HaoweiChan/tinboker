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
Postgres until ``commit``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from shared.db import libpq_url

from ..content_builder.nodes import (
    extractor,
    key_insights_extractor,
    marp_writer,
    ticker_extractor,
    writer,
)
from ..content_builder.nodes.chapter_consolidator import consolidate_chapters
from ..content_builder.nodes.clusterer import cluster_sentences
from ..content_builder.nodes.events_markdown import build_events_markdown
from ..content_builder.nodes.key_insights_extractor import is_placeholder_summary
from ..content_builder.nodes.markdown_transform import transform_to_markdown
from ..content_builder.nodes.marp_converter import convert_marp, convert_marp_ticker
from ..content_builder.nodes.sector_exposures import derive_sector_exposures
from ..content_builder.nodes.social_cards_builder import build_social_cards
from ..content_builder.nodes.tags_tickers import derive_tags_tickers
from ..content_builder.profiles import load_profile
from .schemas import GLOBAL_NOTES, STEP_OUTPUT, validate_output

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

# marp_writer is REQUIRED: a regen that rewrites the summary but skips the slides
# leaves the on-page deck describing the OLD content (EP677 incident, 2026-07-08).
# ticker_marp stays optional because the ticker deck is rebuilt deterministically
# by the ticker_extractor glue (see _apply) — no agent round-trip needed.
REQUIRED_STEPS = [STEP_EXTRACTOR, STEP_WRITER, STEP_KEY_INSIGHTS, STEP_TICKER, STEP_MARP]
OPTIONAL_STEPS = [STEP_TICKER_MARP]
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
    STEP_WRITER: "Write the zh-TW summary article. Return {title, executive_summary, sections, conclusion, stock_tickers, tags} — embed [顯示名](#ticker:SYMBOL)/[顯示名](#tag:Slug) links inline in the prose. #tag:/#ticker: slugs MUST be ASCII (Chinese goes in the display text only); write literal UTF-8, not \\u escapes.",
    STEP_KEY_INSIGHTS: "Extract 3-8 plain-text zh-TW key insights from the summary. Return {\"key_insights\": [...]} (most important first, no markdown/links).",
    STEP_TICKER: "Extract ticker sentiment. Return {\"ticker_recommendations\": [{ticker, sentiment, sentiment_score, time_horizon, bluf_thesis, reasons, risks}, ...]} (keep the legacy key name).",
    STEP_MARP: "Generate episode slide data. Return {title, slides:[{heading, bullet_points, start_time, slide_notes}, ...]}.",
    STEP_TICKER_MARP: "Re-trigger the ticker deck rebuild. The ticker_extractor step already rebuilds it automatically; submit {} only to force a refresh — any slide data is ignored.",
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


def _write_doc_update(episode_id: str, fields: dict[str, Any]) -> None:
    """Jsonb-merge ``fields`` onto ``firestore_mirror.episodes.doc``.

    The sole episode write since P4 (contract § 11.5) — ``commit`` used to write
    Firestore first and treat this as a best-effort mirror. There is no second
    store now, so every failure mode raises: a missing row, a missing
    ``EPISODE_DATABASE_URL``, or a Postgres error. Silently "committing" a regen
    that landed nowhere is the worst outcome available.
    """
    if not fields:
        return

    import psycopg

    from src.podcast.exporters import postgres_mirror

    url = os.getenv("EPISODE_DATABASE_URL")
    if not url:
        raise RegenError(
            "EPISODE_DATABASE_URL is not set — cannot commit the regen (Postgres is "
            "the only content store since P4)."
        )
    with psycopg.connect(libpq_url(url), autocommit=True) as conn, conn.cursor() as cur:
        if not postgres_mirror.merge_episode_doc(cur, episode_id, fields):
            raise RegenError(
                f"No {postgres_mirror.SCHEMA}.episodes row for episode_id={episode_id} "
                "— refusing to fabricate a partial document. Ingest the episode first."
            )


def _episode_sentences(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return doc.get("sentences") or doc.get("transcript_sentences") or []


def _sentences_from_gcs(transcript_url: Optional[str]) -> list[dict[str, Any]]:
    """Fetch the sentence array from the stored transcript JSON, or ``[]``.

    Published/consolidated episodes keep only a flat ``transcript`` field in the
    episode doc and store the real sentence-level transcript (``{index, content,
    start, end}``) as a JSON artifact at ``transcript_url``. Without this, regen is
    impossible for every already-published episode (the inline fields are empty).
    Read failures degrade to ``[]`` so callers fall back cleanly.
    """
    if not transcript_url:
        return []
    try:
        data = json.loads(_gcs_storage_service().download_text_by_gcs_url(str(transcript_url)))
        if isinstance(data, dict):
            return data.get("sentences") or data.get("transcript_sentences") or []
        if isinstance(data, list):
            return data
    except Exception:  # noqa: BLE001 — missing/unreadable/malformed → fall back
        return []
    return []


def _gcs_storage_service():
    """The pipeline's media-store service (same one ``gcs_upload`` uses). Imported
    lazily so importing this module doesn't require the storage env — tests
    monkeypatch this to avoid touching the real media root."""
    from src.secrets_bootstrap import bootstrap_regen

    # The media module calls the full podcast bootstrap at import time. Set the
    # regeneration-only secret scope first, including for direct module callers.
    bootstrap_regen()
    from src.service.gcs_storage_service import GCSStorageService

    return GCSStorageService()


_LIVE_MEDIA_ROOT = Path("/srv/tinboker-media")
_LIVE_MEDIA_PUBLIC_BASE = "https://podcast-api.tinboker.com/media"


def _require_live_media_root() -> None:
    """Refuse a DB commit unless artifacts can reach the production media URL."""
    # Keep this check free of the media-service import: that module bootstraps the
    # full podcast service (including retired Firestore secrets) as a side effect.
    live_root = _LIVE_MEDIA_ROOT.resolve()
    root = Path(os.getenv("MEDIA_STORAGE_ROOT", str(live_root))).expanduser().resolve()
    if root != live_root or not live_root.is_dir():
        raise RegenError(
            f"Regeneration commit requires the live media tree at {live_root}; "
            f"MEDIA_STORAGE_ROOT resolves to {root}. Run the MCP on the VPS with "
            "that tree mounted before writing the episode database."
        )
    if not os.access(root, os.W_OK):
        raise RegenError(f"Regeneration commit cannot write to the live media tree at {root}.")
    public_base = os.getenv("MEDIA_PUBLIC_BASE", _LIVE_MEDIA_PUBLIC_BASE).rstrip("/")
    if public_base != _LIVE_MEDIA_PUBLIC_BASE:
        raise RegenError(
            f"Regeneration commit requires MEDIA_PUBLIC_BASE={_LIVE_MEDIA_PUBLIC_BASE}; "
            f"got {public_base}. Refusing to save a non-production media URL."
        )


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


# Bands measured from the 60 most recent pipeline-written 股癌 episodes. An agent
# writing to these prompts overshoots all three — 股癌 EP127 came out at 6,593 chars /
# 40 ticker links / 24 tickers against the pipeline's 4,090 / 15 / 11 from the same
# transcript. Episodes sit next to each other on the site, so drift of that size reads
# as a different publication. Warned, not enforced: a genuinely dense episode is
# allowed to exceed them, but it should be a decision rather than an accident.
_SUMMARY_CHARS = (3400, 4900)
_TICKER_LINKS_MAX = 20
_TICKERS_MAX = 12
_TAGS_MAX = 12


def _corpus_drift_warnings(state: dict[str, Any]) -> list[str]:
    """Flag writer output that falls outside the corpus it will be published into."""
    out: list[str] = []
    report = state.get("markdown_report") or ""
    lo, hi = _SUMMARY_CHARS
    if report and not (lo <= len(report) <= hi):
        out.append(
            f"summary is {len(report):,} characters; the episodes it will sit next to run "
            f"{lo:,}-{hi:,} (median ~4,300). "
            + ("Tighten it — cut restatement and merge thin sections — and resubmit 'writer' "
               "if this was not deliberate." if len(report) > hi else
               "It may be too thin; check no substantive segment was dropped.")
        )
    links = len(re.findall(r"#ticker:", report))
    if links > _TICKER_LINKS_MAX:
        out.append(
            f"{links} inline #ticker: links; a median episode carries about 9. Link the "
            "companies the discussion is about, not every one named in passing."
        )
    tickers = state.get("related_tickers") or []
    if len(tickers) > _TICKERS_MAX:
        out.append(
            f"{len(tickers)} related_tickers; the corpus median is 7 and p90 is 11. "
            "Passing analogies and examples should not become linked tickers."
        )
    tags = state.get("tags") or []
    if len(tags) > _TAGS_MAX:
        out.append(
            f"{len(tags)} tags; the corpus median is about 8. Extra tags fragment "
            "clustering rather than improving it."
        )
    return out


def _apply(step: str, output: Any, state: dict[str, Any]) -> list[str]:
    """Apply the agent's output for ``step`` and run the unblocked non-LLM glue.

    Returns a list of human-readable warnings (e.g. zero financial events).
    """
    warnings: list[str] = []

    if step == STEP_EXTRACTOR:
        state.update(extractor.postprocess(output, state))
        state.update(cluster_sentences(state))
        state.update(consolidate_chapters(state))
        state.update(build_events_markdown(state))
        state.update(derive_sector_exposures(state))
        if not state.get("clustered_events"):
            warnings.append(
                "0 events kept after clustering — the policy router dropped every "
                "segment (e.g. all typed sponsor/intro/outro/chitchat, or every qa "
                "marked is_substantive=false). Re-run 'extractor' and type the real "
                "market-analysis segments as segment_type='analysis' (and mark any "
                "valuable listener questions is_substantive=true)."
            )
    elif step == STEP_WRITER:
        state.update(writer.postprocess(output, state))
        state.update(transform_to_markdown(state))
        state.update(derive_tags_tickers(state))
        if not state.get("markdown_report", "").strip():
            warnings.append("writer produced an empty summary — check the returned JSON shape.")
        warnings.extend(_corpus_drift_warnings(state))
    elif step == STEP_KEY_INSIGHTS:
        state.update(key_insights_extractor.postprocess(output, state))
    elif step == STEP_TICKER:
        state.update(ticker_extractor.postprocess(output, state))
        # Re-derive sector exposures now that ticker_insights exists: the live graph
        # runs derive_sector_exposures AFTER extract_tickers (commit e435237) so
        # exposures whose constituents overlap the episode's actually-mentioned
        # tickers are auto-approved instead of relying on the LLM verifier alone.
        # The extractor-step pass above ran before tickers existed (verifier-only,
        # which over-drops e.g. foundry/HBM); this refines it to match live fidelity.
        state.update(derive_sector_exposures(state))
        # The ticker deck is deterministic from ticker_insights (same as the live
        # graph's extract_tickers -> convert_marp_ticker edge) — rebuild it here so a
        # commit after this step can never carry a stale ticker deck.
        # ponytail: if ticker runs before writer, related_tickers isn't derived yet
        # and canonicalization is skipped; resubmit ticker (or ticker_marp) to refresh.
        state.update(convert_marp_ticker(state))
        if state.get("marp_slides"):
            state.update(convert_marp(state))
    elif step == STEP_MARP:
        state.update(marp_writer.postprocess(output, state))
        state.update(convert_marp(state))
    elif step == STEP_TICKER_MARP:
        # The ticker deck is now built deterministically from ticker_insights (set by
        # the ticker step) — the agent's submitted slides are ignored; this step just
        # triggers the rebuild. ponytail: kept as a step so in-flight regen states and
        # the MCP contract stay valid; could be retired from the step graph later.
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


def _output_spec(step: str) -> dict[str, Any]:
    """The compact, machine-readable shape + example the agent must produce."""
    spec = STEP_OUTPUT[step]
    return {
        "output_schema": spec["schema"],
        "example": spec["example"],
        "global_notes": GLOBAL_NOTES,
    }


def _next_pointer(step: str) -> dict[str, Any]:
    """A lightweight 'what to produce next' — the output contract WITHOUT the
    transcript-laden system/user body. Fetch the full prompt on demand with
    ``get_role_prompt`` only when you're ready to fill it (keeps responses small).
    """
    return {
        "step": step,
        "role": _STEP_ROLE[step],
        "instructions": _STEP_HINT[step],
        **_output_spec(step),
        "how_to_fetch": f"call get_role_prompt(episode_id, '{step}') for the full system+user prompt.",
    }


def _parse_publication_datetime(raw: Any) -> datetime | None:
    if raw in (None, "", 0) or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        value = float(raw)
        seconds = value / 1000 if abs(value) >= 10_000_000_000 else value
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    elif isinstance(raw, str):
        value = raw.strip()
        try:
            # Also accept numeric timestamps serialized as strings by older drafts.
            numeric = float(value)
            seconds = numeric / 1000 if abs(numeric) >= 10_000_000_000 else numeric
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            try:
                published = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
            if published.tzinfo is None:
                # PodcastEpisode.resolve_publish_ms interprets naive created_time as UTC.
                published = published.replace(tzinfo=timezone.utc)
            return published
    else:
        return None


def _publication_prompt_metadata(draft: dict[str, Any]) -> dict[str, str] | None:
    """Return the canonical local publication date, trying launch time then legacy time."""
    published = _parse_publication_datetime(draft.get("podcast_launch_time"))
    if published is None:
        published = _parse_publication_datetime(draft.get("created_time"))
    if published is None:
        return None
    local = published.astimezone(ZoneInfo("Asia/Taipei"))
    return {
        "date_iso": local.date().isoformat(),
        "display_date": local.strftime("%Y.%m.%d"),
        "published_at": local.isoformat(),
        "timezone": "Asia/Taipei",
    }


def _prompt_messages(
    step: str,
    state: dict[str, Any],
    publication_metadata: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    messages = _build_messages(step, state)
    if step in {STEP_TICKER, STEP_MARP}:
        if publication_metadata:
            date_context = (
                "\n\nAuthoritative episode publication metadata (use this; do not infer from transcript):\n"
                f"- date_iso: {publication_metadata['date_iso']}\n"
                f"- display_date: {publication_metadata['display_date']}\n"
                f"- published_at: {publication_metadata['published_at']}\n"
                f"- timezone: {publication_metadata['timezone']}\n"
                "- Use date_iso for publication_date; use display_date on the Marp cover.\n"
            )
        else:
            date_context = (
                "\n\nEpisode publication metadata is unavailable in the saved episode record. "
                "Do not guess a publication date.\n"
            )
        messages[1] = {**messages[1], "content": messages[1]["content"] + date_context}
    return messages


def _prompt_payload(
    step: str,
    state: dict[str, Any],
    publication_metadata: dict[str, str] | None = None,
) -> dict[str, Any]:
    """The full rendered prompt for ``step`` — system + user + the output contract.

    The two messages carry the (large) transcript/events payload, so this is only
    returned by ``start`` (extractor) and ``get_role_prompt`` (on demand). Note the
    redundant ``messages`` array was dropped — ``system``/``user`` are the contents.
    """
    messages = _prompt_messages(step, state, publication_metadata)
    return {
        "step": step,
        "role": _STEP_ROLE[step],
        "instructions": _STEP_HINT[step],
        **_output_spec(step),
        "system": messages[0]["content"],
        "user": messages[1]["content"],
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
    if draft.get("generation_metadata"):
        payload["generation_metadata"] = draft["generation_metadata"]

    if STEP_WRITER in completed:
        payload["social_thread"] = None
        payload["social_cards"] = []
        payload["summary_content"] = state.get("markdown_report", "")
        # Same tag↔sector dedup as run_pipeline's assembly (graph.py) — done here,
        # not in derive_tags_tickers, because sector exposures are re-derived after
        # the writer step (STEP_TICKER re-runs derive_sector_exposures).
        from ..content_builder.nodes.tags_tickers import dedup_tags_against_sectors
        payload["tags"] = dedup_tags_against_sectors(
            state.get("tags", []), state.get("sector_exposures", [])
        )
        related_tickers = state.get("related_tickers", [])
        if STEP_TICKER in completed and not related_tickers:
            from src.podcast.exporters.ticker_insights import iter_insight_tickers
            ti = state.get("ticker_insights")
            if ti:
                related_tickers = sorted(set(iter_insight_tickers(ti)))
        payload["related_tickers"] = related_tickers
    if STEP_KEY_INSIGHTS in completed:
        payload["key_insights"] = state.get("key_insights", [])
    if STEP_EXTRACTOR in completed:
        payload["macro_claims"] = []
        payload["events_markdown"] = state.get("events_markdown", "")
        for field in (
            "skipped_segments",
            "sector_exposures",
            "unresolved_market_trends",
            "sector_exposure_ids",
            "sector_ids",
            "unresolved_market_trend_ids",
        ):
            payload[field] = state.get(field, [])
    if STEP_TICKER in completed:
        payload["ticker_insights"] = state.get("ticker_insights")
    if STEP_MARP in completed:
        payload["marp_markdown"] = state.get("marp_markdown", "")
        if STEP_KEY_INSIGHTS in completed:
            payload["social_cards"] = build_social_cards(state).get("social_cards", [])
    # The ticker deck is rebuilt by the ticker step's glue (and by the explicit
    # re-trigger step), so either completion means the state's deck is fresh.
    if STEP_TICKER in completed or STEP_TICKER_MARP in completed:
        payload["ticker_marp_markdown"] = state.get("ticker_marp_markdown", "")

    return payload


def _doc_update(payload: dict[str, Any]) -> dict[str, Any]:
    """The episode-doc merge update — everything except the ticker subcollection."""
    protected = {
        "ticker_insights",
        "created_time",
        "modified_summary_url",
        "modified_summary_content",
        "modified_by",
        "modified_at",
    }
    return {k: v for k, v in payload.items() if k not in protected}


# Assembled-payload field -> the ``upload_episode_files`` kwarg that writes its
# media-store artifact. These are the artifacts the backend serves *by URL*: the episode
# transformer hydrates each ``*_content`` field from the matching ``*_url`` only when
# the inline field is empty (see ``episode_transformer._GCS_CONTENT_FIELDS``). The
# regen writes the inline doc fields (``marp_markdown``/``events_markdown``/…) but the
# page reads the stored artifact, so a doc-only commit keeps serving the OLD content —
# the artifact itself must be rewritten.
_GCS_UPLOAD_KWARGS = {
    "summary_content": "summary_content",
    "events_markdown": "events_markdown_content",
    "marp_markdown": "marp_markdown_content",
    "ticker_marp_markdown": "ticker_marp_markdown_content",
}

# ``*_url`` fields returned by ``upload_episode_files`` that we copy back onto the
# episode doc, so hydration reads the freshly-uploaded blob even when the doc's old
# URL pointed at a different bucket/path than this env's uploader produces.
_GCS_URL_FIELDS = (
    "summary_url", "summary_public_url",
    "events_markdown_url", "events_markdown_public_url",
    "marp_markdown_url", "marp_markdown_public_url",
    "ticker_marp_markdown_url", "ticker_marp_markdown_public_url",
    "ticker_insights_url", "ticker_insights_public_url",
)


def _upload_regen_content(
    episode_id: str, podcast_name: str, payload: dict[str, Any]
) -> tuple[dict[str, Any], Optional[str]]:
    """Rewrite the URL-served artifacts (marp/events/ticker_marp/summary + ticker
    insights JSON) so the backend hydrates the regenerated content, not the stale blob.

    Overwrites the existing blobs (``skip_existing=False``) and returns the
    ``{*_url: ...}`` updates to merge onto the episode doc. Returns
    ``(url_updates, error)`` — ``error`` is a human-readable string when the upload
    couldn't run (storage unavailable or the upload itself failed), so ``commit`` can
    surface it as a warning instead of silently leaving the page on the old content.
    """
    cleared_urls: dict[str, Any] = {}
    for field in _GCS_UPLOAD_KWARGS:
        if field in payload and not payload[field]:
            stem = "summary" if field == "summary_content" else field
            cleared_urls[f"{stem}_url"] = None
            cleared_urls[f"{stem}_public_url"] = None
    upload_kwargs: dict[str, Any] = {
        kwarg: payload[field]
        for field, kwarg in _GCS_UPLOAD_KWARGS.items()
        if payload.get(field)
    }
    if "ticker_insights" in payload:
        upload_kwargs["ticker_insights_data"] = payload["ticker_insights"]
    if not upload_kwargs:
        return cleared_urls, None

    try:
        svc = _gcs_storage_service()
    except Exception as exc:  # noqa: BLE001 — storage unavailable → can't refresh
        return {}, (
            f"Media write skipped — storage unavailable ({exc}); the page will keep "
            "serving the OLD marp/events content until the blob is re-uploaded."
        )
    try:
        urls = svc.upload_episode_files(
            episode_id=episode_id,
            podcast_name=podcast_name,
            skip_existing=False,  # the whole point: overwrite the prior blob
            **upload_kwargs,
        )
    except Exception as exc:  # noqa: BLE001 — never abort an otherwise-good commit
        return {}, (
            f"Media write failed ({exc}); the page will keep serving the OLD "
            "marp/events content until the blob is re-uploaded."
        )
    expected = {
        "summary_content": "summary_url",
        "events_markdown_content": "events_markdown_url",
        "marp_markdown_content": "marp_markdown_url",
        "ticker_marp_markdown_content": "ticker_marp_markdown_url",
        "ticker_insights_data": "ticker_insights_url",
    }
    missing = [field for kwarg, field in expected.items() if kwarg in upload_kwargs and not urls.get(field)]
    if missing:
        return {}, f"Media write failed — missing artifact URLs: {', '.join(missing)}"
    return {**cleared_urls, **{k: urls[k] for k in _GCS_URL_FIELDS if urls.get(k)}}, None


def _manual_cache_commands(
    base: Optional[str], podcast_name: str, episode_id: str, has_tickers: bool
) -> list[str]:
    """Exact copy-paste commands to refresh the platform caches by hand — returned by
    ``commit`` only when the automatic notify is disabled/failed, so the full cache
    surface (episode + ticker sentiment + CDN) never has to be reverse-engineered."""
    api = (base or "https://api.tinboker.com").rstrip("/")
    cmds = [
        "# 1. Replay the PATCH (busts episode Redis + ticker cache + CDN via the backend).",
        "#    The endpoint is admin-gated — pass the content-writer service token or it 403s:",
        f"curl -X PATCH '{api}/api/podcast/{podcast_name}/episodes/{episode_id}' "
        "-H \"Authorization: Bearer $TINBOKER_WRITE_TOKEN\" "
        "-H 'Content-Type: application/json' --data '{\"invalidate_caches\":true}'",
    ]
    if has_tickers:
        cmds.append(
            "# 2. If sentiment cards stay stale, clear the ticker cache on the VPS:\n"
            "ssh root@VPS \"docker exec tinboker-redis sh -c \\\"redis-cli -n 0 --scan "
            "--pattern 'ticker_insights:by_ticker:*' | xargs -r redis-cli -n 0 DEL\\\"\""
        )
    cmds.append(
        "# 3. Cloudflare host purge (confirmed-working method; token/zone from GCP Secret Manager):\n"
        "curl -X POST \"https://api.cloudflare.com/client/v4/zones/$ZONE/purge_cache\" "
        "-H \"Authorization: Bearer $TOKEN\" -H 'Content-Type: application/json' "
        "--data '{\"hosts\":[\"api.tinboker.com\"]}'"
    )
    return cmds


# --- Public API (the MCP tools are thin wrappers over these) ----------------

def find_candidates(
    podcast_name: Optional[str] = None,
    limit: int = 20,
    only_placeholder: bool = False,
) -> dict[str, Any]:
    """Episodes that have a transcript but missing/placeholder generated content."""
    from src.service import postgres_mirror_reader

    if only_placeholder:
        # The "needs content" predicate runs in SQL — see query_regen_candidates. A
        # client-side filter over a newest-first window cannot find backfilled
        # episodes, which carry their true old release date and sort to the bottom.
        rows = postgres_mirror_reader.query_regen_candidates(
            podcast_name=podcast_name, limit=limit
        )
    else:
        rows = postgres_mirror_reader.query_episodes(
            podcast_name=podcast_name, limit=limit * 4
        )

    out: list[dict[str, Any]] = []
    for d in rows:
        sentences = _episode_sentences(d)
        # A regen needs *a* transcript: inline sentences, a stored transcript JSON,
        # or at least the flat text. (We don't read the artifact here — checking the
        # URL's presence keeps the listing cheap.) ``start`` resolves the real
        # source on demand.
        has_transcript = bool(sentences) or bool(d.get("transcript_url")) or bool((d.get("transcript") or "").strip())
        if not has_transcript:
            continue
        summary = d.get("summary_content") or ""
        # ``summary_content`` is written ONLY by this regen tool. The normal pipeline
        # stores the real markdown as an artifact and keeps just ``summary_url`` on the
        # doc, so testing the inline field alone reports every normally-summarised
        # episode as an empty placeholder — which would make ``only_placeholder`` a
        # work queue of 4,000+ episodes that are already fine.
        stored_summary = bool(d.get("summary_url") or d.get("summary_public_url"))
        if summary.strip():
            placeholder = is_placeholder_summary(summary)
        else:
            placeholder = not stored_summary
        if only_placeholder and not placeholder:
            continue
        out.append({
            "episode_id": d.get("episode_id") or d.get("id"),
            "podcast_name": d.get("podcast_name"),
            "episode_title": d.get("episode_title") or d.get("title"),
            "sentence_count": len(sentences) if sentences else None,
            "transcript_source": "inline" if sentences else ("gcs" if d.get("transcript_url") else "flat_text"),
            "has_summary": bool(summary.strip()) or stored_summary,
            "is_placeholder": placeholder,
            "key_insight_count": len(d.get("key_insights") or []),
            "ticker_count": len(d.get("related_tickers") or []),
        })
        if len(out) >= limit:
            break
    return {"count": len(out), "candidates": out}


def start(podcast_name: str, episode_id: str, allowed_providers: list[str] | None = None) -> dict[str, Any]:
    """Load a transcribed episode and open a working draft; return the first prompt."""
    from src.podcast.exporters.ticker_insights import episode_publish_time
    from src.service import postgres_mirror_reader

    doc = postgres_mirror_reader.get_episode_by_id(episode_id)
    if not doc:
        raise RegenError(f"Episode '{episode_id}' not found.")
    if doc.get("podcast_name") != podcast_name:
        raise RegenError(
            f"Episode '{episode_id}' belongs to '{doc.get('podcast_name')}', not '{podcast_name}'."
        )

    transcript = doc.get("transcript") or ""
    sentences = _episode_sentences(doc)
    derived_sentences = False
    if not sentences:
        # Published episodes keep the real sentence-level transcript as an artifact, not
        # inline — pull it before falling back to deriving from flat text.
        sentences = _sentences_from_gcs(doc.get("transcript_url"))
    if not sentences and transcript.strip():
        # Last resort: only the flat transcript text is available.
        sentences = _derive_sentences_from_transcript(transcript, doc.get("spotify_duration_ms"))
        derived_sentences = True
    if not sentences:
        raise RegenError(
            f"Episode '{episode_id}' has no stored transcript. "
            "Transcription is out of scope — run the normal pipeline (Whisper) first."
        )

    episode_title = doc.get("episode_title") or doc.get("title") or "Episode"
    source = doc.get("podcast_name") or "Podcast"

    if allowed_providers is not None and (not isinstance(allowed_providers, list) or any(p not in {"local", "openrouter"} for p in allowed_providers)):
        raise RegenError("allowed_providers must contain only local or openrouter")
    draft = {
        "allowed_providers": allowed_providers,
        "generation_metadata": doc.get("generation_metadata") or {"version": 1, "roles": {}, "auxiliary_calls": []},
        "episode_id": episode_id,
        "podcast_name": podcast_name,
        "episode_title": episode_title,
        "source": source,
        "created_time": doc.get("created_time") if isinstance(doc.get("created_time"), str) else None,
        # The episode's TRUE publish time (released_at_ms → Spotify → created_time),
        # stamped onto every ticker_insight so /picks measures forward returns from the
        # real mention date, not the regen-run date. Captured at draft time from the
        # episode doc so commit() doesn't need to re-read it.
        "podcast_launch_time": episode_publish_time(doc),
        "transcript_url": doc.get("transcript_url"),
        "state": {
            "sentences": sentences,
            "source": source,
            "episode_title": episode_title,
            "transcript": transcript,
            # Same per-show prior + segment policy the live pipeline seeds, so the
            # agent regen path is byte-identical (extractor hint + clusterer routing).
            "show_profile": load_profile(source),
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
    draft = deepcopy(_load(episode_id))
    prereq = _STEP_PREREQ[step]
    if prereq and prereq not in draft["completed"]:
        raise RegenError(
            f"Step '{step}' needs '{prereq}' first. Submit '{prereq}' before requesting this prompt."
        )
    return _prompt_payload(step, draft["state"], _publication_prompt_metadata(draft))


def submit(episode_id: str, step: str, output_json: Any, generation_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Store the agent's output for ``step``, run the glue, return what's next."""
    step = _normalize_step(step)
    draft = deepcopy(_load(episode_id))
    prereq = _STEP_PREREQ[step]
    if prereq and prereq not in draft["completed"]:
        raise RegenError(f"Step '{step}' needs '{prereq}' first.")

    if isinstance(output_json, str):
        try:
            output_json = json.loads(output_json)
        except json.JSONDecodeError as exc:
            raise RegenError(f"output_json is not valid JSON: {exc}") from exc

    shape_errors = validate_output(step, output_json)
    if shape_errors:
        raise RegenError(
            f"output_json shape is invalid for step '{step}':\n- " + "\n- ".join(shape_errors)
            + f"\nSee the step's output_schema/example (get_role_prompt(episode_id, '{step}'))."
        )

    if generation_metadata is not None and not isinstance(generation_metadata, dict):
        raise RegenError("generation_metadata must be an object")
    metadata = dict(generation_metadata or {"source": "unknown"})
    if set(metadata) - {"source", "provider", "model", "generated_at"}:
        raise RegenError("generation_metadata accepts only source/provider/model/generated_at; auxiliary calls are server-recorded")
    if metadata.get("source") not in {"generated", "manual", "reused", "unknown"}:
        raise RegenError("generation_metadata source must be generated, manual, reused, or unknown")
    if metadata["source"] == "generated":
        if not all(isinstance(metadata.get(k), str) and metadata[k].strip() for k in ("provider", "model", "generated_at")):
            raise RegenError("generated metadata requires actual provider, model and generated_at")
    if metadata.get("generated_at"):
        try:
            parsed = datetime.fromisoformat(metadata["generated_at"].replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("timezone required")
        except (ValueError, TypeError) as exc:
            raise RegenError("generation_metadata generated_at must be an ISO timestamp with timezone") from exc
    metadata.update({
        "attestation": "caller" if generation_metadata else "unknown",
        "prompt_sha256": hashlib.sha256(json.dumps(
            _prompt_messages(step, draft["state"], _publication_prompt_metadata(draft)),
            ensure_ascii=False,
            sort_keys=True,
        ).encode()).hexdigest(),
        "output_sha256": hashlib.sha256(json.dumps(output_json, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
    })
    if step == STEP_TICKER_MARP:
        metadata = {"source": "deterministic"}
    from ..content_builder.llm import generation_context
    calls: list[dict[str, Any]] = []
    with generation_context(draft.get("allowed_providers"), calls):
        warnings = _apply(step, output_json, draft["state"])
    provenance = draft.setdefault("generation_metadata", {"version": 1, "roles": {}, "auxiliary_calls": []})
    # Resubmission changes downstream prompts: require their outputs again.
    invalidated = {step}
    while True:
        descendants = {s for s, parent in _STEP_PREREQ.items() if parent in invalidated}
        if descendants <= invalidated:
            break
        invalidated.update(descendants)
    invalidated.discard(step)
    stale = invalidated.intersection(draft["completed"])
    pending = set(draft.get("invalidated_steps", [])) | stale
    pending.discard(step)
    draft["invalidated_steps"] = sorted(pending)
    draft["completed"] = [s for s in draft["completed"] if s not in stale]
    for stale_step in stale:
        provenance.setdefault("roles", {}).pop(stale_step, None)
    provenance.setdefault("roles", {})[step] = metadata
    provenance.setdefault("auxiliary_calls", []).extend(calls)
    if step not in draft["completed"]:
        draft["completed"].append(step)
    stored = _load(episode_id)
    stored.update(draft)
    draft = stored
    _save(draft)

    ready = _ready_steps(draft["completed"])
    # Suggest the next required step first, else the next ready (optional) one.
    suggest = next((s for s in REQUIRED_STEPS if s in ready), None) or (ready[0] if ready else None)
    # Return only a lightweight pointer (step + output contract) — NOT the heavy
    # system/user body. The agent fetches that with get_role_prompt when ready,
    # so submit responses stay small no matter how long the transcript is.
    next_step = _next_pointer(suggest) if suggest else None

    required_done = all(s in draft["completed"] for s in REQUIRED_STEPS)
    return {
        "stored": step,
        "completed": draft["completed"],
        "ready_steps": ready,
        "required_done": required_done,
        "warnings": warnings,
        "next": next_step,
        "hint": "All required steps done — call preview_regen then commit_regen."
                if required_done else "Continue with `next` (call get_role_prompt for its full prompt), "
                "or fetch another ready step.",
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
        "sector_exposures": payload.get("sector_exposures", []),
        "unresolved_market_trends": payload.get("unresolved_market_trends", []),
        "generation_metadata": payload.get("generation_metadata"),
        "allowed_providers": draft.get("allowed_providers"),
        "ticker_insight_count": ticker_count,
        "marp_chars": len(payload.get("marp_markdown", "")),
        "ticker_marp_chars": len(payload.get("ticker_marp_markdown", "")),
        "social_card_count": len(payload.get("social_cards", []) or []),
    }


def commit(
    episode_id: str,
    render_cards: bool = False,
    notify_platform: bool = True,
    allow_missing_audio: bool = False,
) -> dict[str, Any]:
    """Persist the regenerated content through the pipeline's existing write paths."""
    draft = _load(episode_id)
    payload = _assemble(draft)
    if not draft["completed"]:
        raise RegenError("Nothing to commit — no steps have been submitted yet.")
    if draft.get("invalidated_steps"):
        raise RegenError(f"Resubmit invalidated steps before commit: {draft['invalidated_steps']}")
    # Hard slide-freshness guard: a new summary with the old deck is exactly the
    # EP677 incident. Partial regens that don't touch the writer stay allowed.
    if STEP_WRITER in draft["completed"] and STEP_MARP not in draft["completed"]:
        raise RegenError(
            "The writer step was regenerated but marp_writer was not — committing "
            "would leave the episode slides describing the OLD summary. Submit "
            "'marp_writer' first (get_role_prompt(episode_id, 'marp_writer'))."
        )
    if allow_missing_audio and render_cards:
        raise RegenError("allow_missing_audio requires render_cards=False for the explicit no-audio/no-image policy.")
    if allow_missing_audio and not set(REQUIRED_STEPS).issubset(set(draft["completed"])):
        raise RegenError("allow_missing_audio requires all five required regen roles to be complete.")
    if allow_missing_audio:
        from src.pipeline.utils import has_complete_regen_provenance

        summary = payload.get("summary_content")
        transcript_url = draft.get("transcript_url")
        if not transcript_url:
            # Legacy drafts are read-only; resolve their existing source URL without
            # mutating the approved draft file or in-memory session.
            from src.service.postgres_mirror_reader import get_episode_by_id

            source_doc = get_episode_by_id(episode_id)
            transcript_url = source_doc.get("transcript_url") if source_doc else None
        if not transcript_url:
            raise RegenError("allow_missing_audio requires an existing transcript_url.")
        if not isinstance(summary, str) or not summary.strip() or is_placeholder_summary(summary):
            raise RegenError("allow_missing_audio requires a real regenerated summary.")
        if not has_complete_regen_provenance(draft.get("generation_metadata")):
            raise RegenError("allow_missing_audio requires valid generated provenance for all five required regen roles.")

    _require_live_media_root()

    report: dict[str, Any] = {"episode_id": episode_id, "warnings": []}

    # Upload and verify every required artifact before changing episode JSON.
    gcs_url_updates, gcs_error = _upload_regen_content(
        episode_id, draft["podcast_name"], payload
    )
    if gcs_error:
        raise RegenError(gcs_error)
    doc_update = _doc_update(payload)
    doc_update.update(gcs_url_updates)
    if allow_missing_audio:
        if not gcs_url_updates.get("summary_url"):
            raise RegenError("allow_missing_audio requires the regenerated summary artifact URL.")
        doc_update["artifact_completion_policy"] = {
            "version": 1,
            "mode": "regen_without_audio_or_image",
            "required_urls": ["transcript_url", "summary_url"],
            "intentionally_omitted_urls": ["mp3_url", "summary_image_url"],
        }
    if doc_update:
        _write_doc_update(episode_id, doc_update)
        report["episode_fields_written"] = sorted(doc_update.keys())
    if gcs_url_updates:
        report["gcs_content_uploaded"] = sorted(gcs_url_updates.keys())

    # 2. Rich ticker sentiment -> firestore_mirror.ticker_insights.
    if STEP_TICKER in draft["completed"]:
        try:
            from src.podcast.exporters.ticker_insights import (
                build_episode_insight_docs,
                replace_episode_insights_postgres,
            )

            docs = build_episode_insight_docs(
                raw_payload=payload["ticker_insights"],
                episode_id=episode_id,
                podcaster=draft["podcast_name"],
                # Real publish time, captured from the episode doc at draft time.
                # `created_time` fallback covers drafts opened before this field existed.
                podcast_launch_time=draft.get("podcast_launch_time") or draft.get("created_time"),
            )
            report["ticker_insights_written"] = (
                replace_episode_insights_postgres(episode_id, docs)
            )
        except Exception as exc:
            raise RegenError(f"ticker_insights replacement failed: {exc}") from exc

    if notify_platform:
        from shared.platform_client import sync_episode_mentions

        sync_episode_mentions(episode_id)

    # 3. Refresh the platform caches by replaying the user-visible fields through the
    #    backend's PATCH (the debug-editor write path). That ONE call busts the episode
    #    Redis cache, the ticker_insights:* sentiment cache (when related_tickers
    #    changed), AND the Cloudflare edge for the target env's API host — so the regen
    #    shows immediately. The result reports what refreshed; if the call is disabled
    #    or fails, it returns the exact manual commands instead of leaving you guessing.
    cached = {
        k: payload[k]
        for k in ("summary_content", "key_insights", "related_tickers", "tags")
        if k in payload
    }
    cached["invalidate_caches"] = True
    base = os.getenv("TINBOKER_PLATFORM_API_URL")
    # The PATCH endpoint is admin-gated (``get_content_write_access``); the regen agent
    # authenticates with the ``TINBOKER_WRITE_TOKEN`` content-writer service token (the
    # same token name the backend accepts for headless content writes). Without it the
    # call 403s and the caches stay stale, so require it explicitly rather than firing
    # an anonymous request that silently fails.
    write_token = os.getenv("TINBOKER_WRITE_TOKEN")
    notified_ok = False
    if notify_platform and cached and base and not write_token:
        report["warnings"].append(
            "TINBOKER_WRITE_TOKEN not set — the platform PATCH requires content-writer "
            "auth and would return 403, leaving Redis/CDN stale until TTL. Set the "
            "service token in the MCP environment, or run the manual commands below."
        )
    elif notify_platform and cached and base:
        try:
            import httpx

            resp = httpx.patch(
                f"{base.rstrip('/')}/api/podcast/{draft['podcast_name']}/episodes/{episode_id}",
                json=cached,
                headers={"Authorization": f"Bearer {write_token}"},
                timeout=20.0,
            )
            report["platform_notified"] = resp.status_code
            notified_ok = resp.status_code < 400
            if not notified_ok:
                report["warnings"].append(f"platform PATCH returned {resp.status_code}: {resp.text[:200]}")
        except Exception as exc:  # noqa: BLE001
            report["warnings"].append(f"platform notify failed (cache may be stale): {exc}")
    elif notify_platform and cached and not base:
        report["warnings"].append("TINBOKER_PLATFORM_API_URL not set — skipped cache invalidation.")

    if cached:
        surfaces = ["episode Redis cache"]
        if cached.get("invalidate_caches") or "related_tickers" in cached:
            surfaces.append("ticker_insights caches (by ticker, by podcaster, recent, trending)")
        surfaces.append("Cloudflare edge (API host)")
        if notified_ok:
            report["cache_refreshed"] = {"via": base, "surfaces": surfaces}
        else:
            report["cache_stale_until_ttl"] = True
            report["manual_invalidation"] = _manual_cache_commands(
                base, draft["podcast_name"], episode_id, True
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
