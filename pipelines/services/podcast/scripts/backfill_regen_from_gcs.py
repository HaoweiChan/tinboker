#!/usr/bin/env python3
"""Regenerate a published episode's summary with the segment-aware pipeline,
sourcing the sentence-level transcript from GCS ``transcript_url`` (not from an
inline Firestore field — published episodes don't have one).

Why this exists: the regen MCP path reads ``doc["transcript"]``/``["sentences"]``
inline, but every published episode keeps the transcript in GCS at
``transcript_url`` (a JSON ``{text, sentences[{index,content,start,end}], words}``)
with only the cached ``summary_content`` inline. This script bridges that gap and
runs the in-process ``run_pipeline`` (new policy-router clustering) over the real
sentence timing, so ``#time:`` chapter anchors are accurate.

Two-phase, for safety on PROD Firestore:

    # 1. dry run — fetch + generate, cache the result, print a preview. No writes.
    uv run --package tinboker-podcast python services/podcast/scripts/backfill_regen_from_gcs.py EP_ID

    # 2. commit — load the cached result, write Firestore + bust the platform cache.
    uv run --package tinboker-podcast python services/podcast/scripts/backfill_regen_from_gcs.py EP_ID --commit

Model: OPENROUTER_API_KEY is not in GSM, so the openrouter:* default can't run
here; we pin all roles to gemini-2.5-flash (GOOGLE_API_KEY is present). Production
new-episode runs use whatever the VPS pipeline_config_overrides set.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote, urlparse

# Pin LLM roles to Gemini BEFORE importing the pipeline (llm.py reads *_MODEL at
# import time). gemini-2.5-flash supports JSON mode and the GOOGLE_API_KEY path.
for _role in ("EXTRACTOR_MODEL", "WRITER_MODEL", "TICKER_EXTRACTOR_MODEL",
              "KEY_INSIGHTS_EXTRACTOR_MODEL", "MARP_WRITER_MODEL"):
    os.environ.setdefault(_role, "gemini-2.5-flash")

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVICE_ROOT))

from src.secrets_bootstrap import bootstrap  # noqa: E402

CACHE_DIR = _SERVICE_ROOT / ".regen_cache"


def _parse_gs(url: str) -> tuple[str, str]:
    p = urlparse(url)
    return p.netloc, p.path.lstrip("/")


def _load_sentences_from_gcs(transcript_url: str) -> tuple[list, str]:
    from google.cloud import storage

    bucket, blob = _parse_gs(transcript_url)
    raw = storage.Client(project=os.environ["GCP_PROJECT_ID"]).bucket(bucket).blob(blob).download_as_text()
    data = json.loads(raw)
    return data.get("sentences") or [], data.get("text", "")


def _chapters(md: str) -> list[tuple[str, str]]:
    return re.findall(r"^##\s+(.*?)\s*\(#time:(\d+)\)", md, re.M)


def generate(episode_id: str) -> dict:
    from src.service.firestore_service import FirestoreService

    fs = FirestoreService()
    doc = fs.get_document("episodes", episode_id)
    if not doc:
        sys.exit(f"episode '{episode_id}' not found")
    transcript_url = doc.get("transcript_url")
    if not transcript_url:
        sys.exit(f"episode '{episode_id}' has no transcript_url")

    sentences, text = _load_sentences_from_gcs(transcript_url)
    if not sentences:
        sys.exit("transcript JSON has no 'sentences' array")
    source = doc.get("podcast_name") or "Podcast"
    title = doc.get("episode_title") or doc.get("title") or "Episode"
    print(f"loaded {len(sentences)} sentences from {transcript_url}")

    # Drop the VPS-only Postgres URL so llm._load_db_overrides() short-circuits
    # instead of hanging on an unreachable host.
    os.environ.pop("EPISODE_DATABASE_URL", None)
    os.environ.pop("PLATFORM_DATABASE_URL", None)

    from src.podcast.content_builder import run_pipeline
    from src.podcast.exporters.ticker_insights import episode_publish_time

    result = run_pipeline(transcript=text, sentences=sentences, source=source, episode_title=title)
    out = {
        "episode_id": episode_id,
        "podcast_name": source,
        "episode_title": title,
        "summary_content": result.get("markdown_report", ""),
        "key_insights": result.get("key_insights", []),
        "tags": result.get("tags", []),
        "related_tickers": result.get("related_tickers", []),
        "ticker_insights": result.get("ticker_insights"),
        "created_time": doc.get("created_time") if isinstance(doc.get("created_time"), str) else None,
        # The episode's TRUE publish time — stamp insights from the real mention date,
        # not this backfill run's date (the bug that collapsed back-catalogues on /picks).
        "podcast_launch_time": episode_publish_time(doc),
    }
    CACHE_DIR.mkdir(exist_ok=True)
    (CACHE_DIR / f"{episode_id}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def preview(out: dict) -> None:
    from src.podcast.exporters.ticker_insights import iter_insight_tickers

    print("\n=== SUMMARY (first 900 chars) ===")
    print(out["summary_content"][:900])
    print("\n=== CHAPTERS (#time anchors) ===")
    for title, ms in _chapters(out["summary_content"]):
        s = int(ms) // 1000
        print(f"  {s // 60:02d}:{s % 60:02d}  {title}")
    print("\n=== key_insights ===")
    for k in out["key_insights"]:
        print("  -", k)
    print("\n=== related_tickers ===", out["related_tickers"])
    ti = out.get("ticker_insights")
    print("=== ticker_insight tickers ===", sorted(set(iter_insight_tickers(ti))) if ti else [])


def commit(episode_id: str, with_tickers: bool = False) -> None:
    path = CACHE_DIR / f"{episode_id}.json"
    if not path.exists():
        sys.exit(f"no cached result for {episode_id}; run the dry phase first")
    out = json.loads(path.read_text(encoding="utf-8"))

    from src.service.firestore_service import FirestoreService

    fs = FirestoreService()
    # The summary/insights/tags are the clean structural win. related_tickers +
    # ticker_insights are gated: the LLM over-resolves private companies/categories
    # to fake symbols (SPCE≠SpaceX, ANTHR/OPENAI, "被動元件"), so don't write them
    # unless explicitly asked — better to leave the existing tickers than add junk.
    doc_update = {k: out[k] for k in ("summary_content", "key_insights", "tags")}
    if with_tickers:
        # The cached related_tickers predate the symbol-validation filter, so clean
        # them here too (ticker_insights is filtered by the exporter below).
        from shared.tickers import valid_tickers

        doc_update["related_tickers"] = valid_tickers(out.get("related_tickers") or [])
    fs.set_document("episodes", episode_id, doc_update, merge=True)
    print(f"episode doc merged: {sorted(doc_update)}"
          + (f" | related_tickers={doc_update['related_tickers']}" if with_tickers else ""))

    written = 0
    ti = out.get("ticker_insights")
    if with_tickers and ti:
        from src.podcast.exporters.ticker_insights import (
            build_episode_insight_docs,
            write_episode_insights,
        )

        docs = build_episode_insight_docs(
            raw_payload=ti, episode_id=episode_id,
            podcaster=out["podcast_name"],
            # Real publish time; created_time fallback covers caches from before this field.
            podcast_launch_time=out.get("podcast_launch_time") or out.get("created_time"),
        )
        if docs:
            written = write_episode_insights(fs.db, episode_id=episode_id, docs=docs)
    print(f"ticker_insights written: {written} (with_tickers={with_tickers})")

    base = os.getenv("TINBOKER_PLATFORM_API_URL")
    if base:
        import httpx

        cache_fields = ["summary_content", "key_insights", "tags"] + (["related_tickers"] if with_tickers else [])
        cached = {k: doc_update.get(k, out.get(k)) for k in cache_fields}
        url = f"{base.rstrip('/')}/api/podcast/{quote(out['podcast_name'])}/episodes/{episode_id}"
        try:
            r = httpx.patch(url, json=cached, timeout=30.0)
            print(f"platform PATCH {url} -> {r.status_code}")
        except Exception as exc:  # noqa: BLE001
            print(f"platform PATCH failed ({exc}); cache may be stale until TTL")
    else:
        print("TINBOKER_PLATFORM_API_URL not set — skipped cache bust")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("episode_id")
    ap.add_argument("--commit", action="store_true", help="write Firestore + bust cache from the cached result")
    ap.add_argument("--with-tickers", action="store_true",
                    help="also write related_tickers + ticker_insights (off by default; LLM ticker resolution is noisy)")
    args = ap.parse_args()

    bootstrap()
    if args.commit:
        commit(args.episode_id, with_tickers=args.with_tickers)
    else:
        preview(generate(args.episode_id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
