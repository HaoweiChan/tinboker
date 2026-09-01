#!/usr/bin/env python3
"""Backfill proper-noun corrections onto already-published episodes.

The live fix (``content_builder.name_normalizer``) only runs at ingest, so every
episode already in the database still carries whatever the ASR misheard — 欣興 stored
as 新興, Warsh as Walsh, 績優生 as 機油生. This applies the same pass to stored rows.

It is the *same* code as the pipeline: :func:`propose_corrections` proposes a
wrong→right map, the equal-length/must-occur vetting rejects rewrites, and
:func:`apply_corrections` rewrites prose while leaving identifiers alone. Nothing
episode-specific is re-derived, so a backfilled episode and a freshly ingested one
end up in the same state.

Two sources, on purpose:
  * **Postgres** (``EPISODE_DATABASE_URL``) — read *and* write. Required for --apply.
  * **the public read API** — dry-run only, so the diff can be reviewed from a laptop
    that cannot reach the database. --apply refuses to run in this mode rather than
    pretending it wrote something.

Only the text fields a reader sees are touched. The transcript
(``sentences_markdown_content``) is deliberately excluded: it is the record of what the
ASR actually heard, and rewriting it would hide the defect from the next investigation.

The model proposes; **a human decides**. A dry run writes a plan file of
``{episode_id: {wrong: right}}`` which you edit — delete the lines you don't want — and
``--from-plan`` applies exactly that, with no second LLM call. This is not ceremony: the
first full dry run proposed ``升息 → 降息`` (a rate call inverted, not a homophone) and
``XBM → HBM`` on an episode *about* XBM and HBF. Both cleared the automated vetting,
because "same length, same script, actually occurs" does not mean "sounds the same".
No rule I can write catches every one of those; reading 20 lines does.

Usage:
    uv run python services/podcast/scripts/backfill_name_normalization.py --dry-run
    uv run python services/podcast/scripts/backfill_name_normalization.py --dry-run --limit 20
    uv run python services/podcast/scripts/backfill_name_normalization.py --dry-run --podcast 財女珍妮
    uv run python services/podcast/scripts/backfill_name_normalization.py \
        --dry-run --plan-out plan.json          # propose, then edit plan.json by hand
    uv run python services/podcast/scripts/backfill_name_normalization.py \
        --from-plan plan.json --apply           # apply exactly what you approved (needs the DB)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVICE_ROOT))
sys.path.insert(0, str(_SERVICE_ROOT / "src"))

try:
    from src.secrets_bootstrap import bootstrap  # noqa: E402

    bootstrap()
except Exception as _e:  # noqa: BLE001 — local runs may already have the env vars
    print(f"  (secrets_bootstrap skipped: {_e})")

from shared.tickers import lookup_ticker, prime_tickers  # noqa: E402
from src.podcast.content_builder.name_normalizer import (  # noqa: E402
    apply_corrections,
    collect_entities,
    propose_corrections,
)

PUBLIC_API = os.getenv("TINBOKER_PLATFORM_API_URL", "https://api.tinboker.com")

# Stored doc fields to correct — the reader-visible ones. Keep in sync with
# name_normalizer._TARGETS (same set, under the storage layer's field names).
DOC_FIELDS = (
    "summary_content",
    "modified_summary_content",
    "events_markdown_content",
    "marp_markdown_content",
    "ticker_marp_markdown_content",
    "ticker_insights_content",
    "key_insights",
    "social_cards",
    "social_thread",
)
# What the model reads to propose the map: the short, name-dense fields.
SAMPLE_FIELDS = ("key_insights", "social_cards", "social_thread", "events_markdown_content")


def _get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "tinboker-backfill"})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 — our own API
        return json.load(resp)


def _episodes_from_api(podcast: str | None, limit: int) -> list[dict]:
    """Recent episodes as full stored docs, newest first (dry-run source).

    Two hops on purpose: the list endpoint omits the large fields (``summary_content``
    comes back empty there), so reporting from it would silently under-count every
    correction that lands in the summary. Each episode is re-fetched by id.
    """
    shows = [podcast] if podcast else [p["name"] for p in _get_json(f"{PUBLIC_API}/api/podcast")]
    index: list[tuple[str, str, int]] = []
    for name in shows:
        q = urllib.parse.urlencode({"limit": min(limit, 200), "sort_by": "created_time",
                                    "order": "desc"})
        url = f"{PUBLIC_API}/api/podcast/{urllib.parse.quote(name)}/episodes?{q}"
        try:
            index += [(name, e["id"], e.get("created_time") or 0) for e in _get_json(url)]
        except Exception as e:  # noqa: BLE001 — one bad show must not stop the survey
            print(f"  ! {name}: {e}")
    index.sort(key=lambda r: r[2], reverse=True)

    out: list[dict] = []
    for name, episode_id, _ in index[:limit]:
        url = (f"{PUBLIC_API}/api/podcast/{urllib.parse.quote(name)}"
               f"/episodes/{urllib.parse.quote(episode_id)}")
        try:
            out.append(_get_json(url))
        except Exception as e:  # noqa: BLE001
            print(f"  ! {episode_id}: {e}")
    return out


def _connect():
    """A Postgres connection, or ``None`` when the database is not reachable."""
    url = os.getenv("EPISODE_DATABASE_URL")
    if not url:
        return None
    try:
        import psycopg
        from shared.db import libpq_url

        return psycopg.connect(libpq_url(url), connect_timeout=8)
    except Exception as e:  # noqa: BLE001 — dry-run falls back to the read API
        print(f"  (Postgres unavailable: {type(e).__name__}: {str(e)[:120]})")
        return None


def _ticker_names(doc: dict) -> list[str]:
    """zh-TW display names for the episode's tickers — the entity anchors."""
    symbols = [str(t) for t in (doc.get("related_tickers") or []) if str(t).strip()]
    if not symbols:
        return []
    prime_tickers(symbols)
    return [info.name for info in (lookup_ticker(s) for s in symbols) if info and info.name]


