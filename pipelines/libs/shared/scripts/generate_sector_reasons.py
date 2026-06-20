#!/usr/bin/env python3
"""Author a one-line zh-TW "why this ticker belongs to the sector" reason per member.

MAINTENANCE / COMPILATION TIER ONLY (docs/firestore-contract.md § 2.1.1): the
runtime resolver stays offline reading the compiled artifact; this script (run
manually or on a schedule, alongside ``enrich_sectors_with_tavily.py``) fills the
``reason`` field on every member of ``sector_and_theme_universe.json``.

The relationships are factual and well-known, so a single Gemini call per exposure
(all of its members at once) produces grounded one-liners cheaply. The model is
asked for STRICT JSON ``{ticker: reason}`` and anything it omits or malforms is
simply skipped — a member with no reason just renders without one.

GOOGLE_API_KEY is read from env or GCP Secret Manager. Dry-run by default.

Usage:
  uv run python libs/shared/scripts/generate_sector_reasons.py --only theme_power_semiconductor
  uv run python libs/shared/scripts/generate_sector_reasons.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

DATA = Path(__file__).resolve().parents[1] / "src" / "shared" / "data" / "sector_and_theme_universe.json"
# Compact mirror the backend serves from (it cannot import the pipelines package).
BACKEND_MIRROR = Path(__file__).resolve().parents[4] / "backend" / "src" / "data" / "sector_reasons.json"
GCP_PROJECT = "gen-lang-client-0901363254"
MODEL = "gemini-2.5-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"


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


_SYSTEM = (
    "你是台股與美股的產業分析師。針對某個產業/題材的成分股，為每一檔股票寫一句"
    "「為什麼這檔屬於這個產業/題材」的繁體中文說明。每句 15~40 字，具體點出該公司在"
    "此題材的角色或產品（例如：晶圓代工、CoWoS 封裝、ABF 載板、矽智財授權…），"
    "不要寫股價、不要投資建議、不要重複公司名稱當開頭、不要贅詞。"
)


def _gemini_reasons(api_key: str, display_name: str, members: list[dict[str, Any]]) -> dict[str, str]:
    roster = "\n".join(
        f'- {m.get("ticker")} {m.get("name") or ""}'.rstrip() for m in members
    )
    prompt = (
        f"產業/題材：{display_name}\n成分股：\n{roster}\n\n"
        "請輸出 JSON 物件，key 為股票代號（與上面完全一致），value 為該句繁體中文說明。"
        "只輸出 JSON，不要其他文字。"
    )
    body = {
        "system_instruction": {"parts": [{"text": _SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"},
    }
    for attempt in range(3):
        try:
            r = httpx.post(GEMINI_URL, params={"key": api_key}, json=body, timeout=90)
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)
            # The model occasionally keys by "<code> <name>" instead of the bare
            # code; take the leading whitespace-delimited token as the ticker so the
            # match is robust either way.
            return {
                str(k).strip().split()[0].upper(): str(v).strip()
                for k, v in parsed.items()
                if v and str(k).strip()
            }
        except Exception as e:  # noqa: BLE001
            print(f"    gemini error (attempt {attempt + 1}): {e}", file=sys.stderr)
            time.sleep(2 ** attempt)
    return {}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", help="generate for a single exposure_id")
    ap.add_argument("--apply", action="store_true", help="write the universe + backend mirror")
    ap.add_argument("--overwrite", action="store_true", help="regenerate reasons that already exist")
    args = ap.parse_args()

    api_key = _secret("GOOGLE_API_KEY")
    universe = json.loads(DATA.read_text(encoding="utf-8"))

    filled = 0
    for exp in universe["exposures"]:
        eid = exp.get("exposure_id")
        if args.only and eid != args.only:
            continue
        members = [m for m in exp.get("members") or [] if isinstance(m, dict)]
        pending = members if args.overwrite else [m for m in members if not m.get("reason")]
        if not pending:
            continue
        print(f"\n[{eid}] {exp.get('display_name')} — {len(pending)} member(s)")
        reasons = _gemini_reasons(api_key, exp.get("display_name", eid), members)
        for m in pending:
            key = str(m.get("ticker") or "").strip().upper()
            reason = reasons.get(key)
            if reason:
                m["reason"] = reason
                filled += 1
                print(f"  {key}: {reason}")
            else:
                print(f"  {key}: (no reason returned)")

    print(f"\n=== {filled} reasons authored ===")

    if args.apply and filled:
        DATA.write_text(json.dumps(universe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote universe: {DATA}")
        _write_backend_mirror(universe)
    elif not args.apply:
        print("(dry-run — pass --apply to write)")
    return 0


def _write_backend_mirror(universe: dict[str, Any]) -> None:
    """Emit the compact ``{exposure_id: {TICKER: reason}}`` map the backend serves."""
    mirror: dict[str, dict[str, str]] = {}
    for exp in universe["exposures"]:
        eid = str(exp.get("exposure_id") or "")
        bucket = {
            str(m.get("ticker") or "").strip().upper(): str(m.get("reason"))
            for m in exp.get("members") or []
            if isinstance(m, dict) and m.get("reason") and m.get("ticker")
        }
        if bucket:
            mirror[eid] = bucket
    BACKEND_MIRROR.write_text(json.dumps(mirror, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote backend mirror: {BACKEND_MIRROR} ({sum(len(v) for v in mirror.values())} reasons)")


if __name__ == "__main__":
    raise SystemExit(main())
