"""TinBoker content-regeneration MCP server (stdio).

Lets an agent re-generate an *already-transcribed* episode's content using the
content pipeline's REAL prompts. The agent itself plays the LLM roles — replacing
the pipeline's cheap ``invoke_json`` call — and this server runs the deterministic
glue between steps and persists everything through the pipeline's existing write
paths (Firestore episode doc + ``ticker_insights`` subcollection).

Per-episode workflow:
  1. start_regen(podcast_name, episode_id)  -> the first rendered prompt (extractor)
  2. for each step: read the prompt, GENERATE the JSON yourself, submit_role(...).
     get_role_prompt re-fetches any step's prompt; submit_role returns the next one.
  3. preview_regen(episode_id)              -> review exactly what will be written
  4. commit_regen(episode_id)               -> persist to Firestore (+ platform cache bust)

Required steps:  extractor -> writer -> key_insights -> ticker_extractor
Optional steps:  marp_writer (episode slides), ticker_marp_writer (ticker slides)

Whisper/transcription is out of scope — the episode must already have a stored
transcript. Prompts are read live from the pipeline YAML files (the same files the
admin "Prompts" editor writes), so prompt edits are picked up automatically.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

# When launched as a plain script, make `from src...` resolve regardless of CWD
# (mirrors main.py — the podcast service is rooted at services/podcast).
_SVC_ROOT = Path(__file__).resolve().parents[3]  # .../services/podcast
if str(_SVC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SVC_ROOT))

from src.podcast.regen import orchestrator as _orch  # noqa: E402

mcp = FastMCP("content-regen")


def _run(fn, *args, **kwargs) -> dict[str, Any]:
    """Call an orchestrator function, converting errors into actionable dicts."""
    try:
        return fn(*args, **kwargs)
    except _orch.RegenError as exc:
        return {"error": str(exc)}
    except Exception as exc:  # noqa: BLE001 — tools must never raise to the client
        return {"error": f"unexpected error: {exc}"}


@mcp.tool()
def list_regen_candidates(
    podcast_name: Optional[str] = None,
    limit: int = 20,
    only_placeholder: bool = False,
) -> dict[str, Any]:
    """Find transcribed episodes whose generated content is missing or placeholder.

    Use this to pick episodes worth regenerating. Only episodes that already have a
    stored transcript are returned.

    Args:
        podcast_name: Optional filter to one podcast (e.g. "股癌").
        limit: Max episodes to return (default 20).
        only_placeholder: If True, return only episodes with an empty or
            placeholder summary (the ones most in need of a rewrite).

    Returns a dict with `count` and `candidates` — each candidate has
    episode_id, podcast_name, episode_title, sentence_count, has_summary,
    is_placeholder, key_insight_count, ticker_count.
    """
    return _run(_orch.find_candidates, podcast_name, limit, only_placeholder)


@mcp.tool()
def start_regen(podcast_name: str, episode_id: str) -> dict[str, Any]:
    """Open a regeneration draft for one episode and return the first prompt.

    Loads the episode's stored transcript/sentences from Firestore and returns the
    rendered `extractor` prompt as `next_prompt`. Errors if the episode has no
    transcript (transcription is out of scope).

    Args:
        podcast_name: The episode's podcast (must match the stored doc).
        episode_id: The Firestore episode document id.

    Returns episode metadata, the current (old) content for reference, the
    step_order, and `next_prompt` (the extractor system+user prompt to fulfill).
    """
    return _run(_orch.start, podcast_name, episode_id)


@mcp.tool()
def get_role_prompt(episode_id: str, step: str) -> dict[str, Any]:
    """Get the rendered system+user prompt for a step (you generate the output).

    This is the core "use the pipeline's prompts" tool — it returns the exact
    prompt the pipeline would send its LLM, filled with this episode's data. You
    then produce the output yourself and submit it with submit_role.

    Args:
        episode_id: The episode being regenerated (from start_regen).
        step: One of extractor, writer, key_insights, ticker_extractor,
            marp_writer, ticker_marp_writer (aliases like "slides",
            "key_insights_extractor", "tickers" are accepted).

    Returns {step, role, instructions, output_schema, example, global_notes,
    system, user}. ``output_schema`` + ``example`` are the exact JSON shape to
    produce (no need to read pipeline source). Errors if the step's prerequisite
    hasn't been submitted yet (e.g. writer needs extractor).
    """
    return _run(_orch.get_prompt, episode_id, step)


@mcp.tool()
def submit_role(episode_id: str, step: str, output_json: dict[str, Any]) -> dict[str, Any]:
    """Submit your generated JSON for a step; runs the glue and returns what's next.

    After you read a step's prompt and generate the result, submit it here. The
    server stores it, runs the deterministic non-LLM glue it unblocks (clustering,
    markdown transform, tag/ticker extraction, marp conversion), and returns the
    next prompt to work on.

    Args:
        episode_id: The episode being regenerated.
        step: The step this output is for (same identifiers as get_role_prompt).
        output_json: Your generated JSON for that step. Follow the step's
            ``output_schema`` + ``example`` (returned by start_regen/get_role_prompt)
            for exact field names. Top-level shapes:
            - extractor:           {"events": [{section_topic, start_index, end_index}, ...]}
            - writer:              {title, executive_summary, sections, conclusion, stock_tickers, tags}
            - key_insights:        {"key_insights": ["...", ...]}
            - ticker_extractor:    {"ticker_recommendations": [{ticker, sentiment, sentiment_score, time_horizon, bluf_thesis, reasons, risks}, ...]}
            - marp_writer / ticker_marp_writer: {title, slides: [{heading, bullet_points, start_time, slide_notes}, ...]}
            Output is validated on submit; a shape error tells you exactly what to fix.
            Write all Chinese as literal UTF-8 — never \\uXXXX escapes.

    Returns {stored, completed, ready_steps, required_done, warnings, next}.
    ``next`` is a LIGHTWEIGHT pointer — {step, instructions, output_schema, example}
    with NO transcript body — so responses stay small. Call
    get_role_prompt(episode_id, next["step"]) to fetch that step's full prompt only
    when you're ready to fill it.
    """
    return _run(_orch.submit, episode_id, step, output_json)


@mcp.tool()
def preview_regen(episode_id: str) -> dict[str, Any]:
    """Show exactly what commit_regen would write — without writing anything.

    Args:
        episode_id: The episode being regenerated.

    Returns the assembled summary_content, key_insights, tags, related_tickers,
    the list of episode fields that will be written, and counts for the
    ticker-insight docs / social cards / slide markdown. Review this before
    committing.
    """
    return _run(_orch.preview, episode_id)


@mcp.tool()
def commit_regen(
    episode_id: str,
    render_cards: bool = False,
    notify_platform: bool = True,
) -> dict[str, Any]:
    """Persist the regenerated content to Firestore and bust the platform cache.

    Writes only the fields whose steps you actually completed (Firestore merge —
    untouched fields are left alone): the episode doc (summary_content,
    key_insights, tags, related_tickers, marp/events markdown, social_cards) and
    the rich ticker sentiment under ticker_insights/{episode_id}/tickers/{ticker}.

    Args:
        episode_id: The episode being regenerated.
        notify_platform: If True (default), replay the four user-visible fields
            through the backend's PATCH (TINBOKER_PLATFORM_API_URL). That single call
            busts the episode Redis cache, the ticker_insights:* sentiment cache (when
            related_tickers changed), AND the Cloudflare edge for the target env's API
            host — so the regen shows immediately, no manual SSH/CF steps.
        render_cards: Reserved — PNG social-card rendering stays in the normal
            pipeline; only the slide markdown is saved here.

    NOTE: writes to the SHARED production Firestore (graphfolio-db) and, by default,
    busts the production caches — run preview_regen first.

    Returns a write report: episode_fields_written, ticker_insights_written, and
    either ``cache_refreshed`` {via, surfaces} on success or ``manual_invalidation``
    (exact copy-paste commands) if the cache bust was disabled/failed.
    """
    return _run(_orch.commit, episode_id, render_cards, notify_platform)


@mcp.tool()
def discard_regen(episode_id: str) -> dict[str, Any]:
    """Drop a regeneration draft without writing (frees the working state).

    Args:
        episode_id: The episode whose draft should be discarded.
    """
    return _run(_orch.discard, episode_id)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
