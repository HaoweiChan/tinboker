#!/usr/bin/env python3
"""
Populate Firestore `podcasts` collection with show-level metadata.

Strategy:
  1. Read podcasts_to_download.json for canonical names + spotify links.
  2. For each podcast, find an episode in Firestore that has `spotify_images`
     and use that as the show thumbnail (Spotify episode images typically
     inherit the show artwork).
  3. Write show-level metadata to the `podcasts` collection so the platform
     has a reliable, single source for thumbnails.

Usage:
    python scripts/populate_podcast_shows.py           # populate all
    python scripts/populate_podcast_shows.py --dry-run  # preview without writing
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.secrets_bootstrap import bootstrap

bootstrap()

import requests
from src.service.upload_to_firebase import FirebaseService

GCP_PROJECT = "gen-lang-client-0901363254"
DB_ID = os.getenv("FIRESTORE_DATABASE_ID", "graphfolio-db")
BASE_URL = (
    f"https://firestore.googleapis.com/v1/projects/{GCP_PROJECT}"
    f"/databases/{DB_ID}/documents"
)


def load_podcasts() -> list[dict]:
    path = Path(__file__).parent.parent / "podcasts_to_download.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_access_token() -> str:
    """Get GCP access token via gcloud for REST API calls."""
    import subprocess
    result = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def find_thumbnail_from_episodes(gcp_token: str, podcast_name: str) -> list[str]:
    """
    Scan episodes in Firestore REST API to find one with spotify_images.
    Returns list of image URLs (largest first) or empty list.
    """
    headers = {"Authorization": f"Bearer {gcp_token}"}
    page_token = None
    while True:
        params = {"pageSize": "300"}
        if page_token:
            params["pageToken"] = page_token
        resp = requests.get(f"{BASE_URL}/episodes", headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        for doc in data.get("documents", []):
            fields = doc.get("fields", {})
            pn = fields.get("podcast_name", {}).get("stringValue", "")
            if pn != podcast_name:
                continue
            si = fields.get("spotify_images", {}).get("arrayValue", {}).get("values", [])
            imgs = [v.get("stringValue", "") for v in si if v.get("stringValue")]
            if imgs:
                return imgs
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return []


def main():
    ap = argparse.ArgumentParser(description="Populate podcast show metadata")
    ap.add_argument("--dry-run", action="store_true", help="Preview without writing to Firestore")
    args = ap.parse_args()

    podcasts = load_podcasts()
    print(f"Loaded {len(podcasts)} podcasts from podcasts_to_download.json\n")

    gcp_token = get_access_token()
    fb = FirebaseService() if not args.dry_run else None

    success, no_images = 0, 0
    for podcast in podcasts:
        name = podcast["name"]
        spotify_link = podcast.get("spotify_show_link", "")
        print(f"[{name}]")

        images = find_thumbnail_from_episodes(gcp_token, name)
        meta = {
            "thumbnail_url": images[0] if images else None,
            "thumbnails": images,
            "spotify_show_link": spotify_link,
        }

        if images:
            print(f"  Thumbnail: {images[0]}")
            print(f"  Total sizes: {len(images)}")
        else:
            print("  No thumbnail found in episodes")
            no_images += 1

        if args.dry_run:
            print(f"  [DRY RUN] Would write to podcasts/{name}")
        else:
            fb.upsert_podcast_show(name, meta)
            print("  Written to Firestore")
        success += 1
        print()

    print(f"Done: {success} processed, {no_images} without thumbnails")


if __name__ == "__main__":
    main()
