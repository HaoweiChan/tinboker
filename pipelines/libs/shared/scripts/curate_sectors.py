#!/usr/bin/env python3
"""Dev tool for the bootstrap fixture only; production taxonomy lives in Postgres."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / "pipelines/libs/shared/src"))

from shared.curation import (  # noqa: E402
    DEFAULT_BACKEND_SEED,
    DEFAULT_MEMBER_REASONS_JSON,
    DEFAULT_OVERRIDES_JSON,
    DEFAULT_PIPELINE_SEED,
    curate_artifacts,
    emit_seed_py,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--enforce", action="store_true", help="Enable POL-1/POL-3/POL-4/POL-5 checks")
    parser.add_argument(
        "--blank-duplicate-reasons",
        action="store_true",
        help="Blank copied non-parent-child member reason strings in emitted seed artifacts",
    )
    args = parser.parse_args()

    before = {
        DEFAULT_BACKEND_SEED: DEFAULT_BACKEND_SEED.read_text(encoding="utf-8"),
        DEFAULT_PIPELINE_SEED: DEFAULT_PIPELINE_SEED.read_text(encoding="utf-8"),
    }
    result = curate_artifacts(
        enforce=args.enforce,
        blank_duplicate_reasons=args.blank_duplicate_reasons,
    )
    after = {
        DEFAULT_BACKEND_SEED: emit_seed_py(result.seed, result.redirects),
        DEFAULT_PIPELINE_SEED: emit_seed_py(result.seed, result.redirects),
    }

    print(f"overrides: {DEFAULT_OVERRIDES_JSON}")
    print(f"member reasons: {DEFAULT_MEMBER_REASONS_JSON}")
    for entry in result.applied:
        print(f"applied: {entry}")
    for warning in result.warnings:
        print(f"warning: {warning}")
    for path, content in after.items():
        status = "unchanged" if before.get(path) == content else "rewrote"
        print(f"{status}: {path}")
    print(
        "summary: "
        f"{len(result.seed)} sectors, "
        f"{sum(len(s.get('members') or []) for s in result.seed)} members, "
        f"{len(result.redirects)} redirects, "
        f"{sum(1 for s in result.seed for m in s.get('members') or [] if not (m or {}).get('reason'))} empty reasons"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
