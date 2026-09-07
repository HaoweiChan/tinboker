#!/usr/bin/env python3
"""Build per-theme candidate pools for a membership review.

A theme's pool is every company sitting in the official TPEx value-chain segments that
its *current* members already occupy — segments holding at least two current members, so
one stray member cannot drag an unrelated segment in (top-1 segment as fallback when no
segment holds two). Current members are excluded from the pool; they are carried through
separately so the reviewer judges old and new membership against the same definition.

The pool is deliberately over-inclusive: it is the ballot, not the result. Whoever
reviews it must be able to state a concrete business link before a candidate becomes a
member, and must re-confirm the existing ones on the same standard.

    python build_theme_pools.py --universe universe.csv --chains chains.jsonl \
        --taxonomy live.jsonl --out pools.json

``taxonomy`` is one JSON object per line per exposure (exposure_id, exposure_type,
display_zh, description, parent_id, aliases, redirect_to, members[]).
"""
from __future__ import annotations

import argparse
import collections
import csv
import json

MAX_CANDIDATES = 150  # a reviewer cannot hold more than this per theme in one pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--universe", required=True)
    ap.add_argument("--chains", required=True)
    ap.add_argument("--taxonomy", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    uni = {r["ticker"]: r for r in csv.DictReader(open(args.universe, encoding="utf-8"))}
    segs_of: dict[str, list[str]] = collections.defaultdict(list)
    members_of: dict[str, set[str]] = collections.defaultdict(set)
    for line in open(args.chains, encoding="utf-8"):
        rec = json.loads(line)
        for chain, segment in rec.get("chains", []):
            key = f"{chain}>{segment}"
            segs_of[rec["ticker"]].append(key)
            members_of[key].add(rec["ticker"])

    live = [json.loads(line) for line in open(args.taxonomy, encoding="utf-8")]
    themes = [t for t in live if t["exposure_type"] == "theme" and not t.get("redirect_to")]

    out = []
    for t in themes:
        current = {m["ticker"]: m for m in (t.get("members") or []) if m.get("market", "TW") == "TW"}
        seg_hits = collections.Counter(k for tk in current for k in segs_of.get(tk, []))
        chosen = [k for k, n in seg_hits.items() if n >= 2] or [k for k, _ in seg_hits.most_common(1)]
        pool = {tk for k in chosen for tk in members_of[k]} - set(current)
        ranked = sorted((tk for tk in pool if tk in uni), key=lambda tk: -float(uni[tk]["adv_e8"] or 0))
        out.append({
            "exposure_id": t["exposure_id"],
            "display_zh": t["display_zh"],
            "description": t.get("description"),
            "parent_id": t.get("parent_id"),
            "aliases": t.get("aliases") or [],
            "segments": [{"segment": k, "current_members_in_it": seg_hits[k], "segment_size": len(members_of[k])}
                         for k in chosen],
            "current": [{"ticker": tk, "name": m["name"], "reason": m.get("reason") or "",
                         "segments": segs_of.get(tk, [])} for tk, m in current.items()],
            "candidates": [{"ticker": tk, "name": uni[tk]["name"], "category": uni[tk]["category"],
                            "segments": segs_of.get(tk, []),
                            "adv_e8": round(float(uni[tk]["adv_e8"] or 0), 2),
                            "mentions": int(uni[tk]["mentions"] or 0)} for tk in ranked[:MAX_CANDIDATES]],
            "pool_truncated": len(ranked) > MAX_CANDIDATES,
        })

    json.dump(out, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    sizes = sorted(len(o["candidates"]) for o in out)
    print(f"themes {len(out)}  candidates {sum(sizes)}  median {sizes[len(sizes)//2]}  "
          f"empty {sizes.count(0)}  truncated {sum(o['pool_truncated'] for o in out)}")


if __name__ == "__main__":
    main()
