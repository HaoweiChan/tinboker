#!/usr/bin/env python3
"""One-time backfill: import existing content-store episodes into the Postgres wiki.

Reads every episode from the consolidated content store and calls
``ingest_episode()`` — creating ``episode`` pages and compounding the shared
``entity``/``topic`` pages — WITHOUT re-running download/transcribe/summarize.
Idempotent: ``ingest_episode`` upserts by ``(kind, slug)``, so re-running is safe
and the live ``wiki_ingest`` pipeline step keeps new episodes flowing in after.

The content-store tables (``episodes``, ``ticker_insights``, …) and ``wiki_pages``
both live in the ``tinboker_wiki`` database, so a single ``WIKI_DATABASE_URL`` is
all this needs. (``EPISODE_DATABASE_URL`` points at the legacy ``podcast_db``
mirror — a different database — and is not used here.)

Episode summaries and events markdown are *not* inlined in the content store —
they are fetched over HTTP from each episode's ``summary_url`` /
``events_markdown_url`` (the podcast-api ``/media`` endpoint). Fetches are
best-effort: a missing file is logged and the episode is still ingested.

Usage:
    uv run python services/podcast/scripts/backfill_episodes_to_wiki.py --dry-run
    uv run python services/podcast/scripts/backfill_episodes_to_wiki.py --limit 20
    uv run python services/podcast/scripts/backfill_episodes_to_wiki.py
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import requests

# Make ``shared`` (and the podcast ``src``) importable when run as a plain script.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "libs" / "shared" / "src"))
sys.path.insert(0, str(_SERVICE_ROOT / "src"))

from shared.db import Episode, get_repositories  # noqa: E402
from shared.db.repository import EpisodeRepository, TickerInsightRepository  # noqa: E402
from shared.wiki_builder import get_repository, ingest_episode  # noqa: E402
from shared.wiki_builder.repository import WikiRepository  # noqa: E402

_PAGE_SIZE = 200


def _normalize_pg_url(url: str) -> str:
    """Force the psycopg (v3) driver — the repo's actual Postgres dependency.

    Bare ``postgresql://`` URLs make SQLAlchemy reach for ``psycopg2``, which is
    not installed; ``tinboker-shared`` depends on ``psycopg`` v3.
    """
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def _episode_date(episode: Episode) -> str | None:
    """The episode's release date as YYYY-MM-DD (Spotify date, else created_time)."""
    if episode.spotify_release_date:
        return episode.spotify_release_date
    if episode.created_time:
        return datetime.fromtimestamp(episode.created_time / 1000, tz=timezone.utc).strftime(
            "%Y-%m-%d"
        )
    return None


def _ticker_insights(insights: list) -> dict | None:
    """Shape stored TickerInsight rows into ingest_episode's ticker_insights dict."""
    recs = [
        {
            "ticker": i.ticker,
            "sentiment": i.sentiment_label or "",
            "sentiment_score": "" if i.sentiment_score is None else i.sentiment_score,
            "bluf_thesis": i.bluf_thesis or "",
            "time_horizon": i.time_horizon or "",
        }
        for i in insights
    ]
    return {"ticker_insights": recs} if recs else None


def _fetch_text(url: str, *, session: requests.Session, timeout: int = 20) -> str:
    """GET a ``/media`` markdown file; return its text, or '' on any failure."""
    try:
        response = session.get(url, timeout=timeout)
        response.raise_for_status()
        return response.text
    except Exception as exc:  # noqa: BLE001 — a missing file must not abort the backfill
        print(f"  ⚠ fetch failed ({url}): {exc}")
        return ""


def backfill(
    episodes: EpisodeRepository,
    ticker_insights: TickerInsightRepository,
    wiki: WikiRepository,
    *,
    limit: int | None = None,
    dry_run: bool = False,
    http_get: Callable[[str], str] | None = None,
) -> dict[str, int]:
    """Ingest every content-store episode into the wiki. Returns per-outcome counts.

    ``http_get`` fetches a URL's text (injected so tests run offline); when
    omitted a real :class:`requests.Session` is used. ``dry_run`` skips every
    fetch and write and just counts the episodes.
    """
    if http_get is None:
        session = requests.Session()

        def http_get(url: str) -> str:
            return _fetch_text(url, session=session)

    counts = {
        "seen": 0,
        "ingested": 0,
        "summary_ok": 0,
        "summary_missing": 0,
        "events_ok": 0,
        "title_from_id": 0,
    }
    total = episodes.count()
    offset = 0

    while offset < total:
        page = episodes.list_recent(limit=_PAGE_SIZE, offset=offset)
        if not page:
            break
        for episode in page:
            if limit is not None and counts["seen"] >= limit:
                return counts
            counts["seen"] += 1

            title = episode.episode_title or episode.id
            if not episode.episode_title:
                counts["title_from_id"] += 1

            if dry_run:
                counts["ingested"] += 1
                continue

            summary_text = episode.summary_content or ""
            if not summary_text.strip() and episode.summary_url:
                summary_text = http_get(episode.summary_url)
            counts["summary_ok" if summary_text.strip() else "summary_missing"] += 1

            events_markdown = episode.events_markdown_content or ""
            if not events_markdown.strip() and episode.events_markdown_url:
                events_markdown = http_get(episode.events_markdown_url)
            if events_markdown.strip():
                counts["events_ok"] += 1

            source_urls = {
                key: value
                for key, value in (
                    ("mp3", episode.mp3_url),
                    ("transcript", episode.transcript_url),
                    ("summary", episode.summary_url),
                )
                if value
            }
            ingest_episode(
                podcast_name=episode.podcast_name,
                episode_number=episode.episode_number,
                title=title,
                date=_episode_date(episode),
                tickers=list(episode.related_tickers or []),
                tags=list(episode.tags or []),
                summary_text=summary_text,
                events_markdown=events_markdown or None,
                ticker_insights=_ticker_insights(
                    ticker_insights.list_by_episode(episode.id)
                ),
                source_urls=source_urls or None,
                repository=wiki,
            )
            counts["ingested"] += 1
        offset += _PAGE_SIZE

    return counts


def main() -> int:
    # Bootstrap secrets from GSM when running on the VPS (no-op if env vars already set).
    try:
        from secrets_bootstrap import bootstrap  # type: ignore[import-untyped]

        bootstrap()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report counts, skip all writes")
    parser.add_argument("--limit", type=int, help="process at most N episodes (for testing)")
    parser.add_argument(
        "--wiki-url",
        default=os.environ.get("WIKI_DATABASE_URL"),
        help="tinboker_wiki DB URL (default: $WIKI_DATABASE_URL) — holds both the "
        "content store and wiki_pages",
    )
    args = parser.parse_args()

    if not args.wiki_url:
        print(
            "ERROR: WIKI_DATABASE_URL is not set (use --wiki-url or set env var)",
            file=sys.stderr,
        )
        return 2
    db_url = _normalize_pg_url(args.wiki_url)

    repos = get_repositories(database_url=db_url)
    wiki = get_repository(db_url)

    print(f"backfilling {repos.episodes.count()} content-store episodes into the wiki...")
    counts = backfill(
        repos.episodes,
        repos.ticker_insights,
        wiki,
        limit=args.limit,
        dry_run=args.dry_run,
    )
    prefix = "[dry-run] " if args.dry_run else ""
    print(prefix + "backfill complete: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
