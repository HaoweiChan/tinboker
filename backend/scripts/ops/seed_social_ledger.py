#!/usr/bin/env python3
"""Backfill the ``social_posts`` ledger from what is already live on Threads + Facebook.

One-off, for the SQLite→Postgres ledger move (Aug 2026). The old ledger lived in a
container-local SQLite file with no volume, so it is gone; deploying the new code with an
empty ledger would re-post everything still inside ``threads_max_age_days``. This
reconstructs the ledger from the platforms themselves: every published thread carries a
``/episode/<id>`` link (main text or first reply/comment), which is the episode id.

Run it BEFORE deploying the new backend image — it only writes a table the old code does
not read, so the order is safe:

    python -m scripts.ops.seed_social_ledger --dry-run   # show what it would insert
    python -m scripts.ops.seed_social_ledger

Idempotent: rows that already exist are left alone.

# ponytail: throwaway. Delete once the ledger has a few weeks of its own history.
"""

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.config import settings  # noqa: E402
from src.services import social_ledger  # noqa: E402

EPISODE_RE = re.compile(r"/episode/([A-Za-z0-9_\-]+)")


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _episode_id(*texts: str) -> str | None:
    for t in texts:
        m = EPISODE_RE.search(t or "")
        if m:
            return m.group(1)
    return None


def threads_rows() -> list[tuple[str, str, str]]:
    """(episode_id, media_id, url) for every thread on the brand account."""
    token, base = settings.threads_access_token, settings.threads_api_base.rstrip("/")
    if not token:
        print("  threads: no THREADS_ACCESS_TOKEN — skipped")
        return []
    rows, after = [], None
    while True:
        q = {"fields": "id,text,permalink,timestamp", "limit": 100, "access_token": token}
        if after:
            q["after"] = after
        page = _get(f"{base}/me/threads?{urllib.parse.urlencode(q)}")
        for post in page.get("data", []):
            ep = _episode_id(post.get("text", ""))
            if not ep:
                # The link lives in the first reply on carousel threads.
                conv = _get(f"{base}/{post['id']}/conversation?"
                            + urllib.parse.urlencode({"fields": "text", "access_token": token}))
                ep = _episode_id(*[c.get("text", "") for c in conv.get("data", [])])
            if ep:
                rows.append((ep, post["id"], post.get("permalink", "")))
        after = (page.get("paging") or {}).get("cursors", {}).get("after")
        if not after or not page.get("data"):
            return rows


def facebook_rows() -> list[tuple[str, str, str]]:
    """(episode_id, post_id, url) for every page post."""
    token, page_id = settings.facebook_page_access_token, settings.facebook_page_id
    base = settings.facebook_api_base.rstrip("/")
    if not (token and page_id):
        print("  facebook: no page token/id — skipped")
        return []
    rows, after = [], None
    while True:
        q = {"fields": "id,message,permalink_url", "limit": 100, "access_token": token}
        if after:
            q["after"] = after
        page = _get(f"{base}/{page_id}/feed?{urllib.parse.urlencode(q)}")
        for post in page.get("data", []):
            ep = _episode_id(post.get("message", ""))
            if not ep:
                cmts = _get(f"{base}/{post['id']}/comments?"
                            + urllib.parse.urlencode({"fields": "message", "limit": 50,
                                                      "access_token": token}))
                ep = _episode_id(*[c.get("message", "") for c in cmts.get("data", [])])
            if ep:
                rows.append((ep, post["id"], post.get("permalink_url", "")))
        after = (page.get("paging") or {}).get("cursors", {}).get("after")
        if not after or not page.get("data"):
            return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="list what would be inserted")
    args = ap.parse_args()

    total_new = 0
    for platform, fetch in (("threads", threads_rows), ("facebook", facebook_rows)):
        print(f"{platform}:")
        rows = fetch()
        seen: set[str] = set()
        new = 0
        for episode_id, media_id, url in rows:
            if episode_id in seen:  # a re-post of the same episode — one ledger row
                continue
            seen.add(episode_id)
            if social_ledger.already_posted(platform, episode_id):
                continue
            new += 1
            if args.dry_run:
                print(f"  + {episode_id}  {url}")
                continue
            if social_ledger.claim(platform, episode_id):
                social_ledger.record(platform, episode_id, media_id, url, [])
        print(f"  {len(rows)} posts, {len(seen)} distinct episodes, {new} new ledger rows"
              + (" (dry run)" if args.dry_run else ""))
        total_new += new
    print(f"\n{'would insert' if args.dry_run else 'inserted'} {total_new} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
