#!/usr/bin/env python3
"""Inspect which Spotify / cover-image fields are populated on Firestore episodes.

Settles the question raised by the platform audit: "Podcast covers missing 19/20."
Either we are not writing them (real gap, fix on our side) or we are writing them
and the platform reads the wrong field (their bug).

For each show with a known image gap, this prints the most-recent N episodes and
reports which of these fields are present, missing, or empty:
  - spotify_id
  - spotify_url
  - spotify_embed_url
  - spotify_duration_ms
  - spotify_release_date
  - spotify_images   (list of cover URLs)
  - thumbnail_url    (legacy field if any)

Usage:
    uv run python services/podcast/scripts/inspect_episode_fields.py \
        --podcast "Gooaye 股癌" --limit 5
    uv run python services/podcast/scripts/inspect_episode_fields.py --all
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVICE_ROOT))

from src.service.upload_to_firebase import FirebaseService  # noqa: E402

FIELDS = [
    "spotify_id",
    "spotify_url",
    "spotify_embed_url",
    "spotify_duration_ms",
    "spotify_release_date",
    "spotify_images",
    "thumbnail_url",
]


def _summarize_episode(ep: dict) -> str:
    parts = []
    for f in FIELDS:
        v = ep.get(f, "MISSING")
        if v == "MISSING":
            parts.append(f"{f}=MISSING")
        elif v in (None, ""):
            parts.append(f"{f}=EMPTY")
        elif isinstance(v, list):
            parts.append(f"{f}=list[{len(v)}]")
        else:
            preview = str(v)
            if len(preview) > 60:
                preview = preview[:57] + "..."
            parts.append(f"{f}={preview!r}")
    return " | ".join(parts)


def _episodes_for_podcast(fb: FirebaseService, podcast_name: str, limit: int) -> list[dict]:
    # Use get_all_episodes (single-field index on created_time) and filter
    # client-side — avoids needing a composite (podcast_name, created_time) index.
    all_eps = fb.get_all_episodes(order_by="created_time", descending=True)
    matched = [ep for ep in all_eps if ep.get("podcast_name") == podcast_name]
    return matched[:limit]


def inspect_podcast(fb: FirebaseService, podcast_name: str, limit: int) -> None:
    eps = _episodes_for_podcast(fb, podcast_name, limit)
    print(f"\n=== {podcast_name} ({len(eps)} episodes shown) ===")
    for ep in eps:
        title = (ep.get("episode_title") or "")[:50]
        print(f"  {ep.get('id')}  {title!r}")
        print(f"    {_summarize_episode(ep)}")


def inspect_all(fb: FirebaseService, limit_per_podcast: int) -> None:
    all_eps = fb.get_all_episodes(order_by="created_time", descending=True)
    by_show: dict[str, list[dict]] = {}
    for ep in all_eps:
        by_show.setdefault(ep.get("podcast_name") or "<unknown>", []).append(ep)
    for podcast, eps in by_show.items():
        print(f"\n=== {podcast} ({len(eps)} total, showing {min(limit_per_podcast, len(eps))}) ===")
        for ep in eps[:limit_per_podcast]:
            title = (ep.get("episode_title") or "")[:50]
            print(f"  {ep.get('id')}  {title!r}")
            print(f"    {_summarize_episode(ep)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--podcast", help="single podcast name to inspect")
    ap.add_argument("--all", action="store_true", help="inspect every show")
    ap.add_argument("--limit", type=int, default=3, help="episodes per show (default 3)")
    args = ap.parse_args()

    if not args.podcast and not args.all:
        ap.error("specify --podcast NAME or --all")

    fb = FirebaseService()
    if args.podcast:
        inspect_podcast(fb, args.podcast, args.limit)
    else:
        inspect_all(fb, args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
