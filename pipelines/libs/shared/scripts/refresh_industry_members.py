#!/usr/bin/env python3
"""Refresh industry (``exposure_type='sector'``) members from FinMind.

Long-term industry membership is authoritative in FinMind:
``TaiwanStockInfo.industry_category`` (which industry) + ``TaiwanStockMarketValue``
(rank by market cap). This refreshes the FinMind-sourced members of the *mapped*
industry sectors in ``sector_and_theme_universe.json`` and non-regressingly syncs
the per-ticker ``sector`` label in ``tickers.json``.

Design (see ``finmind_industry_map.json`` for the why):
* Curated members are always preserved and rank first; FinMind is additive breadth
  + authoritative market-cap ranking, never a wholesale replacement.
* Only clean FinMind categories map. The ``電子工業`` catch-all and finer electronics
  sub-sectors stay curated, so this never downgrades a curated label.
* New FinMind members are added without a ``reason`` so ``generate_sector_reasons.py``
  fills only the new entries (bounded cost).

The merge/sync logic is pure and unit-tested offline; only ``--apply`` and the
``fetch_*`` helpers touch the network. Dry-run by default.

Usage:
  uv run python libs/shared/scripts/refresh_industry_members.py            # dry-run
  uv run python libs/shared/scripts/refresh_industry_members.py --apply
  uv run python libs/shared/scripts/refresh_industry_members.py --start-date 2026-06-20
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx

_SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(_SRC))
from shared.sectors import _member_sort_key  # noqa: E402

DATA = _SRC / "shared" / "data"
UNIVERSE = DATA / "sector_and_theme_universe.json"
TICKERS = DATA / "tickers.json"
MAP_FILE = DATA / "finmind_industry_map.json"
FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
GCP_PROJECT = "gen-lang-client-0901363254"


def _secret(name: str) -> str:
    val = os.getenv(name)
    if val:
        return val
    try:
        return subprocess.run(
            ["gcloud", "secrets", "versions", "access", "latest",
             f"--secret={name}", f"--project={GCP_PROJECT}"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"Could not read secret {name}: {e}")


# ── FinMind fetch (live path only) ──────────────────────────────────────────

def fetch_industry_info(token: str) -> dict[str, dict[str, str]]:
    """``{stock_id: {"name", "category"}}`` for 4-digit TW common shares."""
    r = httpx.get(FINMIND_URL, params={"dataset": "TaiwanStockInfo", "token": token}, timeout=120)
    r.raise_for_status()
    out: dict[str, dict[str, str]] = {}
    for row in r.json().get("data") or []:
        sid = str(row.get("stock_id", "")).strip()
        name = str(row.get("stock_name", "")).strip()
        cat = str(row.get("industry_category", "")).strip()
        if sid.isdigit() and len(sid) == 4 and name and cat:
            out[sid] = {"name": name, "category": cat}
    return out


def fetch_market_values(token: str, start_date: str) -> dict[str, float]:
    """``{stock_id: latest market_value}`` from TaiwanStockMarketValue."""
    r = httpx.get(
        FINMIND_URL,
        params={"dataset": "TaiwanStockMarketValue", "start_date": start_date, "token": token},
        timeout=300,
    )
    r.raise_for_status()
    latest: dict[str, tuple[str, float]] = {}
    for row in r.json().get("data") or []:
        sid = str(row.get("stock_id", "")).strip()
        mv = row.get("market_value")
        date = str(row.get("date", ""))
        if not sid or not mv:
            continue
        if sid not in latest or date > latest[sid][0]:
            latest[sid] = (date, float(mv))
    return {sid: v for sid, (_, v) in latest.items()}


# ── Pure logic (unit-tested offline) ────────────────────────────────────────

def build_finmind_members(
    info: dict[str, dict[str, str]],
    market_values: dict[str, float],
    category_map: dict[str, str],
    cap: int,
) -> dict[str, list[dict[str, Any]]]:
    """``sector_id -> [members]`` ranked by market cap (desc), capped."""
    buckets: dict[str, list[tuple[float, str, str]]] = {}
    for sid, meta in info.items():
        sector_id = category_map.get(meta["category"])
        if not sector_id:
            continue
        buckets.setdefault(sector_id, []).append((market_values.get(sid, 0.0), sid, meta["name"]))
    out: dict[str, list[dict[str, Any]]] = {}
    for sector_id, rows in buckets.items():
        rows.sort(key=lambda r: (-r[0], r[1]))  # market cap desc, then ticker for stability
        out[sector_id] = [
            {"ticker": sid, "name": name, "market": "TW", "source": "finmind", "market_cap_rank": rank}
            for rank, (_, sid, name) in enumerate(rows[:cap], start=1)
        ]
    return out


def merge_sector_members(
    existing: list[dict[str, Any]],
    finmind_members: list[dict[str, Any]],
    cap: int,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Union existing + FinMind, refresh market-cap ranks, sort, cap.

    Returns ``(members, new_tickers)``. Curated members are preserved and (via
    ``_member_sort_key``) rank first; FinMind adds breadth and refreshes
    ``market_cap_rank`` on members it also covers. ``new_tickers`` are FinMind-only
    additions (no ``reason`` yet) — used to bound reason-generation cost.
    """
    by_ticker: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for m in existing:
        t = str(m.get("ticker", "")).upper()
        if not t:
            continue
        by_ticker[t] = dict(m)
        order.append(t)
    new_tickers: list[str] = []
    for m in finmind_members:
        t = str(m["ticker"]).upper()
        if t in by_ticker:
            by_ticker[t]["market_cap_rank"] = m["market_cap_rank"]  # refresh ranking only
        else:
            by_ticker[t] = dict(m)
            order.append(t)
            new_tickers.append(t)
    members = sorted((by_ticker[t] for t in order), key=_member_sort_key)[:cap]
    kept = {str(m.get("ticker", "")).upper() for m in members}
    return members, [t for t in new_tickers if t in kept]


