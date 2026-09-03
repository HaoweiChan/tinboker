#!/usr/bin/env python3
"""Rebuild each episode's stored Marp deck from its (repaired) ``social_cards``.

The deck markdown is not derived at read time — it is a file in the media tree, written
once at ingest. So repairing ``social_cards`` in the database changes the episode page's
card data while the deck keeps the *old* table: after the ticker repair, one episode's
stored deck still read ``name">3037<`` and ``grp">台股<`` even though its cards had
resolved 欣興 and dropped the market column.

That matters because the PNG render reads the **stored deck**, not the cards.
Re-rendering without this step reproduces the old table faithfully.

Rebuilding is deterministic — ``build_inline_deck_markdown`` over the stored cards, the
same call ``marp_converter.convert_marp`` makes in the pipeline — so no LLM runs and
nothing an LLM wrote is regenerated. It also picks up anything that lives in the
*renderer* rather than the data: the cover auto-fit tier, for one, which is computed
when the deck is built and so could never appear by re-rendering an old deck.

Writes only the marp media file. The doc's URL fields already point at it.

Usage:
    uv run python services/podcast/scripts/backfill_marp_decks.py --dry-run
    uv run python services/podcast/scripts/backfill_marp_decks.py --dry-run --limit 20
    uv run python services/podcast/scripts/backfill_marp_decks.py --apply
    uv run python services/podcast/scripts/backfill_marp_decks.py --restore marp-backup.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVICE_ROOT))
sys.path.insert(0, str(_SERVICE_ROOT / "src"))

try:
    from src.secrets_bootstrap import bootstrap  # noqa: E402

    bootstrap()
except Exception as _e:  # noqa: BLE001
    print(f"  (secrets_bootstrap skipped: {_e})")

from src.podcast.content_builder.card_deck import build_inline_deck_markdown  # noqa: E402
from src.service.gcs_storage_service import path_for_media_url  # noqa: E402


def date_str(doc: dict) -> str:
    """``YYYY.MM.DD`` for the cover — mirrors ``marp_converter._date_str``."""
    raw = doc.get("released_at_ms") or doc.get("created_time")
    try:
        ms = int(raw)
    except (TypeError, ValueError):
        return ""
    if ms > 10_000_000_000:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y.%m.%d")
    return ""


def rebuild(doc: dict) -> str:
    """The deck this episode's stored cards imply, or ``""`` when there is nothing to build."""
    cards = doc.get("social_cards")
    if isinstance(cards, str):
        try:
            cards = json.loads(cards)
        except ValueError:
            return ""
    if not isinstance(cards, list) or not cards:
        return ""
    # Same guard convert_marp applies: a lone cover with no bullets is not a deck.
    if len(cards) <= 1 and not (cards[0].get("bullets")):
        return ""
    return build_inline_deck_markdown(
        cards,
        show_name=(doc.get("podcast_name") or "").strip(),
        date_str=date_str(doc),
        content_type="podcast",
        size="1080x1080",
    )


def _connect():
    url = os.getenv("EPISODE_DATABASE_URL")
    if not url:
        print("EPISODE_DATABASE_URL is not set.")
        return None
    try:
        import psycopg
        from shared.db import libpq_url

        return psycopg.connect(libpq_url(url), connect_timeout=8)
    except Exception as e:  # noqa: BLE001
        print(f"Postgres unavailable: {type(e).__name__}: {str(e)[:140]}")
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="report what would change and write nothing (default)")
    mode.add_argument("--apply", action="store_true", help="write the rebuilt decks")
    ap.add_argument("--limit", type=int, default=5000)
    ap.add_argument("--podcast")
    ap.add_argument("--backup-out", metavar="FILE", default="marp-backup.json",
                    help="where --apply saves the previous decks (default: %(default)s)")
    ap.add_argument("--restore", metavar="FILE", help="put back a backup file and exit")
    args = ap.parse_args()

    conn = _connect()
    if conn is None:
        return 2

    if args.restore:
        saved = json.load(open(args.restore, encoding="utf-8"))
        for path, text in saved.items():
            Path(path).write_text(text, encoding="utf-8")
        print(f"{len(saved)} decks restored from {args.restore}")
        return 0

    from src.podcast.exporters.postgres_mirror import SCHEMA
    sql = f'SELECT episode_id, doc FROM "{SCHEMA}".episodes'
    params: list = []
    if args.podcast:
        sql += " WHERE podcast_name = %s"
        params.append(args.podcast)
    sql += " ORDER BY created_time DESC LIMIT %s"
    params.append(args.limit)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    print(f"episodes examined: {len(rows)}")
    backup: dict[str, str] = {}
    changed = skipped_no_file = skipped_no_cards = 0

    for episode_id, doc in rows:
        deck = rebuild(doc)
        if not deck:
            skipped_no_cards += 1
            continue
        url = doc.get("marp_markdown_public_url") or doc.get("marp_markdown_url")
        path = path_for_media_url(url) if url else None
        if not path or not path.is_file():
            skipped_no_file += 1
            continue
        before = path.read_text(encoding="utf-8")
        if before == deck:
            continue
        changed += 1
        if args.apply:
            backup[str(path)] = before
            path.write_text(deck, encoding="utf-8")
        else:
            gone = before.count('grp">') - deck.count('grp">')
            print(f"  {episode_id}: {len(before)} → {len(deck)} chars"
                  f"{f', -{gone} market cells' if gone else ''}")

    if backup:
        with open(args.backup_out, "w", encoding="utf-8") as f:
            json.dump(backup, f, ensure_ascii=False)
        print(f"\nbackup of the previous decks: {args.backup_out}")
        print(f"  undo with: --restore {args.backup_out}")

    verb = "rebuilt" if args.apply else "would be rebuilt"
    print(f"\n{changed} decks {verb} "
          f"({skipped_no_cards} without usable cards, {skipped_no_file} without a deck file)")
    if not args.apply:
        print("dry run — nothing was written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
