#!/usr/bin/env python3
"""Backfill ``episodes.spotify_*`` from the Spotify API for the back catalogue.

Why this exists: 186 of the 200 most recently served episodes carry no
``spotify_url``. It is not that the shows are absent from Spotify — 9 of the 10 in
``podcasts_tw.json`` have a ``spotify_show_link``, and the same show has episodes both
with and without metadata. The cause was ``find_episode_by_title`` reading only the
newest ~100 episodes of a show, which on a daily show is about four months. Anything
older simply could not be matched. That is fixed in ``spotify_podcast/parser.py``; this
script applies the now-working lookup to the rows that missed out.

It matters beyond tidiness: episode pages currently serve a re-hosted MP3 of someone
else's podcast, which is what AdSense flagged as replicated content. Linking to the
source instead needs a source link to exist on every episode first.

Writes ONLY the ``spotify_*`` columns, and only where they are currently empty unless
``--overwrite`` is passed. Never touches ``created_time`` — mutating it re-fires
``new_episode`` notifications.

DRY-RUN BY DEFAULT: prints what it WOULD write and changes nothing. Pass ``--apply``.

Requires:
    SPOTIFY_ID / SPOTIFY_SECRET     Spotify client credentials (GSM on the VPS)
    DATABASE_URL (or --postgres-url) Postgres connection

Usage:
    uv run python services/podcast/scripts/backfill_spotify_metadata.py
    uv run python services/podcast/scripts/backfill_spotify_metadata.py --podcast "Gooaye 股癌" --limit 5
    uv run python services/podcast/scripts/backfill_spotify_metadata.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

import sqlalchemy as sa

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVICE_ROOT))

from src.secrets_bootstrap import bootstrap  # noqa: E402

bootstrap()

from src.spotify_podcast.metadata_helper import get_spotify_metadata  # noqa: E402

_POSTGRES_ENV_KEYS = ("DATABASE_URL", "POSTGRES_URL", "PODCAST_DATABASE_URL")

# Column -> key in the metadata dict get_spotify_metadata returns.
_FIELD_MAP = {
    "spotify_id": "spotify_id",
    "spotify_url": "spotify_url",
    "spotify_embed_url": "embed_url",
    "spotify_release_date": "release_date",
    "spotify_description": "description",
    "spotify_duration_ms": "duration_ms",
}


def _postgres_url(cli_value: Optional[str]) -> str:
    if cli_value:
        return cli_value
    for key in _POSTGRES_ENV_KEYS:
        value = os.getenv(key)
        if value:
            return value
    raise RuntimeError("Postgres URL is required; set one of: " + ", ".join(_POSTGRES_ENV_KEYS))


def load_show_links(config_path: Path) -> dict[str, str]:
    """podcast name -> spotify_show_link, for the shows that have one configured."""
    data = json.loads(config_path.read_text(encoding="utf-8"))
    shows = data if isinstance(data, list) else (data.get("podcasts") or data.get("shows") or [])
    out: dict[str, str] = {}
    for show in shows:
        name = show.get("name") or show.get("podcast_name")
        link = show.get("spotify_show_link")
        if name and link:
            out[name] = link
    return out


def select_episodes(conn: sa.Connection, podcast: Optional[str], limit: Optional[int],
                    overwrite: bool) -> list[sa.Row]:
    where = [] if overwrite else ["(spotify_url IS NULL OR spotify_url = '')"]
    params: dict[str, Any] = {}
    if podcast:
        where.append("podcast_name = :podcast")
        params["podcast"] = podcast
    clause = (" WHERE " + " AND ".join(where)) if where else ""
    sql = (
        "SELECT id, podcast_name, episode_title, spotify_url"
        f" FROM episodes{clause} ORDER BY created_time DESC"
    )
    if limit:
        sql += " LIMIT :limit"
        params["limit"] = limit
    return list(conn.execute(sa.text(sql), params))


def build_updates(meta: dict) -> dict[str, Any]:
    """Metadata dict -> column/value pairs, dropping anything Spotify did not give us.

    Nulls are dropped rather than written: a partial Spotify response should never
    blank out a column that already holds a good value.
    """
    updates: dict[str, Any] = {}
    for column, key in _FIELD_MAP.items():
        value = meta.get(key)
        if value not in (None, "", []):
            updates[column] = value
    images = meta.get("images")
    if images:
        updates["spotify_images"] = list(images)
    return updates


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="actually write (default: dry-run)")
    ap.add_argument("--overwrite", action="store_true",
                    help="also refresh episodes that already have a spotify_url")
    ap.add_argument("--podcast", help="restrict to one show")
    ap.add_argument("--limit", type=int, help="process at most N episodes")
    ap.add_argument("--search-depth", type=int, default=400,
                    help="how many episodes back to search per show (default: 400)")
    ap.add_argument("--postgres-url")
    ap.add_argument("--config", default=str(_SERVICE_ROOT / "podcasts_tw.json"))
    args = ap.parse_args()

    show_links = load_show_links(Path(args.config))
    if not show_links:
        print(f"No shows with spotify_show_link in {args.config}", file=sys.stderr)
        return 1

    engine = sa.create_engine(_postgres_url(args.postgres_url))
    with engine.connect() as conn:
        rows = select_episodes(conn, args.podcast, args.limit, args.overwrite)
        print(f"{len(rows)} episode(s) to process "
              f"({'apply' if args.apply else 'DRY RUN — nothing will be written'})")

        matched = skipped_no_link = not_found = 0
        for row in rows:
            link = show_links.get(row.podcast_name)
            if not link:
                skipped_no_link += 1
                continue
            meta = get_spotify_metadata(link, row.episode_title or "", limit=args.search_depth)
            if not meta:
                not_found += 1
                print(f"  ✗ {row.podcast_name} · {(row.episode_title or '')[:44]}")
                continue
            updates = build_updates(meta)
            if not updates:
                not_found += 1
                continue
            matched += 1
            print(f"  ✓ {row.podcast_name} · {(row.episode_title or '')[:44]}"
                  f" → {updates.get('spotify_url')}")
            if args.apply:
                assignments = ", ".join(f"{col} = :{col}" for col in updates)
                conn.execute(
                    sa.text(f"UPDATE episodes SET {assignments} WHERE id = :id"),
                    {**updates, "id": row.id},
                )
        if args.apply:
            conn.commit()

    print(f"\nmatched={matched}  not_found={not_found}  no_show_link={skipped_no_link}")
    if not args.apply:
        print("Dry run — re-run with --apply to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