def _loads(value):
    """Stored JSON columns come back as text from some readers, dicts from others."""
    if isinstance(value, str) and value[:1] in "[{":
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _plan(doc: dict) -> tuple[dict[str, str], dict[str, int]]:
    """Propose a correction map for one episode and count where it would land."""
    fields = {k: _loads(doc.get(k)) for k in DOC_FIELDS}
    sample = "\n\n".join(
        fields[k] if isinstance(fields.get(k), str) else json.dumps(fields.get(k), ensure_ascii=False)
        for k in SAMPLE_FIELDS if fields.get(k)
    )
    if not sample.strip():
        return {}, {}
    entities = collect_entities(
        episode_title=doc.get("episode_title") or "",
        source=doc.get("podcast_name") or "",
        ticker_names=_ticker_names(doc),
    )
    mapping = propose_corrections(
        sample, entities,
        source=doc.get("podcast_name") or "",
        episode_title=doc.get("episode_title") or "",
    )
    if not mapping:
        return {}, {}
    return mapping, _count_hits(doc, mapping)


def _count_hits(doc: dict, mapping: dict[str, str]) -> dict[str, int]:
    """Occurrences of the map's wrong forms, per stored field."""
    hits: dict[str, int] = {}
    for name in DOC_FIELDS:
        value = _loads(doc.get(name))
        if not value:
            continue
        blob = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        n = sum(blob.count(w) for w in mapping)
        if n:
            hits[name] = n
    return hits


def _write_doc(conn, episode_id: str, fields: dict) -> None:
    """Merge ``fields`` into the episode's stored doc (a partial JSONB update)."""
    from psycopg.types.json import Jsonb
    from src.podcast.exporters.postgres_mirror import SCHEMA
    with conn.cursor() as cur:
        cur.execute(
            f'UPDATE "{SCHEMA}".episodes SET doc = doc || %s WHERE episode_id = %s',
            (Jsonb(fields), episode_id),
        )
    conn.commit()


