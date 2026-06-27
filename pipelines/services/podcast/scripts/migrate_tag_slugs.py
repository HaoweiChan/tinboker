#!/usr/bin/env python3
"""Consolidate fragmented ``tags/{slug}`` docs onto their canonical normalized id.

Spellings like ``ai_supply_chain`` / ``ai_supplychain`` / ``aisupplychain`` (and the
case-variant ``AI`` vs ``ai``) all normalize to one key but were stored as separate
Firestore tag docs — so the topics cloud showed duplicate chips and a tag page only
listed the episodes filed under one spelling. This merges every non-canonical doc's
``episodes`` subcollection into ``tags/{normalize_tag_slug(id)}`` and deletes the
source doc. CJK-only slugs (which normalize to an empty key — they should never have
been doc ids) are deleted outright.

Idempotent. Dry-run by default — pass --commit to write.

    uv run --package tinboker-podcast python scripts/migrate_tag_slugs.py          # preview
    uv run --package tinboker-podcast python scripts/migrate_tag_slugs.py --commit # apply
"""
import argparse
import sys
from collections import defaultdict
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVICE_ROOT))

from google.cloud import firestore  # noqa: E402
from src.podcast.content_builder.tag_vocabulary import normalize_tag_slug  # noqa: E402

_PROJECT = "gen-lang-client-0901363254"
_DB = "graphfolio-db"


def _move_episodes(db, tags, src_id: str, dst_id: str) -> int:
    """Copy ``tags/{src}/episodes/*`` into ``tags/{dst}/episodes`` and delete the source.

    Batched (<=400 ops/batch). Returns the number of episode refs moved.
    """
    dst_eps = tags.document(dst_id).collection("episodes")
    src_eps = tags.document(src_id).collection("episodes")
    moved = 0
    batch = db.batch()
    n = 0
    for ep in src_eps.stream():
        batch.set(dst_eps.document(ep.id), ep.to_dict() or {}, merge=True)
        batch.delete(ep.reference)
        n += 2
        moved += 1
        if n >= 400:
            batch.commit()
            batch = db.batch()
            n = 0
    if n:
        batch.commit()
    return moved


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--commit", action="store_true", help="apply (default: dry-run)")
    args = ap.parse_args()

    db = firestore.Client(project=_PROJECT, database=_DB)
    tags = db.collection("tags")

    groups: dict[str, list[str]] = defaultdict(list)
    for d in tags.list_documents():
        groups[normalize_tag_slug(d.id)].append(d.id)

    cjk_junk = groups.pop("", [])
    merged_docs = moved_eps = 0
    fragmented = 0
    for norm, ids in groups.items():
        sources = [i for i in ids if i != norm]
        if not sources:
            continue
        fragmented += 1
        for src in sources:
            if args.commit:
                moved_eps += _move_episodes(db, tags, src, norm)
                tags.document(norm).set({}, merge=True)  # ensure canonical parent exists
                tags.document(src).delete()
            merged_docs += 1

    for j in cjk_junk:
        if args.commit:
            for ep in tags.document(j).collection("episodes").stream():
                ep.reference.delete()
            tags.document(j).delete()

    print(
        f"groups={len(groups)} fragmented/non-canonical groups={fragmented} "
        f"source docs merged+deleted={merged_docs} "
        f"episode refs moved={moved_eps if args.commit else '(commit to count)'} "
        f"CJK-junk docs deleted={len(cjk_junk)}"
    )
    if not args.commit:
        print("DRY-RUN — pass --commit to write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
