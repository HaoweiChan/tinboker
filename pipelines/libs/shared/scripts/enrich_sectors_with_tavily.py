#!/usr/bin/env python3
"""Enrich sector/theme ticker baskets using Tavily discovery + FinMind validation.

MAINTENANCE / COMPILATION TIER ONLY (docs/firestore-contract.md § 2.1.1): the
runtime resolver stays offline reading the compiled artifact; this script (run
manually or on a schedule) expands the *representative* baskets in
``sector_and_theme_universe.json``.

Pipeline:
  * DISCOVER — Tavily searches for each sector's concept stocks (TW).
  * VALIDATE — every candidate 4-digit code MUST exist in FinMind's
    ``TaiwanStockInfo`` table AND be co-mentioned with its canonical FinMind name
    in the search text. The stored name is FinMind's (Traditional Chinese), never
    the LLM/search text — so no hallucinated or mis-named ticker can enter.
  * MERGE — validated members are unioned with the existing curated members
    (curated kept first), deduped by ticker, ranked by mention frequency, capped.

Keys are read from GCP Secret Manager (TAVILY_API_KEY / FINMIND_API_KEY) unless
provided via env. Dry-run by default; pass --apply to write the universe.

Usage:
  uv run python libs/shared/scripts/enrich_sectors_with_tavily.py --only sector_passive_components
  uv run python libs/shared/scripts/enrich_sectors_with_tavily.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

DATA = Path(__file__).resolve().parents[1] / "src" / "shared" / "data" / "sector_and_theme_universe.json"
TAVILY_URL = "https://api.tavily.com/search"
FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
GCP_PROJECT = "gen-lang-client-0901363254"

_CODE_RE = re.compile(r"(?<![\d.])(\d{4})(?![\d.])")


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


def finmind_tw_info(token: str) -> dict[str, str]:
    """{stock_id: stock_name} for all TW common shares — the authoritative validator."""
    r = httpx.get(FINMIND_URL, params={"dataset": "TaiwanStockInfo", "token": token}, timeout=90)
    r.raise_for_status()
    out: dict[str, str] = {}
    for row in r.json().get("data", []):
        sid = str(row.get("stock_id", "")).strip()
        name = str(row.get("stock_name", "")).strip()
        if sid.isdigit() and len(sid) == 4 and name:  # 4-digit = common shares
            out.setdefault(sid, name)
    return out


def tavily_search(api_key: str, query: str, max_results: int = 8) -> dict[str, Any]:
    payload = {
        "query": query, "search_depth": "advanced", "max_results": max_results,
        "include_answer": True, "include_raw_content": True,
    }
    # Newer Tavily prefers Bearer auth; older accepts api_key in the body. Try both.
    try:
        r = httpx.post(TAVILY_URL, json={**payload, "api_key": api_key}, timeout=60)
        if r.status_code == 401:
            r = httpx.post(TAVILY_URL, json=payload,
                           headers={"Authorization": f"Bearer {api_key}"}, timeout=60)
        r.raise_for_status()
        return r.json()
    except Exception as e:  # noqa: BLE001
        print(f"    tavily error: {e}", file=sys.stderr)
        return {}


def _result_text(res: dict[str, Any]) -> str:
    parts = [res.get("answer") or ""]
    for r in res.get("results", []) or []:
        parts.append((r.get("content") or "") + " " + (r.get("raw_content") or ""))
    return " ".join(parts)


def discover_tw(api_key: str, display_name: str, tw_info: dict[str, str], want: int) -> list[tuple[str, str, int]]:
    """Return validated [(ticker, finmind_name, mentions)] ranked by mention count."""
    queries = [
        f"{display_name} 概念股 龍頭股 台股 上市櫃 成分股 有哪些",
        f"{display_name} 類股 individual 個股 台股 代號",
    ]
    counts: Counter = Counter()
    for q in queries:
        text = _result_text(tavily_search(api_key, q))
        if not text:
            continue
        seen_codes = set(_CODE_RE.findall(text))
        for code in seen_codes:
            name = tw_info.get(code)
            # Strong validation: real TW stock AND its FinMind name (>=2-char prefix)
            # co-mentioned in the text — kills year/price false positives.
            if name and (name in text or (len(name) >= 2 and name[:2] in text)):
                counts[code] += text.count(code)
    return [(code, tw_info[code], c) for code, c in counts.most_common(want)]


def _clean_name(name: str) -> str:
    return name.rstrip("*").strip()


def _reverse_lookup(name: str, tw_info: dict[str, str]) -> str | None:
    """Find a TW stock code from a name (exact, then unique substring match)."""
    name = name.strip()
    exact = [c for c, n in tw_info.items() if _clean_name(n) == name]
    if exact:
        return exact[0]
    partial = [c for c, n in tw_info.items() if name and (name in n or _clean_name(n) in name)]
    return partial[0] if len(partial) == 1 else None


def validate_candidates(cands: list[str], tw_info: dict[str, str]) -> list[tuple[str, str]]:
    """Validate WebSearch/manual candidates (4-digit codes or zh names) via FinMind.

    Every result is FinMind-confirmed; names are FinMind's authoritative value, so a
    typo'd or hallucinated candidate is simply dropped.
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw in cands:
        c = str(raw).strip()
        code = c if (c.isdigit() and len(c) == 4 and c in tw_info) else _reverse_lookup(c, tw_info)
        if code and code in tw_info and code not in seen:
            seen.add(code)
            out.append((code, _clean_name(tw_info[code])))
    return out


