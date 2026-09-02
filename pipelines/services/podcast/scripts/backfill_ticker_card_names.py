#!/usr/bin/env python3
"""Repair the ticker names already baked into stored ``social_cards``.

A card's company name is resolved once, when the card is built, and written into the
row. So fixing ``shared.tickers`` only helps episodes ingested afterwards — every card
already in the database keeps whatever it was given, which for Taiwanese listings was
the bare code: 股癌 EP693 (2026-09-02) shipped with rows reading ``2454``, ``NVDA``,
``AVGO`` and ``2330`` where 聯發科, 輝達, 博通 and 台積電 belonged. 244 of 832 rows
across the last 97 episodes were like that.

Deterministic and cheap: no LLM, no regeneration of anything an LLM wrote. Each row
already carries its symbol (``code`` when it resolved, ``name`` when it did not), so the
repair is to look the symbol up again with the fixed registry and rewrite three derived
fields — ``name``, ``code`` and the ``group`` market label. Every other field, and every
theme card, is left byte-for-byte alone.

It also corrects the cover card's ``title``, which stored the marp deck title — the
LLM's hallucinated show name (股癌 on 13 of 83 covers belonging to six other podcasts).
The renderer always overrode it, so nothing user-facing was wrong; the stored value was
simply a lie waiting for a consumer.

Because it derives everything from the doc's own ``social_cards``, this needs only the
database — no media tree — so unlike the name backfill it can run through a tunnel.

Usage:
    uv run python services/podcast/scripts/backfill_ticker_card_names.py --dry-run
    uv run python services/podcast/scripts/backfill_ticker_card_names.py --dry-run --limit 50
    uv run python services/podcast/scripts/backfill_ticker_card_names.py --apply
    uv run python services/podcast/scripts/backfill_ticker_card_names.py \
        --restore ticker-card-backup.json
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVICE_ROOT))
sys.path.insert(0, str(_SERVICE_ROOT / "src"))

try:
    from src.secrets_bootstrap import bootstrap  # noqa: E402

    bootstrap()
except Exception as _e:  # noqa: BLE001 — local runs may already have the env vars
    print(f"  (secrets_bootstrap skipped: {_e})")

from shared.tickers import prime_tickers  # noqa: E402
from src.podcast.content_builder.nodes.social_cards_builder import (  # noqa: E402
    _MARKET_ZH,
    _ticker_name_code,
)
from src.podcast.exporters.ticker_insights import market_for_ticker  # noqa: E402


def _symbol(entry: dict) -> str:
    """The row's ticker symbol: ``code`` when it resolved, ``name`` when it did not."""
    return str(entry.get("code") or entry.get("name") or "").strip()


def _symbols_in(cards: list) -> set[str]:
    out = set()
    for card in cards:
        if not isinstance(card, dict):
            continue
        for entry in (card.get("rows") or []) + (card.get("items") or []):
            if isinstance(entry, dict) and _symbol(entry):
                out.add(_symbol(entry))
    return out


def repair_cards(cards: list, show_name: str) -> tuple[list, list[str]]:
    """Return ``(new_cards, changes)`` — the repaired deck and a human-readable diff."""
    cards = copy.deepcopy(cards)
    changes: list[str] = []
    for card in cards:
        if not isinstance(card, dict):
            continue

        if card.get("kind") == "cover":
            old = (card.get("title") or "").strip()
            if show_name and old != show_name:
                card["title"] = show_name
                changes.append(f"cover title: {old!r} → {show_name!r}")

        for entry in (card.get("rows") or []) + (card.get("items") or []):
            if not isinstance(entry, dict):
                continue
            symbol = _symbol(entry)
            if not symbol:
                continue
            name, code = _ticker_name_code(symbol)
            group = _MARKET_ZH.get(market_for_ticker(symbol), "其他")
            before = (entry.get("name"), entry.get("code"), entry.get("group"))
            after = (name, code, group if "group" in entry else entry.get("group"))
            if before[:2] == after[:2] and before[2] == after[2]:
                continue
            entry["name"], entry["code"] = name, code
            if "group" in entry:
                entry["group"] = group
            changes.append(
                f"{symbol}: {before[0]!r}/{before[1]!r}/{before[2]!r} → "
                f"{after[0]!r}/{after[1]!r}/{after[2]!r}"
            )
    return cards, changes


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


def _write_cards(conn, episode_id: str, cards: list) -> None:
    from psycopg.types.json import Jsonb
    from src.podcast.exporters.postgres_mirror import SCHEMA
    with conn.cursor() as cur:
        cur.execute(
            f'UPDATE "{SCHEMA}".episodes SET doc = doc || %s WHERE episode_id = %s',
            (Jsonb({"social_cards": cards}), episode_id),
        )
    conn.commit()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="report what would change and write nothing (default)")
    mode.add_argument("--apply", action="store_true", help="write the repaired cards")
    ap.add_argument("--limit", type=int, default=2000, help="max episodes to examine")
    ap.add_argument("--podcast", help="restrict to one show")
    ap.add_argument("--backup-out", metavar="FILE", default="ticker-card-backup.json",
                    help="where --apply saves the previous cards (default: %(default)s)")
    ap.add_argument("--restore", metavar="FILE", help="put back a backup file and exit")
    args = ap.parse_args()

    conn = _connect()
    if conn is None:
        return 2

    from src.podcast.exporters.postgres_mirror import SCHEMA

    if args.restore:
        saved = json.load(open(args.restore, encoding="utf-8"))
        for episode_id, cards in saved.items():
            _write_cards(conn, episode_id, cards)
            print(f"  ↩ restored {episode_id}")
        print(f"\n{len(saved)} episodes restored from {args.restore}")
        return 0

    sql = f'SELECT episode_id, podcast_name, doc FROM "{SCHEMA}".episodes'
    params: list = []
    if args.podcast:
        sql += " WHERE podcast_name = %s"
        params.append(args.podcast)
    sql += " ORDER BY created_time DESC LIMIT %s"
    params.append(args.limit)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    print(f"episodes examined: {len(rows)}\n" + "=" * 78)
    backup: dict[str, list] = {}
    changed = total_fixes = 0

    for episode_id, podcast_name, doc in rows:
        cards = doc.get("social_cards")
        if isinstance(cards, str):
            try:
                cards = json.loads(cards)
            except ValueError:
                continue
        if not isinstance(cards, list) or not cards:
            continue

        # One batch lookup per episode, before anything is resolved.
        prime_tickers(_symbols_in(cards))
        new_cards, diffs = repair_cards(cards, (podcast_name or "").strip())
        if not diffs:
            continue
        changed += 1
        total_fixes += len(diffs)
        print(f"\n{podcast_name} | {episode_id}")
        print(f"  {(doc.get('episode_title') or '')[:70]}")
        for d in diffs:
            print(f"    {d}")
        if args.apply:
            backup[episode_id] = cards
            _write_cards(conn, episode_id, new_cards)
            print("    ✓ written")

    if backup:
        with open(args.backup_out, "w", encoding="utf-8") as f:
            json.dump(backup, f, ensure_ascii=False)
        print(f"\nbackup of the previous cards: {args.backup_out}")
        print(f"  undo with: --restore {args.backup_out}")

    print("\n" + "=" * 78)
    verb = "repaired" if args.apply else "would be repaired"
    print(f"{changed} of {len(rows)} episodes {verb} ({total_fixes} field groups)")
    if not args.apply:
        print("dry run — nothing was written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
