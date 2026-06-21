"""Run ONE stored episode through the real content pipeline, offline.

Sets every per-role model env to the chosen OpenRouter model BEFORE importing the
``llm``/node modules (they read model env at import), loads the episode transcript from
Firestore, runs extract_events → cluster_sentences → consolidate_chapters → write_article
→ transform_to_markdown, and writes a metrics JSON (+ a ``.md`` with the full summary).

NOTHING is written to Firestore or GCS — this is a read-only evaluation harness.

    cd pipelines
    uv run --package tinboker-podcast python \
      ../.claude/skills/pipeline-debug/scripts/run_episode_offline.py \
      <episode_id> "<podcast_name>" <openrouter_model_id> <out.json>

Env: OPENROUTER_API_KEY, FIRESTORE_DATABASE_ID=graphfolio-db, GCP_PROJECT_ID (+ ADC).
"""
import json
import os
import re
import sys
import time
import traceback

EID, SRC, MODEL, OUT = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

# Point every role at the candidate model BEFORE importing the llm module (env is read
# at import time). The pipeline prepends no prefix itself, so pass an ``openrouter:`` id.
_full = MODEL if MODEL.startswith("openrouter:") else f"openrouter:{MODEL}"
for var in ("EXTRACTOR_MODEL", "WRITER_MODEL", "MARP_WRITER_MODEL",
            "TICKER_EXTRACTOR_MODEL", "KEY_INSIGHTS_EXTRACTOR_MODEL"):
    os.environ[var] = _full
# Keep DB overrides out of the way so the env model wins for this offline run.
os.environ.pop("PLATFORM_DATABASE_URL", None)
os.environ.pop("EPISODE_DATABASE_URL", None)

# Make `src.podcast…` importable regardless of CWD: locate the podcast service root
# (the dir containing src/podcast) from the current dir or the usual `pipelines/` CWD.
for _cand in (os.getcwd(), os.path.join(os.getcwd(), "services", "podcast")):
    if os.path.isdir(os.path.join(_cand, "src", "podcast")):
        sys.path.insert(0, _cand)
        break

from src.podcast.content_builder.nodes.chapter_consolidator import consolidate_chapters
from src.podcast.content_builder.nodes.clusterer import cluster_sentences
from src.podcast.content_builder.nodes.extractor import extract_events
from src.podcast.content_builder.nodes.markdown_transform import transform_to_markdown
from src.podcast.content_builder.nodes.writer import write_article
from src.podcast.content_builder.profiles import load_profile
from src.podcast.regen.orchestrator import (
    _derive_sentences_from_transcript,
    _episode_sentences,
    _firestore,
    _sentences_from_gcs,
)

PLACEHOLDER_MARKERS = ["摘要生成中", "內容生成中", "摘要產生中", "內容產生中", "生成失敗",
                       "summary unavailable"]
HEADING_RE = re.compile(r"^##\s+(.*?)(?:\s*\(#time:(\d+)\))?\s*$", re.M)
TICKER_RE = re.compile(r"\[[^\]]+\]\(#ticker:[^)]+\)")
TAG_RE = re.compile(r"\[[^\]]+\]\(#tag:[^)]+\)")


def _opencc_leak(md: str):
    """opencc s2t delta — NOTE: noisy (flags acceptable TW variants 台/群/才). Read the md."""
    try:
        import opencc
        t = opencc.OpenCC("s2t").convert(md)
        return sum(1 for a, b in zip(md, t) if a != b)
    except Exception:
        return -1


rec = {"model": MODEL, "episode_id": EID, "source": SRC, "error": None}
t0 = time.time()
try:
    doc = _firestore().get_document("episodes", EID)
    if not doc:
        raise RuntimeError(f"Episode '{EID}' not found.")
    rec["episode_title"] = doc.get("episode_title") or doc.get("title") or ""
    transcript = doc.get("transcript") or ""
    sents = (_episode_sentences(doc) or _sentences_from_gcs(doc.get("transcript_url"))
             or (_derive_sentences_from_transcript(transcript, doc.get("spotify_duration_ms"))
                 if transcript.strip() else []))
    rec["sentence_count"] = len(sents)
    if not sents:
        raise RuntimeError("No transcript sentences.")

    state = {"sentences": sents, "source": SRC, "episode_title": rec["episode_title"],
             "transcript": transcript, "show_profile": load_profile(SRC)}
    for fn in (extract_events, cluster_sentences, consolidate_chapters,
               write_article, transform_to_markdown):
        print(f"  {fn.__name__} ...", flush=True)
        state.update(fn(state))

    md = state.get("markdown_report", "") or ""
    wo = state.get("writer_output", {}) or {}
    rec.update(
        event_count=len(state.get("events", []) or []),
        clustered_count=len(state.get("clustered_events", []) or []),
        chapter_count=len(state.get("chapter_events", []) or []),
        writer_section_count=len(wo.get("sections", []) or []),
        executive_summary=wo.get("executive_summary", ""),
        heading_count=len(HEADING_RE.findall(md)),
        markdown_len=len(md),
        placeholder_hits=[m for m in PLACEHOLDER_MARKERS if m in md],
        ticker_links=len(TICKER_RE.findall(md)),
        tag_links=len(TAG_RE.findall(md)),
        opencc_changed_count=_opencc_leak(md),
        json_ok=True,
    )
    with open(OUT.replace(".json", ".md"), "w") as f:
        f.write(md)
except Exception as e:
    rec["json_ok"] = False
    rec["error"] = f"{type(e).__name__}: {e}"
    rec["traceback"] = traceback.format_exc()[-1500:]

rec["runtime_s"] = round(time.time() - t0, 1)
with open(OUT, "w") as f:
    json.dump(rec, f, ensure_ascii=False, indent=2)
print(f"\n=== {OUT} json_ok={rec.get('json_ok')} chapters={rec.get('chapter_count')} "
      f"sections={rec.get('writer_section_count')} tickers={rec.get('ticker_links')} "
      f"tags={rec.get('tag_links')} ===", flush=True)
