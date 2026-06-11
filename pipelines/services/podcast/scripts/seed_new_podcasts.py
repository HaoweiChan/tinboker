#!/usr/bin/env python3
"""
Seed episodes for newly added podcasts: 威利財經角, 股市隱者, M觀點.

Phase 1 (fetch):  Fetch metadata + download MP3s + transcribe with Groq.
Phase 2 (upload): Read generated content from JSON and upload to Firestore.

Usage:
    python scripts/seed_new_podcasts.py fetch     # Phase 1
    python scripts/seed_new_podcasts.py upload     # Phase 2
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.secrets_bootstrap import bootstrap

bootstrap()

import requests
from src.service.firestore_service import FirestoreService
from src.service.gcs_storage_service import GCSStorageService
from src.service.speech_to_text import GroqService
from src.service.upload_to_firebase import FirebaseService

SEED_DIR = Path(__file__).parent / "seed_data"
SEED_DIR.mkdir(exist_ok=True)

PODCASTS = [
    {"name": "威利財經角", "api_id": "426819", "spotify_show": "https://open.spotify.com/show/1cfWGkNOClf7TdfpKRDoUv"},
    {"name": "股市隱者", "api_id": "4658079", "spotify_show": "https://open.spotify.com/show/0XxHVoRageDoUxUywWLBMy"},
    {"name": "M觀點", "api_id": "843399", "spotify_show": "https://open.spotify.com/show/3q2hc5Zsk9nFEYxXmMqVDW"},
]

MAX_EPISODES_PER_PODCAST = 5
CUTOFF_DAYS = 30


def log(msg: str):
    print(msg, flush=True)


def fetch_episodes_from_api(api_id: str) -> list[dict]:
    url = f"https://podcasttomp3.com/api/episodes?id={api_id}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def filter_recent(episodes: list[dict], days: int = CUTOFF_DAYS) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent = []
    for ep in episodes:
        dp = ep.get("datePublished", "")
        try:
            dt = datetime.fromisoformat(dp.replace("Z", "+00:00"))
            if dt >= cutoff:
                recent.append(ep)
        except (ValueError, TypeError):
            continue
    recent.sort(key=lambda e: e.get("datePublished", ""), reverse=True)
    return recent


def make_episode_id(podcast_name: str, episode_number: int, title: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]", "_", title)[:40]
    raw = f"{podcast_name}_{episode_number}_{slug}"
    h = hashlib.md5(raw.encode()).hexdigest()[:8]
    return f"ep_{h}"


def download_mp3(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 100_000:
        log(f"    Already downloaded: {dest.name}")
        return True
    try:
        resp = requests.get(url, stream=True, timeout=120, allow_redirects=True)
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        size_mb = dest.stat().st_size / (1024 * 1024)
        log(f"    Downloaded: {size_mb:.1f} MB")
        return True
    except Exception as e:
        log(f"    Download failed: {e}")
        return False


def transcribe_mp3(mp3_path: Path, groq_svc: GroqService) -> dict | None:
    try:
        result = groq_svc.transcribe(str(mp3_path), language="zh")
        return result
    except Exception as e:
        log(f"    Transcription failed: {e}")
        return None


def cmd_fetch(args):
    """Phase 1: Fetch metadata, download MP3s, transcribe."""
    groq_svc = GroqService(
        api_key=os.environ.get("GROQ_API_KEY"),
        language="zh",
        model="whisper-large-v3",
    )
    all_results = {}

    for podcast in PODCASTS:
        name = podcast["name"]
        api_id = podcast["api_id"]
        log(f"\n{'='*60}")
        log(f"Processing: {name} (API ID: {api_id})")
        log(f"{'='*60}")

        episodes = fetch_episodes_from_api(api_id)
        recent = filter_recent(episodes)[:MAX_EPISODES_PER_PODCAST]
        log(f"Found {len(recent)} recent episodes (max {MAX_EPISODES_PER_PODCAST})")

        podcast_results = []
        for i, ep in enumerate(recent):
            title = ep.get("title", "Untitled")
            ep_num = ep.get("episodeNumber", i)
            date_pub = ep.get("datePublished", "")
            ep_url = ep.get("episodeUrl", "")
            description = ep.get("description", "")
            ep_id = make_episode_id(name, ep_num, title)

            log(f"\n  [{i+1}/{len(recent)}] {title}")
            log(f"    Date: {date_pub[:10]}, EP#{ep_num}, ID: {ep_id}")

            result_file = SEED_DIR / f"{ep_id}.json"
            if result_file.exists():
                log("    Already processed, skipping")
                with open(result_file) as f:
                    podcast_results.append(json.load(f))
                continue

            if not ep_url:
                log("    No MP3 URL, skipping")
                continue

            mp3_dir = SEED_DIR / "mp3"
            mp3_dir.mkdir(exist_ok=True)
            mp3_path = mp3_dir / f"{ep_id}.mp3"
            log("    Downloading MP3...")
            if not download_mp3(ep_url, mp3_path):
                continue

            log("    Transcribing with Groq Whisper...")
            t0 = time.time()
            transcript_result = transcribe_mp3(mp3_path, groq_svc)
            if not transcript_result:
                continue
            elapsed = time.time() - t0
            transcript_text = transcript_result.get("text", "")
            log(f"    Transcribed: {len(transcript_text)} chars in {elapsed:.1f}s")

            result = {
                "episode_id": ep_id,
                "podcast_name": name,
                "episode_title": title,
                "episode_number": ep_num,
                "date_published": date_pub,
                "description": description,
                "episode_url": ep_url,
                "spotify_show_link": podcast["spotify_show"],
                "transcript": transcript_text,
                "sentences": transcript_result.get("sentences", []),
                "summary_content": None,
                "key_insights": None,
                "tags": None,
                "related_tickers": None,
            }
            with open(result_file, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            podcast_results.append(result)
            log(f"    Saved to {result_file.name}")

            # Keep the MP3 — the upload phase pushes it to GCS so the platform
            # player (signed-URL MP3 stream) can play the episode.
            log(f"    Kept MP3 for upload phase: {mp3_path.name}")

        all_results[name] = podcast_results

    log(f"\n{'='*60}")
    log("SUMMARY")
    log(f"{'='*60}")
    for name, results in all_results.items():
        log(f"  {name}: {len(results)} episodes")
    total = sum(len(r) for r in all_results.values())
    log(f"  Total: {total} episodes saved to {SEED_DIR}")
    log("\nNext: Generate content for each episode, then run 'upload'")


def upload_episode_media(
    gcs: GCSStorageService, data: dict, summary_content: str | None = None
) -> dict:
    """Upload MP3 + transcript + summary to GCS; return the URL fields for the doc.

    The platform player streams episodes via a signed URL resolved from
    ``mp3_url`` (PR #120), so an episode without it is unplayable — Spotify
    fields are null for these seeded shows.
    """
    ep_id = data["episode_id"]
    name = data["podcast_name"]

    mp3_path = SEED_DIR / "mp3" / f"{ep_id}.mp3"
    if not mp3_path.exists():
        ep_url = data.get("episode_url")
        if ep_url:
            log("    MP3 not on disk — re-downloading from source feed...")
            mp3_path.parent.mkdir(exist_ok=True)
            if not download_mp3(ep_url, mp3_path):
                mp3_path = None
        else:
            log("    WARNING: no local MP3 and no episode_url — mp3_url will stay null")
            mp3_path = None

    transcript_data = None
    if data.get("transcript"):
        transcript_data = {
            "text": data["transcript"],
            "sentences": data.get("sentences") or None,
        }

    urls = gcs.upload_episode_files(
        episode_id=ep_id,
        podcast_name=name,
        mp3_path=mp3_path,
        transcript_data=transcript_data,
        summary_content=summary_content or data.get("summary_content"),
        skip_existing=True,
    )
    return {
        k: urls.get(k)
        for k in (
            "mp3_url", "mp3_public_url",
            "transcript_url", "transcript_public_url",
            "summary_url", "summary_public_url",
        )
        if urls.get(k)
    }


def cmd_upload(args):
    """Phase 2: Upload media to GCS, then episode docs to Firestore."""
    fb = FirebaseService()
    fs = FirestoreService()
    gcs = GCSStorageService()

    episode_files = sorted(SEED_DIR.glob("ep_*.json"))
    log(f"Found {len(episode_files)} episode files to upload")

    for ep_file in episode_files:
        with open(ep_file, encoding="utf-8") as f:
            data = json.load(f)

        ep_id = data["episode_id"]
        name = data["podcast_name"]
        title = data.get("episode_title", "")

        if not data.get("summary_content"):
            log(f"  SKIP {ep_id} ({title[:40]}) — no generated content yet")
            continue

        log(f"\n  Uploading: {ep_id} | {name} | {title[:50]}")

        log("    Uploading media to GCS...")
        media_urls = upload_episode_media(gcs, data)
        if media_urls.get("mp3_url"):
            log(f"    MP3 -> {media_urls['mp3_url']}")
        else:
            log("    WARNING: episode has no MP3 in GCS — unplayable on the platform")

        dp = data.get("date_published", "")
        try:
            dt = datetime.fromisoformat(dp.replace("Z", "+00:00"))
            created_time_ms = int(dt.timestamp() * 1000)
            released_at_ms = created_time_ms
            release_date_str = dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            created_time_ms = int(datetime.now().timestamp() * 1000)
            released_at_ms = created_time_ms
            release_date_str = None

        episode_doc = {
            "id": ep_id,
            "podcast_name": name,
            "episode_title": title,
            "episode_number": data.get("episode_number"),
            "transcript": data.get("transcript", ""),
            "summary_content": data.get("summary_content", ""),
            "key_insights": data.get("key_insights", []),
            "related_tickers": data.get("related_tickers", []),
            "tags": data.get("tags", []),
            "created_time": created_time_ms,
            "released_at_ms": released_at_ms,
            "number_click": 0,
            "num_likes": 0,
            "schema_version": 2,
            "spotify_release_date": release_date_str,
            "spotify_images": [],
            "spotify_embed_url": None,
            "spotify_id": None,
            "spotify_url": None,
            "spotify_description": data.get("description", ""),
            "spotify_duration_ms": None,
            "mp3_url": None,
            "transcript_url": None,
            "summary_url": None,
            "summary_image_url": None,
            "events_markdown_url": None,
            "sentences_markdown_url": None,
        }
        episode_doc.update(media_urls)

        fs.set_document("episodes", ep_id, episode_doc, merge=True)
        log("    Written episode doc")

        tickers = data.get("related_tickers", [])
        tags = data.get("tags", [])

        for ticker in tickers:
            ticker_upper = ticker.upper().strip()
            if not ticker_upper:
                continue
            idx_data = {"episode_id": ep_id, "created_time": created_time_ms}
            ticker_ref = fs.db.collection("tickers").document(ticker_upper)
            ticker_ref.collection("episodes").document(ep_id).set(idx_data)
        if tickers:
            log(f"    Written {len(tickers)} ticker indices")

        for tag in tags:
            tag_lower = tag.lower().strip()
            if not tag_lower:
                continue
            idx_data = {"episode_id": ep_id, "created_time": created_time_ms}
            tag_ref = fs.db.collection("tags").document(tag_lower)
            tag_ref.collection("episodes").document(ep_id).set(idx_data)
        if tags:
            log(f"    Written {len(tags)} tag indices")

        if media_urls.get("mp3_url"):
            mp3_path = SEED_DIR / "mp3" / f"{ep_id}.mp3"
            if mp3_path.exists():
                mp3_path.unlink()
                log("    Cleaned up local MP3 (now in GCS)")

    log(f"\n{'='*60}")
    log("Writing podcast show documents...")
    for podcast in PODCASTS:
        name = podcast["name"]
        show_meta = {
            "podcast_name": name,
            "spotify_show_link": podcast["spotify_show"],
            "thumbnail_url": None,
            "thumbnails": [],
        }
        try:
            oembed_url = f"https://open.spotify.com/oembed?url={podcast['spotify_show']}"
            resp = requests.get(oembed_url, timeout=10)
            if resp.status_code == 200:
                oembed = resp.json()
                thumb = oembed.get("thumbnail_url")
                if thumb:
                    show_meta["thumbnail_url"] = thumb
                    show_meta["thumbnails"] = [thumb]
                    log(f"  {name}: got Spotify thumbnail")
        except Exception:
            pass
        fb.upsert_podcast_show(name, show_meta)
        log(f"  {name}: show doc written")

    log("\nDone! Check https://dev.tinboker.com/podcaster")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Seed new podcasts")
    sub = ap.add_subparsers(dest="command")
    sub.add_parser("fetch", help="Phase 1: fetch + transcribe")
    sub.add_parser("upload", help="Phase 2: upload to Firestore")
    args = ap.parse_args()

    if args.command == "fetch":
        cmd_fetch(args)
    elif args.command == "upload":
        cmd_upload(args)
    else:
        ap.print_help()
