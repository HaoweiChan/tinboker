#!/usr/bin/env python3
"""Crawl the official TPEx industry value-chain segments for a ticker universe.

Source: ic.tpex.org.tw (櫃買中心 產業價值鏈資訊平台) — public, free, no token. Each
listed company self-reports the chain>segment positions it occupies, which is the only
free, official Taiwan dataset that carves the market *below* the ~48 statutory industry
categories. We use it as the candidate pool for theme membership: being in a segment is
evidence a company could belong to a theme, never proof that it does — the judgement
step decides that.

Polite by construction: one request at a time, 2 req/s, resumable (an existing output
file is read first and its tickers skipped), so an interrupted run costs nothing.

    python crawl_ictpex_chains.py --universe universe.csv --out chains.jsonl

``universe.csv`` needs a ticker column (``ticker``/``stock_id``/``code``). Output is one
JSON object per line: ``{"ticker": ..., "chains": [[chain, segment], ...]}`` or
``{"ticker": ..., "error": ...}``.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import subprocess
import time

MARKER = "個體公司所屬產業鏈"


def segments(page: str) -> list[tuple[str, str]]:
    """Pull (chain, segment) pairs out of the company page's chain table."""
    body = page.split("所屬產業鏈如下", 1)[1] if "所屬產業鏈如下" in page else ""
    text = html.unescape(re.sub(r"<[^>]+>", "\n", body)).replace("\xa0", " ")
    pairs = re.findall(r"\n\s*([^\n>]+?)\s*\n\s*>\s*([^\n]+)", text)
    return [(a.strip(), b.strip()) for a, b in pairs if a.strip() and b.strip() and "使用條款" not in a]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", required=True, help="CSV with a ticker column")
    ap.add_argument("--out", required=True, help="JSONL output (appended, resumable)")
    ap.add_argument("--delay", type=float, default=0.5)
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.universe, encoding="utf-8")))
    col = next(k for k in rows[0] if k.lower() in ("ticker", "stock_id", "code"))
    done = set()
    if os.path.exists(args.out):
        done = {json.loads(line)["ticker"] for line in open(args.out, encoding="utf-8")}

    with open(args.out, "a", encoding="utf-8") as f:
        for row in rows:
            code = row[col]
            if code in done:
                continue
            try:
                page = subprocess.run(
                    ["curl", "-s", "-m", "20", "-A", "Mozilla/5.0",
                     f"https://ic.tpex.org.tw/company_chain.php?stk_code={code}"],
                    capture_output=True,
                ).stdout.decode("utf-8", "ignore")
                if MARKER not in page:
                    raise RuntimeError("unexpected page")
                rec = {"ticker": code, "chains": segments(page)}
            except Exception as exc:  # one bad page must not end the crawl
                rec = {"ticker": code, "error": str(exc)[:80]}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            f.flush()
            time.sleep(args.delay)


if __name__ == "__main__":
    main()
