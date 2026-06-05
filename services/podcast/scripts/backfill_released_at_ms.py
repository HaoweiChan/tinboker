#!/usr/bin/env python3
"""Backfill ``episodes/{episode_id}.released_at_ms`` from the feed publish date.

`released_at_ms` is the episode's TRUE publish time (handoff spec §2.3 #1). For
historical docs it was derived from ``spotify_release_date`` (null for ~all zh-TW
episodes) or ``created_time`` (the ingestion/backfill time — clusters on the day
the batch ran, not when the episode aired). The reliable value is the feed
``datePublished`` returned by the podcasttomp3 API for every episode.

For each FOLLOWED show this script:
  1. Resolves the show list exactly like the live pipeline (platform /api/sources
     → Postgres registry → ``podcasts_tw.json``), so it targets the same set.
  2. Re-fetches the feed (``fetch_episodes`` → ``datePublished`` for every episode).
  3. Matches existing Firestore docs by ``podcast_name`` + ``episode_title``
     (+ ``episode_number`` when present), with a title+number fallback for docs
     whose ``podcast_name`` differs from the configured name.
  4. Sets ONLY ``released_at_ms`` via a partial ``update()``.

It NEVER touches ``created_time`` — mutating it re-fires ``new_episode``
notifications (handoff spec §6.3). No Spotify dependency.

DRY-RUN BY DEFAULT: prints what it WOULD write and changes nothing. Pass
``--apply`` to actually write.

Requires (loaded from Google Secret Manager via ``secrets_bootstrap`` on the VPS,
or set in the environment locally):
    GCP_CREDENTIALS_JSON / _PATH        Firestore access
    FIRESTORE_DATABASE_ID               (optional) non-default database

Usage:
    uv run python services/podcast/scripts/backfill_released_at_ms.py            # dry-run (default)
    uv run python services/podcast/scripts/backfill_released_at_ms.py --podcast "Gooaye 股癌" --limit 5
    uv run python services/podcast/scripts/backfill_released_at_ms.py --apply    # actually write
    uv run python services/podcast/scripts/backfill_released_at_ms.py --apply --overwrite
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVICE_ROOT))
sys.path.insert(0, str(_SERVICE_ROOT / "src"))

# Load secrets from GSM (idempotent; no-op if env vars already set).
try:
    from src.secrets_bootstrap import bootstrap  # noqa: E402

    bootstrap()
except Exception as _e:  # noqa: BLE001 — local runs may already have env vars set
    print(f"  (secrets_bootstrap skipped: {_e})")

from src.podcast.orchestrator import (  # noqa: E402
    _load_podcasts_from_db,
    _load_podcasts_from_platform,
    _parse_episode_date,
    load_podcasts_config,
)
from src.service.download_podcasts import (  # noqa: E402
    extract_podcast_id,
    fetch_episodes,
)
from src.service.upload_to_firebase import FirebaseService  # noqa: E402


def _resolve_followed_shows(config_file: Path) -> List[Dict]:
    """Resolve the followed-show list the same way the live pipeline does:
    platform /api/sources → Postgres registry → JSON config fallback.
    """
    podcasts = _load_podcasts_from_platform()
    if podcasts is None:
        podcasts = _load_podcasts_from_db()
    if podcasts is None:
        podcasts = load_podcasts_config(config_file)
    return podcasts or []


def _date_published_to_ms(value: object) -> Optional[int]:
    """Parse a feed ``datePublished`` (ISO-8601) into Unix milliseconds."""
    dt = _parse_episode_date(value)
    if dt is None:
        return None
    return int(dt.timestamp() * 1000)


def _match_episode_doc(fb: FirebaseService, podcast_name: str, ep: Dict) -> Optional[Dict]:
    """Find the Firestore doc for a feed episode by title (+ number when present).

    Tries the canonical (podcast_name, title, number) query first, then falls
    back to (title, number) for docs whose stored ``podcast_name`` differs.
    """
    title = ep.get("title")
    number = ep.get("episodeNumber")
    if not title:
        return None
    doc = fb.get_episode_by_fields(podcast_name, title, number)
    if doc is None:
        doc = fb.get_episode_by_title_and_number(title, number)
    return doc


def _fmt_ms(ms: Optional[int]) -> str:
    if ms is None:
        return "—"
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="actually write to Firestore (default is a dry run that writes nothing)",
    )
    ap.add_argument(
        "--overwrite",
        action="store_true",
        help="rewrite released_at_ms even when it already differs from created_time-derived value",
    )
    ap.add_argument("--podcast", help="only process the show whose name matches this exactly")
    ap.add_argument("--limit", type=int, help="process at most N episodes per show")
    ap.add_argument(
        "--config-file",
        type=Path,
        default=_SERVICE_ROOT / "podcasts_tw.json",
        help="JSON show config used only if platform/DB sources are unavailable",
    )
    args = ap.parse_args()
    dry_run = not args.apply

    shows = _resolve_followed_shows(args.config_file)
    if args.podcast:
        shows = [s for s in shows if s.get("name") == args.podcast]
    if not shows:
        print("No followed shows resolved — nothing to do.")
        return 0

    mode = "DRY-RUN (no writes)" if dry_run else "APPLY (writing released_at_ms)"
    print(f"{mode} — {len(shows)} show(s)\n")

    fb = FirebaseService()
    would_write = no_date = no_match = unchanged = failed = 0

    for show in shows:
        name = show.get("name")
        link = show.get("link")
        if not name or not link:
            print(f"  skip invalid show entry: {show!r}")
            continue
        try:
            podcast_id = extract_podcast_id(link)
        except ValueError as e:
            print(f"  [{name}] bad feed link, skipping: {e}")
            continue

        episodes = fetch_episodes(podcast_id)
        if args.limit:
            episodes = episodes[: args.limit]
        print(f"  [{name}] {len(episodes)} feed episode(s)")

        for ep in episodes:
            title = (ep.get("title") or "")[:48]
            new_ms = _date_published_to_ms(ep.get("datePublished"))
            if new_ms is None:
                no_date += 1
                continue

            doc = _match_episode_doc(fb, name, ep)
            if doc is None:
                no_match += 1
                continue

            ep_id = doc.get("id")
            current_ms = doc.get("released_at_ms")
            # Skip when already correct. Without --overwrite we also leave docs
            # alone when their stored value already matches the feed date.
            if current_ms == new_ms and not args.overwrite:
                unchanged += 1
                continue

            verb = "would set" if dry_run else "set"
            print(
                f"      {ep_id}: {verb} released_at_ms "
                f"{_fmt_ms(current_ms)} -> {_fmt_ms(new_ms)}  | {title}"
            )
            if dry_run:
                would_write += 1
                continue
            try:
                # Partial update: touches ONLY released_at_ms. created_time and
                # every other field are left untouched (no new_episode re-fire).
                fb.update_episode_fields(ep_id, {"released_at_ms": new_ms})
                would_write += 1
            except Exception as e:  # noqa: BLE001
                print(f"      {ep_id}: write failed ({e})")
                failed += 1

    wv = "would write" if dry_run else "wrote"
    print(
        f"\n{wv} {would_write} | {unchanged} already-correct | "
        f"{no_match} feed-episode-not-in-firestore | {no_date} no-datePublished | "
        f"{failed} failed"
    )
    if dry_run:
        print("\nDry run — nothing was written. Re-run with --apply to commit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
