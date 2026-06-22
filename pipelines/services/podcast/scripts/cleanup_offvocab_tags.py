"""One-off cleanup: delete off-vocabulary tag docs from the Firestore `tags` collection.

The LLM writer was only prompt-constrained to the tag vocabulary, so the `tags`
collection accumulated thousands of off-vocabulary junk slugs (hallucinated proper
nouns, fund/ETF names, ticker symbols like ``000660``). The runtime now filters these
out (backend vocabulary gate + the write-boundary enforcement in
``upload_to_firebase.upload_tags_and_tickers``), so this script removes the historical
junk that predates enforcement.

A tag is JUNK iff its normalized slug is not in the canonical vocabulary
(``canonical_tag_slug`` returns None). Deletion is RECURSIVE — the tag parent doc and
its ``episodes`` subcollection.

Dry-run by default (writes nothing). Review the counts + samples, then re-run with
``--commit`` to delete.

Usage:
    uv run python services/podcast/scripts/cleanup_offvocab_tags.py            # dry-run
    uv run python services/podcast/scripts/cleanup_offvocab_tags.py --limit 50 # dry-run, sample
    uv run python services/podcast/scripts/cleanup_offvocab_tags.py --commit   # delete junk
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVICE_ROOT))

from src.podcast.content_builder.tag_vocabulary import canonical_tag_slug  # noqa: E402
from src.service.upload_to_firebase import FirebaseService  # noqa: E402


def classify(db) -> tuple[list[str], list[str]]:
    """Return (kept_vocab_slugs, junk_offvocab_slugs) across the whole tags collection."""
    kept: list[str] = []
    junk: list[str] = []
    for doc in db.collection("tags").stream():
        slug = doc.id
        if canonical_tag_slug(slug) is not None:
            kept.append(slug)
        else:
            junk.append(slug)
    kept.sort()
    junk.sort()
    return kept, junk


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete off-vocabulary tag docs.")
    parser.add_argument("--commit", action="store_true", help="Actually delete (default: dry-run).")
    parser.add_argument("--limit", type=int, default=0, help="Cap deletions this run (0 = no cap).")
    parser.add_argument("--sample", type=int, default=25, help="How many junk/kept slugs to print.")
    args = parser.parse_args()

    svc = FirebaseService()
    db = svc.db
    if db is None:
        print("ERROR: Firestore client unavailable (check GCP creds / FIRESTORE_DATABASE_ID).")
        return 1

    kept, junk = classify(db)
    total = len(kept) + len(junk)
    print(f"tags collection: {total} parent docs — {len(kept)} in-vocabulary, {len(junk)} junk")
    print(f"  keep sample:  {kept[: args.sample]}")
    print(f"  junk sample:  {junk[: args.sample]}")

    targets = junk[: args.limit] if args.limit else junk
    if not args.commit:
        print(f"\nDRY-RUN — would delete {len(targets)} junk tag doc(s) (recursive). "
              f"Re-run with --commit to delete.")
        return 0

    print(f"\nDeleting {len(targets)} junk tag doc(s) recursively…")
    deleted = 0
    for slug in targets:
        try:
            db.recursive_delete(db.collection("tags").document(slug))
            deleted += 1
            if deleted % 200 == 0:
                print(f"  …{deleted}/{len(targets)}")
        except Exception as e:
            print(f"  ⚠ failed to delete {slug!r}: {e}")
    print(f"Done. Deleted {deleted}/{len(targets)} junk tag doc(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
