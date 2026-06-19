#!/usr/bin/env python3
"""Aggregate unresolved market trends for demand-driven curation.

This is the lightweight background-job boundary for the dynamic/agentic tier.
It reads recent episode JSON exported from Firestore (or a JSON array of raw
``unresolved_market_trends`` rows), counts repeated normalized concepts, and
prints candidates that crossed the threshold. A scheduler can feed those
candidates to a constrained LangChain + Tavily agent that only proposes aliases
and top 3-5 market-leader tickers for manual review into ``curated_themes.json``.

Normal daily podcast ingestion does not run Tavily or any networked research.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from shared.sectors import aggregate_unresolved_trends


def _load_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit("input must be a JSON array")
    rows: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        trends = item.get("unresolved_market_trends")
        if isinstance(trends, list):
            rows.extend(t for t in trends if isinstance(t, dict))
        elif item.get("normalized_text"):
            rows.append(item)
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, help="JSON array of episode docs or unresolved trend rows")
    parser.add_argument("--threshold", type=int, default=3)
    args = parser.parse_args(argv)

    candidates = aggregate_unresolved_trends(_load_rows(args.input), threshold=args.threshold)
    json.dump({"candidates": candidates}, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
