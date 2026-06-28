"""Backfill the ticker registry with the full TW listing from FinMind.

The curated ``tickers.json`` only held a handful of TW names, so any episode that
mentioned a less-common TW stock rendered as a bare number on the social cards. This
pulls FinMind's authoritative ``TaiwanStockInfo`` (id -> Traditional-Chinese name) and
ADDS every missing 4-digit TW symbol. Existing (curated) entries are never overwritten,
so their richer metadata (name_en / sector / aliases) is preserved.

Run:  FINMIND_API_KEY=... uv run --package tinboker-shared python \
        libs/shared/scripts/backfill_tw_tickers.py
(or let it read FINMIND_API_KEY from GCP Secret Manager via the env the caller exports.)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"
DATA_FILE = Path(__file__).resolve().parents[1] / "src" / "shared" / "data" / "tickers.json"


def finmind_tw_info(token: str) -> dict[str, str]:
    """{stock_id: stock_name} for all 4-digit TW listings (common shares + 00xx ETFs)."""
    qs = urllib.parse.urlencode({"dataset": "TaiwanStockInfo", "token": token})
    with urllib.request.urlopen(f"{FINMIND_URL}?{qs}", timeout=90) as resp:  # noqa: S310 (trusted API)
        payload = json.loads(resp.read().decode("utf-8"))
    out: dict[str, str] = {}
    for row in payload.get("data", []):
        sid = str(row.get("stock_id", "")).strip()
        name = str(row.get("stock_name", "")).strip()
        if sid.isdigit() and len(sid) == 4 and name:
            out.setdefault(sid, name)
    return out


def main() -> int:
    token = os.getenv("FINMIND_API_KEY")
    if not token:
        print("FINMIND_API_KEY not set", file=sys.stderr)
        return 1

    doc = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    tickers: dict[str, dict] = doc.setdefault("tickers", {})
    before = len(tickers)

    tw = finmind_tw_info(token)
    print(f"FinMind TaiwanStockInfo: {len(tw)} TW symbols")

    added = 0
    for sid, name in sorted(tw.items()):
        if sid in tickers:
            continue  # never clobber a curated entry
        # 00xx = ETF (元大台灣50 etc.); everything else is a company. type is not shown
        # on the cards, so a coarse split is fine; sector/name_en stay empty (unknown).
        tickers[sid] = {
            "name": name,
            "market": "TW",
            "type": "etf" if sid.startswith("00") else "company",
        }
        added += 1

    # Stable on-disk order so diffs stay readable.
    doc["tickers"] = {k: tickers[k] for k in sorted(tickers)}
    DATA_FILE.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"tickers.json: {before} -> {len(doc['tickers'])} (+{added})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