def _restore(conn, path: str) -> int:
    """Put back every value saved in a backup file."""
    saved = json.load(open(path, encoding="utf-8"))
    for episode_id, fields in saved.items():
        _write_doc(conn, episode_id, fields)
        print(f"  ↩ restored {episode_id} ({', '.join(sorted(fields))})")
    print(f"\n{len(saved)} episodes restored from {path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="report what would change and write nothing (default)")
    mode.add_argument("--apply", action="store_true", help="write the corrections (needs Postgres)")
    ap.add_argument("--plan-out", metavar="FILE",
                    help="write the proposed corrections to a JSON file for review")
    ap.add_argument("--from-plan", metavar="FILE",
                    help="use an approved plan file instead of asking the model again")
    ap.add_argument("--backup-out", metavar="FILE", default="name-backfill-backup.json",
                    help="where --apply saves the pre-change values (default: %(default)s)")
    ap.add_argument("--restore", metavar="FILE",
                    help="put back the values saved in a backup file and exit")
    ap.add_argument("--limit", type=int, default=200, help="max episodes to examine")
    ap.add_argument("--podcast", help="restrict to one show")
    ap.add_argument("--episode", help="restrict to one episode id")
    args = ap.parse_args()

    conn = _connect()
    if (args.apply or args.restore) and conn is None:
        print("ERROR: writing needs EPISODE_DATABASE_URL to resolve. Refusing to "
              "pretend: run this where the database is reachable.")
        return 2

    if args.restore:
        return _restore(conn, args.restore)

    if conn is not None:
        from src.podcast.exporters.postgres_mirror import SCHEMA
        with conn.cursor() as cur:
            sql = f'SELECT episode_id, doc FROM "{SCHEMA}".episodes'
            params: list = []
            where = []
            if args.podcast:
                where.append("podcast_name = %s")
                params.append(args.podcast)
            if args.episode:
                where.append("episode_id = %s")
                params.append(args.episode)
            if where:
                sql += " WHERE " + " AND ".join(where)
            sql += " ORDER BY created_time DESC LIMIT %s"
            params.append(args.limit)
            cur.execute(sql, params)
            episodes = [{**(row[1] or {}), "id": row[0]} for row in cur.fetchall()]
        source = "postgres"
    else:
        episodes = _episodes_from_api(args.podcast, args.limit)
        if args.episode:
            episodes = [e for e in episodes if e.get("id") == args.episode]
        source = f"read API ({PUBLIC_API}) — dry-run only"

    print(f"\nsource: {source}")
    print(f"episodes examined: {len(episodes)}\n" + "=" * 78)

    approved: dict[str, dict[str, str]] = {}
    if args.from_plan:
        approved = json.load(open(args.from_plan, encoding="utf-8"))
        print(f"plan: {args.from_plan} ({len(approved)} episodes approved)")

    changed = 0
    total_occurrences = 0
    plan: dict[str, dict[str, str]] = {}
    backup: dict[str, dict] = {}
    for ep in episodes:
        if args.from_plan:
            # Trust the reviewed file verbatim — no second opinion, no drift between
            # what was approved and what lands.
            mapping = approved.get(ep["id"]) or {}
            hits = _count_hits(ep, mapping)
        else:
            mapping, hits = _plan(ep)
        if not mapping:
            continue
        plan[ep["id"]] = mapping
        changed += 1
        total_occurrences += sum(hits.values())
        print(f"\n{ep.get('podcast_name','?')} | {ep.get('id')}")
        print(f"  {(ep.get('episode_title') or '')[:72]}")
        for wrong, right in mapping.items():
            print(f"    {wrong}  →  {right}")
        print("    fields: " + ", ".join(f"{k}×{v}" for k, v in sorted(hits.items())))

        if args.apply:
            touched = [k for k in DOC_FIELDS if ep.get(k)]
            # Snapshot before overwriting. A correction map is cheap to re-derive; the
            # prose it rewrote is not, and this writes to the one database every
            # environment shares.
            backup[ep["id"]] = {k: _loads(ep.get(k)) for k in touched}
            updated = {k: apply_corrections(_loads(ep.get(k)), mapping) for k in touched}
            _write_doc(conn, ep["id"], updated)
            print("    ✓ written")

    if backup:
        with open(args.backup_out, "w", encoding="utf-8") as f:
            json.dump(backup, f, ensure_ascii=False)
        print(f"\nbackup of the previous values: {args.backup_out}")
        print(f"  undo with: --restore {args.backup_out}")

    if args.plan_out:
        with open(args.plan_out, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False, indent=1)
        print(f"\nplan written to {args.plan_out} — delete anything you disagree with, "
              f"then re-run with --from-plan {args.plan_out} --apply")

    print("\n" + "=" * 78)
    verb = "corrected" if args.apply else "would be corrected"
    print(f"{changed} of {len(episodes)} episodes {verb} "
          f"({total_occurrences} occurrences across the stored fields)")
    if not args.apply:
        print("dry run — nothing was written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
