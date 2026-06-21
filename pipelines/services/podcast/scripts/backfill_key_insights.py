#!/usr/bin/env python3
"""Backfill ``episodes/{episode_id}.key_insights`` in Firestore.

For each episode this script:
  1. Skips it if ``key_insights`` is already populated (unless ``--overwrite``).
  2. Fetches the episode's summary markdown — ``summary_url`` (gs://) first, then
     any https summary URL — which is the best source for the takeaways.
  3. Runs the SAME extractor the live pipeline uses
     (``extract_key_insights_from_markdown``) → 3–8 plain-text zh-TW strings.
  4. Writes them back with ``doc_ref.update({"key_insights": [...]})``.

The ``update()`` call is a partial write: it touches ONLY ``key_insights`` and
leaves every other field — including the platform-owned ``modified_*`` fields and
the immutable ``created_time`` — untouched. Idempotent: re-running overwrites
``key_insights`` with a fresh build and never duplicates data.

Requires (loaded from Google Secret Manager via ``secrets_bootstrap`` on the VPS,
or set in the environment locally):
    OPENROUTER_API_KEY                  the OpenRouter key for the extractor
    GCP_CREDENTIALS_JSON / _PATH        Firestore + GCS access
    FIRESTORE_DATABASE_ID               (optional) non-default database

Usage:
    uv run python services/podcast/scripts/backfill_key_insights.py --dry-run --limit 5
    uv run python services/podcast/scripts/backfill_key_insights.py --limit 20
    uv run python services/podcast/scripts/backfill_key_insights.py            # full run
    uv run python services/podcast/scripts/backfill_key_insights.py --overwrite # regenerate all
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.request
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVICE_ROOT))
sys.path.insert(0, str(_SERVICE_ROOT / "src"))

# Load secrets from GSM (idempotent; no-op if env vars already set).
try:
    from src.secrets_bootstrap import bootstrap  # noqa: E402

    bootstrap()
except Exception as _e:  # noqa: BLE001 — local runs may already have env vars set
    print(f"  (secrets_bootstrap skipped: {_e})")

from firebase_admin import firestore  # noqa: E402 — for DELETE_FIELD on cleanup
from src.podcast.content_builder.nodes.key_insights_extractor import (  # noqa: E402
    extract_key_insights_from_markdown,
    is_placeholder_summary,
)
from src.service.upload_to_firebase import FirebaseService  # noqa: E402


def _read_gcs_text(gs_url: str) -> str | None:
    """Download a gs:// object as UTF-8 text (reads are safe cross-bucket)."""
    if not gs_url or not gs_url.startswith("gs://"):
        return None
    bucket, _, path = gs_url[5:].partition("/")
    from google.cloud import storage

    blob = storage.Client().bucket(bucket).blob(path)
    return blob.download_as_text(encoding="utf-8")


def _read_http_text(url: str) -> str | None:
    """Download an http(s) text resource (VPS-migrated summary URLs)."""
    if not url or not url.startswith(("http://", "https://")):
        return None
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 — trusted own URLs
        return resp.read().decode("utf-8")


def _fetch_summary_markdown(ep: dict) -> str | None:
    """Resolve the episode's summary markdown from its stored URLs.

    Prefers the canonical gs:// ``summary_url``; falls back to https URLs for
    episodes whose URLs were migrated to the VPS.
    """
    for key in ("summary_url", "summary_public_url"):
        url = ep.get(key)
        if not url:
            continue
        try:
            if url.startswith("gs://"):
                text = _read_gcs_text(url)
            else:
                text = _read_http_text(url)
        except Exception as e:  # noqa: BLE001 — try the next candidate URL
            print(f"      fetch failed for {key}={url}: {e}")
            continue
        if text and text.strip():
            return text
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="extract but don't write to Firestore")
    ap.add_argument("--limit", type=int, help="process at most N episodes")
    ap.add_argument("--overwrite", action="store_true", help="regenerate even if key_insights already set")
    ap.add_argument("--podcast", help="only process episodes whose podcast_name matches this exactly")
    args = ap.parse_args()

    if not os.getenv("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY is not set — the extractor needs it.", file=sys.stderr)
        return 2

    fb = FirebaseService()
    print("Streaming episodes from Firestore...")
    episodes = fb.get_all_episodes(order_by="created_time", descending=True)
    if args.podcast:
        episodes = [ep for ep in episodes if ep.get("podcast_name") == args.podcast]
    if args.limit:
        episodes = episodes[: args.limit]  # cap episodes *examined* (testing)
    total = len(episodes)
    print(f"  {total} episodes to examine"
          f"{f' (podcast={args.podcast})' if args.podcast else ''}"
          f"{f' [--limit {args.limit}]' if args.limit else ''}\n")

    written = cleared = already = placeholder = short = 0
    no_summary: list[str] = []
    failed: list[str] = []
    for i, ep in enumerate(episodes, 1):
        ep_id = ep.get("id")
        if not ep_id:
            failed.append("<no-id>")
            continue
        existing = ep.get("key_insights")
        title = (ep.get("episode_title") or "")[:40]

        markdown = _fetch_summary_markdown(ep)
        if not markdown:
            print(f"  [{i}/{total}] {ep_id}: no usable summary — skip")
            no_summary.append(ep_id)
            continue

        # Placeholder summaries yield generic junk — never generate insights for
        # them. If a previous run already wrote some, clear the field so the
        # platform falls back to its teaser (absent key_insights is valid).
        if is_placeholder_summary(markdown):
            if existing:
                if not args.dry_run:
                    fb.db.collection("episodes").document(ep_id).update(
                        {"key_insights": firestore.DELETE_FIELD}
                    )
                cleared += 1
                verb = "would clear" if args.dry_run else "cleared"
                print(f"  [{i}/{total}] {ep_id}: placeholder summary — {verb} stale key_insights")
            else:
                placeholder += 1
            continue

        if existing and not args.overwrite:
            already += 1
            continue

        insights = extract_key_insights_from_markdown(
            markdown=markdown,
            source=ep.get("podcast_name") or "Podcast",
            episode_title=ep.get("episode_title") or "Episode",
        )
        if not insights:
            print(f"  [{i}/{total}] {ep_id}: extractor returned nothing — skip")
            failed.append(ep_id)
            continue
        if len(insights) < 3:
            short += 1
            print(f"  [{i}/{total}] {ep_id}: only {len(insights)} insights (<3) — {title}")

        if args.dry_run:
            print(f"  [{i}/{total}] {ep_id}: would write {len(insights)} — {insights[0]}")
            written += 1
            continue
        try:
            # Partial update: touches ONLY key_insights. modified_*/created_time untouched.
            fb.db.collection("episodes").document(ep_id).update({"key_insights": insights})
            written += 1
            print(f"  [{i}/{total}] {ep_id}: wrote {len(insights)} — {insights[0]}")
        except Exception as e:  # noqa: BLE001
            print(f"  [{i}/{total}] {ep_id}: write failed ({e})")
            failed.append(ep_id)

    wv = "would write" if args.dry_run else "wrote"
    print(
        f"\n{wv} {written} | cleared {cleared} placeholder-junk | "
        f"{already} already populated | {placeholder} placeholder-empty | "
        f"{len(no_summary)} no-summary | {len(failed)} failed "
        f"({short} had <3 items)"
    )
    if no_summary:
        print(f"no-summary: {no_summary[:10]}{'...' if len(no_summary) > 10 else ''}")
    if failed:
        print(f"failed: {failed[:10]}{'...' if len(failed) > 10 else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