def enrich(universe: dict[str, Any], tw_info: dict[str, str], tavily_key: str,
           only: str | None, cap: int) -> dict[str, list[tuple[str, str, int]]]:
    proposals: dict[str, list[tuple[str, str, int]]] = {}
    for exp in universe["exposures"]:
        eid = exp.get("exposure_id")
        if only and eid != only:
            continue
        existing = {str(m.get("ticker")) for m in exp.get("members") or []}
        found = discover_tw(tavily_key, exp.get("display_name", eid), tw_info, want=cap * 2)
        # only genuinely NEW, validated TW members
        new = [(c, n, cnt) for c, n, cnt in found if c not in existing][: max(0, cap - len(existing))]
        proposals[eid] = new
        print(f"\n[{eid}] {exp.get('display_name')} — existing {sorted(existing)}")
        if new:
            print("  + " + ", ".join(f"{c} {n}(x{cnt})" for c, n, cnt in new))
        else:
            print("  (no new validated TW members found)")
    return proposals


def apply_proposals(universe: dict[str, Any], proposals: dict[str, list[tuple[str, str, int]]],
                    source: str = "tavily") -> int:
    added = 0
    for exp in universe["exposures"]:
        new = proposals.get(exp.get("exposure_id")) or []
        if not new:
            continue
        members = exp.setdefault("members", [])
        start_rank = max((int(m.get("rank") or 0) for m in members), default=0) + 1
        for i, (code, name, _cnt) in enumerate(new):
            members.append({"ticker": code, "name": name, "market": "TW",
                            "source": source, "rank": start_rank + i})
            added += 1
    return added


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", help="enrich a single exposure_id")
    ap.add_argument("--cap", type=int, default=12, help="target max members per basket")
    ap.add_argument("--candidates", type=Path,
                    help="JSON {exposure_id: [code|name, ...]} (e.g. WebSearch-discovered); "
                         "validated via FinMind instead of Tavily")
    ap.add_argument("--apply", action="store_true", help="write the universe (default: dry-run)")
    args = ap.parse_args()

    finmind_token = _secret("FINMIND_API_KEY")
    print("Fetching FinMind TaiwanStockInfo (validator)...")
    tw_info = finmind_tw_info(finmind_token)
    print(f"  {len(tw_info)} TW common shares loaded.")

    universe = json.loads(DATA.read_text(encoding="utf-8"))
    if args.cap > int(universe.get("max_tickers") or 10):
        universe["max_tickers"] = args.cap  # let the runtime show the fuller basket
    by_id = {e.get("exposure_id"): e for e in universe["exposures"]}
    source = "tavily"

    if args.candidates:
        # FinMind-validate externally-discovered candidates (WebSearch / manual).
        source = "websearch"
        raw = json.loads(args.candidates.read_text(encoding="utf-8"))
        proposals: dict[str, list[tuple[str, str, int]]] = {}
        for eid, cands in raw.items():
            exp = by_id.get(eid)
            if not exp:
                print(f"  ! unknown exposure_id {eid}, skipping")
                continue
            existing = {str(m.get("ticker")) for m in exp.get("members") or []}
            validated = validate_candidates(list(cands), tw_info)
            new = [(c, n, 0) for c, n in validated if c not in existing][: max(0, args.cap - len(existing))]
            proposals[eid] = new
            print(f"\n[{eid}] {exp.get('display_name')} — existing {sorted(existing)}")
            print("  + " + (", ".join(f"{c} {n}" for c, n, _ in new) if new else "(none)"))
    else:
        tavily_key = _secret("TAVILY_API_KEY")
        proposals = enrich(universe, tw_info, tavily_key, args.only, args.cap)

    total_new = sum(len(v) for v in proposals.values())
    print(f"\n=== {total_new} new validated members proposed ===")

    if args.apply and total_new:
        added = apply_proposals(universe, proposals, source=source)
        DATA.write_text(json.dumps(universe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Applied: added {added} members; wrote {DATA}")
    elif not args.apply:
        print("(dry-run — pass --apply to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
