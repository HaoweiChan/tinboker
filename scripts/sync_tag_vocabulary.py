#!/usr/bin/env python3
"""Sync the backend's tag-vocabulary mirror from the pipeline canonical.

STALE / NOT CURRENTLY WIRED UP: this script's CANONICAL/MIRROR paths below
(``tag_vocabulary.json`` on both sides) do not exist on this branch — running it
as-is will crash with FileNotFoundError. The actual live-at-runtime source of
truth today is ``pipelines/libs/shared/src/shared/tag_vocabulary_seed_backup.py``
(``TAG_VOCABULARY_SEED``, a plain Python dict, imported directly by
``pipelines/services/podcast/src/podcast/content_builder/tag_vocabulary.py``), and
its backend mirror is ``backend/src/data/tag_vocabulary_seed.py`` — kept in sync
BY HAND, guarded by
``pipelines/services/podcast/tests/unit/test_tag_vocabulary_sync.py`` /
``backend/tests/unit/test_tag_vocabulary_sync.py``. Edit both ``.py`` seed files
together; do not rely on this script until it is repointed at them.

Original design intent (kept for history — the JSON-based mirroring this script
implements never shipped):

    pipelines/services/podcast/src/podcast/content_builder/tag_vocabulary.json   (CANONICAL, hand-edited)
    backend/src/data/tag_vocabulary.json                                         (GENERATED MIRROR)

The two packages deploy as separate Docker images with disjoint build contexts
(``./backend`` vs ``./pipelines``), so each runtime needs its own physical copy of
the data. To keep them from drifting (which once shipped English tags to prod — see
PRs #161/#162), the backend copy was meant to be GENERATED from the canonical by
this script and guarded by a drift test in both CI suites.

Usage:
    python scripts/sync_tag_vocabulary.py          # write the mirror
    python scripts/sync_tag_vocabulary.py --check   # exit 1 if the mirror is stale (CI/pre-commit)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CANONICAL = REPO_ROOT / "pipelines/services/podcast/src/podcast/content_builder/tag_vocabulary.json"
MIRROR = REPO_ROOT / "backend/src/data/tag_vocabulary.json"

_BANNER = (
    "// GENERATED MIRROR — do not edit by hand.\n"
    "// Source of truth: pipelines/services/podcast/src/podcast/content_builder/tag_vocabulary.json\n"
    "// Regenerate: python scripts/sync_tag_vocabulary.py\n"
)


def render(canonical: dict[str, str]) -> str:
    """Deterministic JSON text for the mirror (stable key order = stable diffs)."""
    # JSON has no comments, so the provenance banner lives under a "_comment" key
    # that loaders ignore. Everything else mirrors the canonical verbatim.
    body = {"_comment": _BANNER.replace("// ", "").strip(), **canonical}
    return json.dumps(body, ensure_ascii=False, indent=2) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify the mirror is up to date; do not write")
    args = parser.parse_args()

    canonical = json.loads(CANONICAL.read_text(encoding="utf-8"))
    expected = render(canonical)

    if args.check:
        actual = MIRROR.read_text(encoding="utf-8") if MIRROR.exists() else ""
        if actual != expected:
            print(
                f"❌ {MIRROR.relative_to(REPO_ROOT)} is out of sync with the canonical "
                f"{CANONICAL.relative_to(REPO_ROOT)}.\n   Run: python scripts/sync_tag_vocabulary.py",
                file=sys.stderr,
            )
            return 1
        print("✅ backend tag-vocabulary mirror is in sync with the pipeline canonical")
        return 0

    MIRROR.parent.mkdir(parents=True, exist_ok=True)
    MIRROR.write_text(expected, encoding="utf-8")
    print(f"✅ wrote {MIRROR.relative_to(REPO_ROOT)} ({len(canonical)} tags) from canonical")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