def resolve_ticker_sector_updates(
    tickers: dict[str, Any],
    info: dict[str, dict[str, str]],
    category_map: dict[str, str],
    sector_display: dict[str, str],
) -> dict[str, str]:
    """Non-regressing ``{stock_id: new_sector_label}`` for *existing* TW entries.

    Only writes our canonical zh-TW sector label when FinMind's category maps
    cleanly and differs from the current value. Never adds tickers, never writes
    the raw ``電子工業`` bucket — so a curated fine label is never downgraded.
    """
    updates: dict[str, str] = {}
    for sid, meta in info.items():
        sector_id = category_map.get(meta["category"])
        label = sector_display.get(sector_id) if sector_id else None
        if not label:
            continue
        entry = tickers.get(sid)
        if isinstance(entry, dict) and entry.get("sector") != label:
            updates[sid] = label
    return updates


# ── Orchestration ───────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="write universe + tickers.json (default: dry-run)")
    ap.add_argument("--start-date", default=None, help="market-value lookback start (default: ~10 days ago)")
    args = ap.parse_args()

    universe = json.loads(UNIVERSE.read_text(encoding="utf-8"))
    tickers_doc = json.loads(TICKERS.read_text(encoding="utf-8"))
    tickers = tickers_doc.get("tickers") or {}
    category_map = (json.loads(MAP_FILE.read_text(encoding="utf-8")).get("map")) or {}
    cap = int(universe.get("max_tickers") or 12)

    sector_exposures = [e for e in universe["exposures"] if e.get("exposure_type") == "sector"]
    sector_display = {e["exposure_id"]: e.get("display_name", e["exposure_id"]) for e in sector_exposures}
    mapped_ids = set(category_map.values())

    start_date = args.start_date or _days_ago(10)
    token = _secret("FINMIND_API_KEY")
    print(f"Fetching FinMind TaiwanStockInfo + market values (since {start_date})...")
    info = fetch_industry_info(token)
    market_values = fetch_market_values(token, start_date)
    print(f"  {len(info)} TW common shares, {len(market_values)} with market value.")

    finmind_members = build_finmind_members(info, market_values, category_map, cap)

    total_new = 0
    for exp in sector_exposures:
        eid = exp["exposure_id"]
        if eid not in mapped_ids:
            continue
        before = {str(m.get("ticker", "")).upper() for m in exp.get("members") or []}
        merged, new_tickers = merge_sector_members(exp.get("members") or [], finmind_members.get(eid, []), cap)
        exp["members"] = merged
        total_new += len(new_tickers)
        after = {str(m.get("ticker", "")).upper() for m in merged}
        added, dropped = after - before, before - after
        print(f"[{eid}] {exp.get('display_name')}: {len(merged)} members "
              f"(+{len(added)} -{len(dropped)}, {len(new_tickers)} new → need reasons)")
        if added:
            print(f"    + {sorted(added)}")
        if dropped:
            print(f"    - {sorted(dropped)}")

    unmapped = [e["exposure_id"] for e in sector_exposures if e["exposure_id"] not in mapped_ids]
    print(f"\nLeft curated (no clean FinMind category): {unmapped}")

    updates = resolve_ticker_sector_updates(tickers, info, category_map, sector_display)
    print(f"tickers.json sector-label updates: {len(updates)}")
    for sid, label in list(updates.items())[:20]:
        print(f"    {sid}: {tickers[sid].get('sector')!r} -> {label!r}")

    print(f"\n=== {total_new} new FinMind members across mapped sectors (reason cost ≈ "
          f"#mapped sectors with new members, ≤ {len(mapped_ids)} LLM calls) ===")

    if args.apply:
        UNIVERSE.write_text(json.dumps(universe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for sid, label in updates.items():
            tickers[sid]["sector"] = label  # surgical: only the sector field of existing entries
        TICKERS.write_text(json.dumps(tickers_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {UNIVERSE.name} and {len(updates)} tickers.json updates.")
        print("Next: compile_sector_and_theme_universe.py → generate_sector_visuals.py → generate_sector_reasons.py")
    else:
        print("(dry-run — pass --apply to write)")
    return 0


def _days_ago(n: int) -> str:
    """Date string n days ago. Imported lazily so the module stays import-pure for tests."""
    import datetime
    return (datetime.date.today() - datetime.timedelta(days=n)).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
