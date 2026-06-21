#!/usr/bin/env python3
"""Compile the offline sector/theme universe artifact.

This script is the maintenance boundary for the hybrid update pipeline:

* Static/low-cost tier: merge stable local ticker metadata, FinMind-derived TW
  sector rows, and official ETF issuer CSV holdings that have been downloaded by
  an ops job into local JSON/CSV inputs.
* Curated tier: merge manually reviewed ``curated_themes.json`` entries.
* Runtime tier: write ``shared/data/sector_and_theme_universe.json`` so normal
  podcast ingestion never calls FinMind, ETF issuer endpoints, Tavily, or scraping
  code.

The current implementation compiles from committed local data only. Future jobs
can materialize FinMind/issuer CSV snapshots before invoking this script.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1] / "src" / "shared" / "data"
TICKERS = ROOT / "tickers.json"
CURATED_THEMES = ROOT / "curated_themes.json"
OUT = ROOT / "sector_and_theme_universe.json"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _ticker_meta(symbol: str, tickers: dict[str, Any]) -> dict[str, Any]:
    meta = tickers.get(symbol) or {}
    return {
        "ticker": symbol.upper(),
        "name": meta.get("name", symbol),
        "name_en": meta.get("name_en", symbol),
        "market": meta.get("market", ""),
    }


def _theme_entry(theme: dict[str, Any], tickers: dict[str, Any]) -> dict[str, Any]:
    members = []
    for i, raw in enumerate(theme.get("members") or [], start=1):
        symbol = str(raw.get("ticker") or "").upper()
        if not symbol:
            continue
        member = {**_ticker_meta(symbol, tickers), **raw}
        member["ticker"] = symbol
        member["source"] = raw.get("source") or "curated"
        member["rank"] = int(raw.get("rank") or i)
        members.append(member)
    theme_id = str(theme["theme_id"])
    entry = {
        "exposure_id": f"theme_{theme_id}",
        "exposure_type": "theme",
        "sector_id": None,
        "theme_id": theme_id,
        "display_name": theme.get("display_name", theme_id),
        "aliases": theme.get("aliases") or [theme.get("display_name", theme_id)],
        "members": sorted(members, key=lambda m: int(m.get("rank") or 1_000_000)),
    }
    # Carry through display visuals (icon_id/color_hex) authored by
    # generate_sector_visuals.py so a recompile doesn't drop them.
    for key in ("icon_id", "color_hex"):
        if theme.get(key):
            entry[key] = theme[key]
    return entry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=OUT,
        help="Output path for the compiled runtime artifact",
    )
    args = parser.parse_args(argv)

    tickers = (_load(TICKERS).get("tickers") or {})
    themes = (_load(CURATED_THEMES).get("themes") or [])

    # Keep any existing standard sector/issuer entries. This lets an ops job
    # prebuild richer low-cost sector baselines while this script refreshes the
    # manually curated themes deterministically.
    existing = _load(OUT) if OUT.exists() else {"version": 1, "max_tickers": 10, "exposures": []}
    non_theme_entries = [
        e for e in (existing.get("exposures") or [])
        if e.get("exposure_type") != "theme"
    ]

    compiled = {
        "version": int(existing.get("version") or 1),
        "max_tickers": int(existing.get("max_tickers") or 10),
        "_comment": existing.get("_comment") or "Compiled offline sector/theme universe.",
        "exposures": [*non_theme_entries, *[_theme_entry(t, tickers) for t in themes]],
    }
    args.output.write_text(json.dumps(compiled, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output} with {len(compiled['exposures'])} exposures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
