#!/usr/bin/env python3
"""Deterministic, token-free backfill script for skipped segments in Firestore.

This script parses existing summary headings to find the "kept" chapter timestamps,
downloads the transcript sentence list from GCS, identifies the skipped gaps,
classifies them using keyword heuristics (intro, chitchat, sponsor, qa, outro),
and commits the result as `skipped_segments` directly to Firestore.

Usage:
  # Dry run for a single episode
  uv run --package tinboker-podcast python services/podcast/scripts/backfill_skipped_segments.py <episode_id>

  # Commit changes for a single episode
  uv run --package tinboker-podcast python services/podcast/scripts/backfill_skipped_segments.py <episode_id> --commit

  # Dry run for all episodes of a specific podcast
  uv run --package tinboker-podcast python services/podcast/scripts/backfill_skipped_segments.py --podcast "股癌"

  # Commit changes for all episodes of a specific podcast
  uv run --package tinboker-podcast python services/podcast/scripts/backfill_skipped_segments.py --podcast "股癌" --commit
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

# Setup path so we can import internal service and shared modules
_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVICE_ROOT))

from src.secrets_bootstrap import bootstrap  # noqa: E402
from src.service.firestore_service import FirestoreService  # noqa: E402

SPONSOR_KEYWORDS = [
    "本集節目由", "贊助", "專屬優惠", "折扣碼", "優惠碼", "折價券", 
    "專屬連結", "點擊下方", "資訊欄", "折扣", "蝦皮", "床墊", 
    "床包", "代碼", "下單", "官網", "輸入", "折扣", "合作",
    "nordvpn", "surfshark", "pressplay", "hahow", "沙發"
]

QA_KEYWORDS = [
    "進入qa", "進到qa", "來讀qa", "聽眾提問", "五星好評", "五星留言", 
    "大家留言", "打氣", "評論區", "讀留言", "念留言", "五星吹捧",
    "下面一位", "第一位", "五星", "留言"
]


def _parse_gs(url: str) -> tuple[str, str]:
    p = urlparse(url)
    return p.netloc, p.path.lstrip("/")


def _load_sentences_from_gcs(transcript_url: str) -> tuple[list, str]:
    from google.cloud import storage

    bucket, blob = _parse_gs(transcript_url)
    raw = storage.Client(project=os.environ["GCP_PROJECT_ID"]).bucket(bucket).blob(blob).download_as_text()
    data = json.loads(raw)
    return data.get("sentences") or [], data.get("text", "")


def extract_summary_timestamps(markdown: str) -> list[int]:
    if not markdown:
        return []
    # Match pattern (#time:12345)
    matches = re.findall(r"\(#time:\s*(\d+)\)", markdown)
    timestamps = []
    for m in matches:
        try:
            val = int(m)
            # Filter out invalid or ordinal markers (e.g. 1-999 ms)
            if val == 0 or val >= 1000:
                timestamps.append(val)
        except ValueError:
            continue
    return sorted(list(set(timestamps)))


def is_sponsor_sentence(text: str) -> bool:
    if not text:
        return False
    text = text.replace(" ", "").replace("\n", "").lower()
    for kw in SPONSOR_KEYWORDS:
        if kw in text:
            return True
    return False


def detect_sponsor_ranges(sentences: list[dict], duration_ms: int) -> list[tuple[int, int]]:
    ranges = []
    in_block = False
    block_start = 0
    block_end = 0
    non_sponsor_count = 0
    sponsor_hits = 0

    for s in sentences:
        text = s.get("content") or s.get("text") or ""
        start = s.get("start")
        end = s.get("end")
        if start is None or end is None:
            continue

        if is_sponsor_sentence(text):
            sponsor_hits += 1
            if not in_block:
                in_block = True
                block_start = start
            block_end = end
            non_sponsor_count = 0
        elif in_block:
            non_sponsor_count += 1
            if non_sponsor_count > 4:
                # Require blocks to be at least 15s long with at least 2 matching hits
                if block_end - block_start >= 15000 and sponsor_hits >= 2:
                    ranges.append((block_start, block_end))
                in_block = False
                sponsor_hits = 0

    if in_block and block_end - block_start >= 15000 and sponsor_hits >= 2:
        ranges.append((block_start, block_end))

    return ranges


def detect_qa_start(sentences: list[dict], duration_ms: int) -> int | None:
    # QA section is usually in the last 40% of the episode
    qa_search_start = int(duration_ms * 0.60)
    for s in sentences:
        start = s.get("start")
        if start is None or start < qa_search_start:
            continue
        text = s.get("content") or s.get("text") or ""
        text = text.replace(" ", "").replace("\n", "").lower()
        for kw in QA_KEYWORDS:
            if kw in text:
                return start
    return None


def clip_to_gaps(start: int, end: int, kept_ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Return parts of [start, end] that do not overlap with any range in kept_ranges."""
    gaps = [(start, end)]
    for k_start, k_end in kept_ranges:
        next_gaps = []
        for g_start, g_end in gaps:
            # No overlap
            if g_end <= k_start or g_start >= k_end:
                next_gaps.append((g_start, g_end))
            else:
                # Overlap: shrink or split
                if g_start < k_start:
                    next_gaps.append((g_start, k_start))
                if g_end > k_end:
                    next_gaps.append((k_end, g_end))
        gaps = next_gaps
    # Only keep segments that are at least 10 seconds long to avoid noise
    return [g for g in gaps if g[1] - g[0] >= 10000]


