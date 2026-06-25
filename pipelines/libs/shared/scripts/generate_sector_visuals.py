#!/usr/bin/env python3
"""Assign each sector/theme a display icon + accent color.

MAINTENANCE / COMPILATION TIER ONLY (docs/firestore-contract.md § 2.1.1): the
runtime resolver stays offline reading the compiled artifact; this script stamps
an ``icon_id`` (a lucide-react icon name) and ``color_hex`` (accent color) onto
every exposure so the web UI renders a meaningful, colorful tile instead of the
generic ``hash`` fallback.

Unlike ``generate_sector_reasons.py`` there is no model call: the mapping is a
small, deliberately-curated table (``VISUALS`` below) — icons are a design choice,
not something to guess at ingest time. Adding a new sector/theme is a two-step
edit: add it to ``curated_themes.json`` (themes) / the universe (sectors), then add
one line to ``VISUALS`` and re-run this with ``--apply``.

This writes three places so the value survives a universe recompile:
  * ``sector_and_theme_universe.json`` — every exposure gets icon_id/color_hex (live).
  * ``curated_themes.json``           — theme entries get them too, so
    ``compile_sector_and_theme_universe.py`` carries them through on the next compile.
  * ``backend/src/data/sector_visuals.json`` — the compact mirror the backend serves
    (it cannot import the pipelines package).

Usage:
  uv run python libs/shared/scripts/generate_sector_visuals.py            # dry-run
  uv run python libs/shared/scripts/generate_sector_visuals.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1] / "src" / "shared" / "data"
UNIVERSE = ROOT / "sector_and_theme_universe.json"
CURATED_THEMES = ROOT / "curated_themes.json"
# Compact mirror the backend serves from (it cannot import the pipelines package).
BACKEND_MIRROR = Path(__file__).resolve().parents[4] / "backend" / "src" / "data" / "sector_visuals.json"

# Authored visual identity per exposure_id.
#   icon_id   — a lucide-react icon name (kebab-case); the frontend maps it to a
#               component in SectorIcon.tsx's ICON_REGISTRY. Keep both in sync.
#   color_hex — accent color for the icon chip / page header.
VISUALS: dict[str, dict[str, str]] = {
    # ── Sectors ──────────────────────────────────────────────────────────
    "sector_semiconductor":           {"icon_id": "cpu",           "color_hex": "#3B82F6"},
    "sector_passive_components":      {"icon_id": "circuit-board", "color_hex": "#10B981"},
    "sector_shipping":               {"icon_id": "ship",          "color_hex": "#14B8A6"},
    "sector_heavy_electrical":       {"icon_id": "plug",          "color_hex": "#F97316"},
    "sector_memory":                 {"icon_id": "memory-stick",  "color_hex": "#EF4444"},
    "sector_pcb_substrate":          {"icon_id": "circuit-board", "color_hex": "#A855F7"},
    "sector_networking":             {"icon_id": "network",       "color_hex": "#6366F1"},
    "sector_financials":             {"icon_id": "landmark",      "color_hex": "#F59E0B"},
    "sector_semiconductor_equipment": {"icon_id": "wrench",        "color_hex": "#2DD4BF"},
    "sector_biotech":                {"icon_id": "flask-conical", "color_hex": "#22C55E"},
    "sector_bicycle":                {"icon_id": "bike",          "color_hex": "#84CC16"},
    "sector_steel":                  {"icon_id": "factory",       "color_hex": "#94A3B8"},
    "sector_tourism":                {"icon_id": "plane",         "color_hex": "#F43F5E"},
    # ── Themes ───────────────────────────────────────────────────────────
    "sector_ai_server":               {"icon_id": "server",        "color_hex": "#8B5CF6"},
    "sector_liquid_cooling":          {"icon_id": "droplets",      "color_hex": "#38BDF8"},
    "sector_silicon_photonics":       {"icon_id": "radio",         "color_hex": "#0EA5E9"},
    "sector_power_semiconductor":     {"icon_id": "zap",           "color_hex": "#EAB308"},
    "sector_robotics":                {"icon_id": "bot",           "color_hex": "#06B6D4"},
    "sector_silicon_ip":              {"icon_id": "file-code",     "color_hex": "#EC4899"},
    "sector_advanced_packaging":      {"icon_id": "package",       "color_hex": "#D946EF"},
    "sector_ai_software":             {"icon_id": "brain",         "color_hex": "#7C3AED"},
    "sector_cryptocurrency":          {"icon_id": "bitcoin",       "color_hex": "#F59E0B"},
    "sector_electric_vehicle":        {"icon_id": "car",           "color_hex": "#22C55E"},
    "sector_cybersecurity":           {"icon_id": "shield",        "color_hex": "#EF4444"},
    "sector_defense_aerospace":       {"icon_id": "rocket",        "color_hex": "#64748B"},
    "sector_energy":                  {"icon_id": "flame",         "color_hex": "#F97316"},
    "sector_software_saas":           {"icon_id": "code",          "color_hex": "#3B82F6"},
    "sector_fintech":                 {"icon_id": "credit-card",   "color_hex": "#14B8A6"},
    "sector_precious_metals":         {"icon_id": "gem",           "color_hex": "#CA8A04"},
    "sector_ecommerce":               {"icon_id": "shopping-cart", "color_hex": "#EC4899"},
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="write the universe + curated themes + backend mirror")
    args = ap.parse_args()

    universe = _load(UNIVERSE)
    themes_doc = _load(CURATED_THEMES)

    # Surface any exposure that has no authored visual so it gets a real icon
    # rather than silently riding the frontend's hashed-hue fallback.
    missing = [
        e.get("exposure_id")
        for e in universe.get("exposures") or []
        if e.get("exposure_id") not in VISUALS
    ]
    if missing:
        print(f"WARNING: no VISUALS entry for: {', '.join(missing)}", file=sys.stderr)
        print("  → add them to VISUALS in this script.", file=sys.stderr)

    stamped = 0
    for exp in universe.get("exposures") or []:
        v = VISUALS.get(exp.get("exposure_id"))
        if v:
            exp["icon_id"] = v["icon_id"]
            exp["color_hex"] = v["color_hex"]
            stamped += 1

    for theme in themes_doc.get("themes") or []:
        v = VISUALS.get(f"sector_{theme.get('theme_id')}")
        if v:
            theme["icon_id"] = v["icon_id"]
            theme["color_hex"] = v["color_hex"]

    mirror = {eid: v for eid, v in VISUALS.items()}

    print(f"=== {stamped} exposures stamped, {len(mirror)} visuals in mirror ===")

    if args.apply:
        UNIVERSE.write_text(json.dumps(universe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote universe: {UNIVERSE}")
        CURATED_THEMES.write_text(json.dumps(themes_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote curated themes: {CURATED_THEMES}")
        BACKEND_MIRROR.write_text(json.dumps(mirror, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote backend mirror: {BACKEND_MIRROR}")
    else:
        print("(dry-run — pass --apply to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
