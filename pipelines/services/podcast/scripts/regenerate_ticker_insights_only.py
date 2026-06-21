#!/usr/bin/env python3
"""Regenerate only ticker insights for existing podcast episodes.

This is the cheap repair path for stock insight cards. It reuses already-stored
episode artifacts and runs only the ticker insight extractor:

  1. Read transcript sentences from ``episodes/{id}.transcript_url``.
  2. Prefer cached ``events_markdown`` to reconstruct event ranges without an
     extra LLM call.
  3. Cluster the reconstructed financial events deterministically.
  4. Run only ``ticker_extractor`` and write ``ticker_insights/{episode}/tickers``.

If an episode has no cached events markdown, the script skips it by default to
save API cost. Pass ``--allow-event-extract`` to spend one additional LLM call
for those episodes.

Usage:
    uv run python services/podcast/scripts/regenerate_ticker_insights_only.py --ticker 2330 --list-only --limit 10
    uv run python services/podcast/scripts/regenerate_ticker_insights_only.py --ticker 2330 --dry-run --limit 10
    uv run python services/podcast/scripts/regenerate_ticker_insights_only.py --episode EPISODE_ID
    uv run python services/podcast/scripts/regenerate_ticker_insights_only.py --ticker EEM --allow-event-extract
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
_PIPELINES_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_SERVICE_ROOT))
sys.path.insert(0, str(_SERVICE_ROOT / "src"))
sys.path.insert(0, str(_PIPELINES_ROOT / "libs" / "shared" / "src"))

# Load GSM secrets when available. Local env vars still win.
try:
    from src.secrets_bootstrap import bootstrap  # noqa: E402

    bootstrap()
except Exception as _e:  # noqa: BLE001
    print(f"  (secrets_bootstrap skipped: {_e})")

from shared.tickers import canonical_symbol  # noqa: E402
from src.podcast.content_builder.nodes.clusterer import cluster_sentences  # noqa: E402
from src.podcast.content_builder.nodes.extractor import extract_events  # noqa: E402
from src.podcast.content_builder.nodes.ticker_extractor import extract_tickers  # noqa: E402
from src.podcast.exporters.ticker_insights import (  # noqa: E402
    build_episode_insight_docs,
    write_episode_insights,
)
from src.service.gcs_storage_service import GCSStorageService  # noqa: E402
from src.service.upload_to_firebase import FirebaseService  # noqa: E402

_EVENT_HEADING_RE = re.compile(r"^##\s+(?P<topic>.*?)(?:\s+\(#time:[^)]+\))?\s*$")
_EVENT_INDICES_RE = re.compile(r"Indices:\s*(?P<start>\d+)\s*-\s*(?P<end>\d+)")


def _canonical_ticker(value: str) -> str:
    return canonical_symbol(value.strip().upper())


def _episode_tickers(ep: dict[str, Any]) -> set[str]:
    tickers: set[str] = set()
    for key in ("related_tickers", "tickers", "ticker_symbols"):
        values = ep.get(key)
        if isinstance(values, list):
            tickers.update(_canonical_ticker(str(v)) for v in values if v)
    return tickers


def _read_http_text(url: str) -> str | None:
    if not url.startswith(("http://", "https://")):
        return None
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 - own stored URLs
        return resp.read().decode("utf-8")


def _read_http_json(url: str) -> dict[str, Any] | None:
    text = _read_http_text(url)
    if not text:
        return None
    parsed = json.loads(text)
    return parsed if isinstance(parsed, dict) else {"text": text}


def parse_events_markdown(markdown: str) -> list[dict[str, Any]]:
    """Parse cached events markdown back into extractor-style event ranges."""
    events: list[dict[str, Any]] = []
    current_topic: str | None = None

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        heading = _EVENT_HEADING_RE.match(line)
        if heading:
            current_topic = heading.group("topic").strip()
            continue

        indices = _EVENT_INDICES_RE.search(line)
        if current_topic and indices:
            start = int(indices.group("start"))
            end = int(indices.group("end"))
            if end >= start:
                events.append(
                    {
                        "section_topic": current_topic,
                        "start_index": start,
                        "end_index": end,
                    }
                )
            current_topic = None

    return events


def _fetch_events_markdown(ep: dict[str, Any], gcs: GCSStorageService) -> str | None:
    content = ep.get("events_markdown_content")
    if isinstance(content, str) and content.strip():
        return content

    for key in ("events_markdown_url", "events_markdown_public_url"):
        url = ep.get(key)
        if not isinstance(url, str) or not url:
            continue
        try:
            if url.startswith("gs://"):
                return gcs.download_text_by_gcs_url(url)
            return _read_http_text(url)
        except Exception as e:  # noqa: BLE001 - fall through to next URL
            print(f"      could not read {key}: {e}")
    return None


def _fetch_transcript(ep: dict[str, Any], gcs: GCSStorageService) -> dict[str, Any] | None:
    url = ep.get("transcript_url") or ep.get("transcript_public_url")
    if not isinstance(url, str) or not url:
        return None
    try:
        if url.startswith("gs://"):
            return gcs.download_transcript_by_gcs_url(url)
        return _read_http_json(url)
    except Exception as e:  # noqa: BLE001
        print(f"      could not read transcript: {e}")
        return None


def _launch_time(ep: dict[str, Any]) -> Any:
    for key in ("spotify_release_date", "published_at", "release_date"):
        value = ep.get(key)
        if value:
            return value
    for key in ("released_at_ms", "created_time"):
        value = ep.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return datetime.fromtimestamp(value / 1000, timezone.utc)
    return datetime.now(timezone.utc)


def _select_episodes(fb: FirebaseService, args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.episode:
        episodes: list[dict[str, Any]] = []
        for episode_id in args.episode:
            ep = fb.get_episode_by_id(episode_id)
            if ep:
                episodes.append(ep)
            else:
                print(f"  episode not found: {episode_id}")
        return episodes

    episodes = fb.get_all_episodes(order_by="created_time", descending=True)
    if args.podcast:
        episodes = [ep for ep in episodes if ep.get("podcast_name") == args.podcast]
    if args.ticker:
        wanted = {_canonical_ticker(ticker) for ticker in args.ticker}
        episodes = [ep for ep in episodes if _episode_tickers(ep) & wanted]
    if args.limit:
        episodes = episodes[: args.limit]
    return episodes


def _cache_raw_ticker_insights(
    *,
    fb: FirebaseService,
    gcs: GCSStorageService,
    ep: dict[str, Any],
    raw_payload: Any,
) -> None:
    ep_id = ep["id"]
    podcast_name = ep.get("podcast_name") or "Podcast"
    raw_json = json.dumps(raw_payload, ensure_ascii=False, indent=2)
    success, gcs_url = gcs.upload_file_from_string(
        raw_json,
        "ticker_insights",
        podcast_name,
        ep_id,
        "json",
        skip_existing=False,
    )
    if not success or not gcs_url:
        return

    blob_path = gcs_url.replace(f"gs://{gcs.bucket_name}/", "")
    fb.update_episode_fields(
        ep_id,
        {
            "ticker_insights_url": gcs_url,
            "ticker_insights_public_url": gcs.generate_public_url(blob_path),
        },
    )


def _generate_raw_payload(
    *,
    ep: dict[str, Any],
    gcs: GCSStorageService,
    allow_event_extract: bool,
) -> tuple[Any | None, str]:
    transcript = _fetch_transcript(ep, gcs)
    if not transcript:
        return None, "no transcript"

    sentences = transcript.get("sentences")
    if not isinstance(sentences, list) or not sentences:
        return None, "transcript has no sentence timing"

    events_md = _fetch_events_markdown(ep, gcs)
    events = parse_events_markdown(events_md) if events_md else []
    source = "cached-events"

    if not events:
        if not allow_event_extract:
            return None, "no cached events; pass --allow-event-extract to regenerate them"
        events = extract_events(
            {
                "sentences": sentences,
                "source": ep.get("podcast_name") or "Podcast",
                "episode_title": ep.get("episode_title") or "Episode",
            }
        ).get("events", [])
        source = "event-extractor"

    clustered_events = cluster_sentences(
        {
            "events": events,
            "sentences": sentences,
        }
    ).get("clustered_events", [])
    if not clustered_events:
        return None, f"{source} produced no financial event clusters"

    raw_payload = extract_tickers(
        {
            "clustered_events": clustered_events,
            "source": ep.get("podcast_name") or "Podcast",
            "episode_title": ep.get("episode_title") or "Episode",
        }
    ).get("ticker_insights")
    return raw_payload, f"{source}; {len(clustered_events)} clusters"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="extract but don't write Firestore/GCS")
    ap.add_argument("--limit", type=int, help="process at most N matching episodes")
    ap.add_argument("--episode", action="append", help="episode id to process; can be repeated")
    ap.add_argument("--ticker", action="append", help="only process episodes tagged with this ticker; can be repeated")
    ap.add_argument("--podcast", help="only process episodes from this exact podcast_name")
    ap.add_argument("--list-only", action="store_true", help="show selected episodes and cache readiness; no LLM calls")
    ap.add_argument(
        "--allow-event-extract",
        action="store_true",
        help="run event extraction when cached events markdown is missing (extra LLM call)",
    )
    ap.add_argument(
        "--skip-gcs-cache",
        action="store_true",
        help="write Firestore docs only; don't refresh the raw ticker_insights JSON URL on episodes",
    )
    args = ap.parse_args()

    if not args.list_only and not os.getenv("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY is not set; ticker extraction needs it.", file=sys.stderr)
        return 2

    fb = FirebaseService()
    gcs = GCSStorageService()
    targets = _select_episodes(fb, args)
    print(f"Selected {len(targets)} episode(s).")

    if args.list_only:
        ready = 0
        for index, ep in enumerate(targets, 1):
            ep_id = ep.get("id") or "<no-id>"
            transcript = _fetch_transcript(ep, gcs)
            sentences = transcript.get("sentences") if transcript else None
            events_md = _fetch_events_markdown(ep, gcs)
            events = parse_events_markdown(events_md) if events_md else []
            if isinstance(sentences, list) and sentences and events:
                ready += 1
                status = f"ready: {len(events)} cached events, {len(sentences)} sentences"
            elif isinstance(sentences, list) and sentences:
                status = f"needs --allow-event-extract: {len(sentences)} sentences, no cached events"
            else:
                status = "skip: no transcript sentence timing"
            print(f"  [{index}/{len(targets)}] {ep_id}: {status}")
        print(f"\n{ready}/{len(targets)} episode(s) can use the cheapest cached-events path.")
        return 0

    total_docs = 0
    skipped: list[str] = []
    for index, ep in enumerate(targets, 1):
        ep_id = ep.get("id")
        if not ep_id:
            skipped.append("<no-id>")
            continue

        raw_payload, note = _generate_raw_payload(
            ep=ep,
            gcs=gcs,
            allow_event_extract=args.allow_event_extract,
        )
        if raw_payload is None:
            print(f"  [{index}/{len(targets)}] {ep_id}: skip ({note})")
            skipped.append(ep_id)
            continue

        docs = build_episode_insight_docs(
            raw_payload=raw_payload,
            episode_id=ep_id,
            podcaster=ep.get("podcast_name") or "",
            podcast_launch_time=_launch_time(ep),
        )
        if not docs:
            print(f"  [{index}/{len(targets)}] {ep_id}: skip (no ticker docs from extractor; {note})")
            skipped.append(ep_id)
            continue

        tickers = ", ".join(sorted(docs))
        if args.dry_run:
            print(f"  [{index}/{len(targets)}] {ep_id}: would write {len(docs)} ({tickers}) [{note}]")
            total_docs += len(docs)
            continue

        written = write_episode_insights(fb.db, episode_id=ep_id, docs=docs)
        if not args.skip_gcs_cache:
            _cache_raw_ticker_insights(fb=fb, gcs=gcs, ep=ep, raw_payload=raw_payload)
        total_docs += written
        print(f"  [{index}/{len(targets)}] {ep_id}: wrote {written} ({tickers}) [{note}]")

    verb = "would write" if args.dry_run else "wrote"
    print(f"\n{verb} {total_docs} ticker insight doc(s); skipped {len(skipped)} episode(s).")
    if skipped:
        print(f"skipped: {skipped[:10]}{'...' if len(skipped) > 10 else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