def backfill_episode(fs: FirestoreService, episode_id: str, commit: bool) -> bool:
    doc = fs.get_document("episodes", episode_id)
    if not doc:
        print(f"❌ Episode {episode_id} not found in Firestore")
        return False

    summary = doc.get("modified_summary_content") or doc.get("summary_content") or ""
    if not summary and doc.get("summary_url"):
        try:
            from google.cloud import storage
            bucket_name, blob_name = _parse_gs(doc.get("summary_url"))
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_name)
            summary = blob.download_as_text()
        except Exception as e:
            print(f"⚠️ Failed to load summary from GCS for {episode_id}: {e}")

    kept_starts = extract_summary_timestamps(summary)
    if not kept_starts:
        print(f"⚠️ Episode {episode_id} has no valid timestamp markers in summary. Skipping.")
        return False

    transcript_url = doc.get("transcript_url")
    if not transcript_url:
        print(f"⚠️ Episode {episode_id} has no transcript_url. Skipping.")
        return False

    try:
        sentences, _ = _load_sentences_from_gcs(transcript_url)
    except Exception as e:
        print(f"❌ Failed to load transcript from GCS for {episode_id}: {e}")
        return False

    if not sentences:
        print(f"⚠️ Transcript JSON for {episode_id} has no sentences. Skipping.")
        return False

    # Find duration
    last_sentence = sentences[-1]
    duration_ms = last_sentence.get("end") or last_sentence.get("start") or 0
    if duration_ms <= 0:
        print(f"⚠️ Invalid duration for {episode_id}. Skipping.")
        return False

    # Run Heuristics
    qa_start_ms = detect_qa_start(sentences, duration_ms)
    sponsor_ranges = detect_sponsor_ranges(sentences, duration_ms)

    # Build kept ranges
    kept_ranges = []
    for i in range(len(kept_starts)):
        start = kept_starts[i]
        if i + 1 < len(kept_starts):
            next_start = kept_starts[i+1]
            if qa_start_ms and start < qa_start_ms < next_start:
                end = qa_start_ms
            else:
                end = next_start
        else:
            end = qa_start_ms if qa_start_ms and qa_start_ms > start else duration_ms
        if start < end:
            kept_ranges.append((start, end))

    # Candidates list
    candidates = []

    # 1. Intro
    intro_end = min(kept_starts[0], 90000)
    if intro_end > 10000:
        candidates.append((0, intro_end, "intro", "開場"))

    # 2. Chitchat
    if kept_starts[0] > intro_end:
        candidates.append((intro_end, kept_starts[0], "chitchat", "生活閒聊"))

    # 3. Sponsors
    for start, end in sponsor_ranges:
        candidates.append((start, end, "sponsor", "業配 / 廣告"))

    # 4. QA & Outro
    if qa_start_ms:
        outro_start = duration_ms - 45000
        if outro_start > qa_start_ms:
            candidates.append((qa_start_ms, outro_start, "qa", "聽眾來信"))
            candidates.append((outro_start, duration_ms, "outro", "結尾"))
    else:
        # 5. Outro (only if no QA captured it)
        candidates.append((duration_ms - 45000, duration_ms, "outro", "結尾"))

    # Clip candidates against kept ranges to avoid overlapping financial summary chapters
    skipped_segments = []
    for c_start, c_end, c_type, c_label in candidates:
        gaps = clip_to_gaps(c_start, c_end, kept_ranges)
        for g_start, g_end in gaps:
            skipped_segments.append({
                "segment_type": c_type,
                "label": c_label,
                "section_topic": "",
                "start": g_start,
                "end": g_end
            })

    # Sort by start time
    skipped_segments.sort(key=lambda x: x["start"])

    # Print summary
    print(f"\nEpisode: {doc.get('episode_title') or episode_id} ({episode_id})")
    print(f"Duration: {duration_ms // 1000}s | Kept chapters: {len(kept_starts)}")
    if qa_start_ms:
        print(f"QA detected starting at: {qa_start_ms // 1000}s")
    print(f"Generated {len(skipped_segments)} skipped segments:")
    for seg in skipped_segments:
        start_s = seg["start"] // 1000
        end_s = seg["end"] // 1000
        print(f"  [{seg['segment_type']}] {seg['label']} ({start_s // 60:02d}:{start_s % 60:02d} -> {end_s // 60:02d}:{end_s % 60:02d})")

    if not skipped_segments:
        print("No skippable segments generated.")
        return True

    if commit:
        fs.set_document("episodes", episode_id, {"skipped_segments": skipped_segments}, merge=True)
        print(f"✅ Successfully committed skipped_segments to episodes/{episode_id}")
    else:
        print("ℹ️ Dry-run mode: Firestore write skipped. Run with --commit to apply changes.")

    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("episode_id", nargs="?", help="Episode ID to backfill")
    ap.add_argument("--podcast", help="Podcast name to backfill all episodes for")
    ap.add_argument("--all", action="store_true", help="Backfill all episodes in the collection")
    ap.add_argument("--commit", action="store_true", help="Write changes to Firestore")
    args = ap.parse_args()

    bootstrap()
    fs = FirestoreService()

    if args.episode_id:
        backfill_episode(fs, args.episode_id, args.commit)
    elif args.podcast:
        print(f"Fetching episodes for podcast: {args.podcast}")
        docs = fs.db.collection("episodes").where("podcast_name", "==", args.podcast).stream()
        count = 0
        success = 0
        for doc in docs:
            count += 1
            if backfill_episode(fs, doc.id, args.commit):
                success += 1
        print(f"\nDone. Processed {success}/{count} episodes successfully.")
    elif args.all:
        print("Fetching all episodes in the collection")
        docs = fs.db.collection("episodes").stream()
        count = 0
        success = 0
        for doc in docs:
            count += 1
            if backfill_episode(fs, doc.id, args.commit):
                success += 1
        print(f"\nDone. Processed {success}/{count} episodes successfully.")
    else:
        ap.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main())
