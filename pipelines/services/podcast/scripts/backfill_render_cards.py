#!/usr/bin/env python3
"""Re-render stored social-card PNGs from the (rebuilt) Marp deck.

The PNGs are baked at render time, so every fix upstream of them — resolved ticker
names, the dropped market column, the cover auto-fit, the proper-noun corrections —
only reaches a reader once the images are made again.

Runs on the media host rather than through the admin endpoint on purpose. That endpoint
does the same work, but the backend containers cannot reach the Marp service: it is
published on ``127.0.0.1:5004`` only, so a container resolving ``host.docker.internal``
connects to the docker gateway address where nothing is listening. The pipelines run on
the host, where that port is simply local.

Only episodes that already have rendered images are touched — the render is on-demand
elsewhere in the system, and an episode that never had PNGs does not want them now.

Usage:
    uv run python services/podcast/scripts/backfill_render_cards.py --dry-run
    uv run python services/podcast/scripts/backfill_render_cards.py --apply --limit 20
    uv run python services/podcast/scripts/backfill_render_cards.py --apply
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVICE_ROOT))
sys.path.insert(0, str(_SERVICE_ROOT / "src"))

try:
    from src.secrets_bootstrap import bootstrap  # noqa: E402

    bootstrap()
except Exception as _e:  # noqa: BLE001
    print(f"  (secrets_bootstrap skipped: {_e})")

from src.pipeline.steps.social_cards_render import _render_png  # noqa: E402
from src.service.gcs_storage_service import path_for_media_url  # noqa: E402

MARP_SERVICE_URL = os.environ.get("MARP_SERVICE_URL", "http://127.0.0.1:5004")
_STYLE_RE = re.compile(r"<style>(.*?)</style>", re.DOTALL)


def _deck_and_css(doc: dict) -> tuple[str, str]:
    """The episode's stored deck markdown and its inline theme CSS."""
    url = doc.get("marp_markdown_public_url") or doc.get("marp_markdown_url")
    path = path_for_media_url(url) if url else None
    if not path or not path.is_file():
        return "", ""
    deck = path.read_text(encoding="utf-8").strip()
    style = _STYLE_RE.search(deck)
    return (deck, style.group(1)) if style else (deck, "")


def _connect():
    url = os.getenv("EPISODE_DATABASE_URL")
    if not url:
        print("EPISODE_DATABASE_URL is not set.")
        return None
    import psycopg
    from shared.db import libpq_url

    return psycopg.connect(libpq_url(url), connect_timeout=8)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True)
    mode.add_argument("--apply", action="store_true", help="render and upload")
    ap.add_argument("--limit", type=int, default=5000)
    ap.add_argument("--podcast")
    args = ap.parse_args()

    conn = _connect()
    if conn is None:
        return 2

    from src.podcast.exporters.postgres_mirror import SCHEMA
    from src.service.gcs_storage_service import GCSStorageService

    svc = GCSStorageService()

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

    todo = []
    for episode_id, doc in rows:
        cards = doc.get("social_cards")
        if isinstance(cards, str):
            try:
                cards = json.loads(cards)
            except ValueError:
                continue
        if not isinstance(cards, list) or not cards:
            continue
        # Only episodes that already have images: rendering is on-demand elsewhere.
        if not any(c.get("image_url") for c in cards if isinstance(c, dict)):
            continue
        todo.append((episode_id, doc, cards))

    print(f"episodes with rendered cards: {len(todo)}")
    if not args.apply:
        print("dry run — nothing was rendered.")
        return 0

    from psycopg.types.json import Jsonb

    done = failed = 0
    for n, (episode_id, doc, cards) in enumerate(todo, 1):
        deck, css = _deck_and_css(doc)
        if not deck or not css:
            failed += 1
            print(f"  [{n}/{len(todo)}] {episode_id}: no deck or no inline theme — skipped")
            continue
        try:
            images = _render_png(deck, css, MARP_SERVICE_URL)
        except Exception as e:  # noqa: BLE001 — one bad episode must not stop the run
            failed += 1
            print(f"  [{n}/{len(todo)}] {episode_id}: render failed: {str(e)[:90]}")
            continue
        # Index alignment is load-bearing (card i == slide i == carousel image i).
        if len(images) != len(cards):
            failed += 1
            print(f"  [{n}/{len(todo)}] {episode_id}: {len(images)} PNG vs {len(cards)} cards — skipped")
            continue

        for i, b64 in enumerate(images):
            ok, url = svc.upload_file_from_base64(
                b64, "social_cards", doc.get("podcast_name") or "",
                f"{episode_id}/{i}", "png", skip_existing=False, public=True,
            )
            if ok and url:
                ver = hashlib.md5(b64.encode("utf-8")).hexdigest()[:10]
                cards[i]["image_url"] = f"{url}?v={ver}"
        with conn.cursor() as cur:
            cur.execute(
                f'UPDATE "{SCHEMA}".episodes SET doc = doc || %s WHERE episode_id = %s',
                (Jsonb({"social_cards": cards}), episode_id),
            )
        conn.commit()
        done += 1
        if n % 25 == 0 or n == len(todo):
            print(f"  [{n}/{len(todo)}] {done} rendered, {failed} skipped")

    print(f"\n{done} episodes re-rendered, {failed} skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
