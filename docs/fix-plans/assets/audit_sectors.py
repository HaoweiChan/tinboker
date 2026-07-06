#!/usr/bin/env python3
"""Sector-universe data-quality audit for TinBoker's sectors_seed.py.

Loads SECTORS_SEED by exec'ing the seed module (it's a pure Python literal),
then computes mechanical metrics (Part 1 a-f of the audit brief).

Run: python3 audit_sectors.py [path-to-sectors_seed.py]
Prints a plain-text report to stdout. No deps beyond stdlib.
"""
import sys, ast
from collections import Counter, defaultdict
from itertools import combinations

SEED_PATH = sys.argv[1] if len(sys.argv) > 1 else (
    "backend/src/data/sectors_seed.py")

def load_seed(path):
    src = open(path, encoding="utf-8").read()
    # The file is `"""docstring""" \n SECTORS_SEED = [ ... ]`. Grab the literal.
    marker = "SECTORS_SEED = "
    i = src.index(marker) + len(marker)
    literal = src[i:]
    return ast.literal_eval(literal)  # safe: pure data literal

SECTORS = load_seed(SEED_PATH)

INDUSTRY_IDS = {s["exposure_id"] for s in SECTORS
                if s["exposure_type"] == "industry"}

def members(s):
    return s.get("members") or []

def tickers(s):
    return {m["ticker"] for m in members(s)}

# ---------------------------------------------------------------- a. counts
counts = {s["exposure_id"]: len(members(s)) for s in SECTORS}
sorted_counts = sorted(counts.values())
n = len(sorted_counts)
median = (sorted_counts[n//2] if n % 2 else
          (sorted_counts[n//2 - 1] + sorted_counts[n//2]) / 2)
small = sorted([(sid, c) for sid, c in counts.items() if c < 4])
large = sorted([(sid, c) for sid, c in counts.items() if c > 40],
               key=lambda x: -x[1])

# ------------------------------------------------------------- b. fan-out
ticker_sectors = defaultdict(set)   # ticker -> set of exposure_ids
ticker_name = {}
for s in SECTORS:
    for m in members(s):
        ticker_sectors[m["ticker"]].add(s["exposure_id"])
        ticker_name.setdefault(m["ticker"], m.get("name"))
fanout = {t: len(v) for t, v in ticker_sectors.items()}
fanout_dist = Counter(fanout.values())
top_fanout = sorted(fanout.items(), key=lambda x: -x[1])[:20]

# --------------------------------------------------------- c. overlaps
id_to_tickers = {s["exposure_id"]: tickers(s) for s in SECTORS}
jaccard_pairs = []      # (a, b, jac, |A|, |B|, |inter|)
subset_pairs = []       # (sub, sup, coverage, |sub|, |sup|)
ids = [s["exposure_id"] for s in SECTORS]
for a, b in combinations(ids, 2):
    A, B = id_to_tickers[a], id_to_tickers[b]
    if not A or not B:
        continue
    inter = len(A & B)
    if inter == 0:
        continue
    union = len(A | B)
    jac = inter / union
    if jac >= 0.5:
        jaccard_pairs.append((a, b, round(jac, 3), len(A), len(B), inter))
    # subset: >=90% of smaller sector's members inside the larger
    small_set, big_set = (A, B) if len(A) <= len(B) else (B, A)
    small_id, big_id = (a, b) if len(A) <= len(B) else (b, a)
    cov = inter / len(small_set)
    if cov >= 0.9 and len(small_set) < len(big_set):
        subset_pairs.append((small_id, big_id, round(cov, 3),
                             len(small_set), len(big_set)))
jaccard_pairs.sort(key=lambda x: -x[2])
subset_pairs.sort(key=lambda x: -x[2])

# --------------------------------------------------- d. reason quality
empty_reason = 0
total_members = 0
reason_to_sectors = defaultdict(set)   # (ticker, reason) -> set of sector ids
sector_dupreason = Counter()           # sector -> # of members whose reason is reused elsewhere
# First pass: build reason->sectors map for non-empty reasons
for s in SECTORS:
    for m in members(s):
        total_members += 1
        r = (m.get("reason") or "").strip()
        if not r:
            empty_reason += 1
        else:
            reason_to_sectors[(m["ticker"], r)].add(s["exposure_id"])
# reused = same (ticker, reason) appears in >=2 sectors
reused_pairs = {k: v for k, v in reason_to_sectors.items() if len(v) >= 2}
# Also: identical reason STRING reused across different tickers? (looser bug signal)
reason_str_to_pairs = defaultdict(set)
for s in SECTORS:
    for m in members(s):
        r = (m.get("reason") or "").strip()
        if r:
            reason_str_to_pairs[r].add((m["ticker"], s["exposure_id"]))
reused_str = {r: v for r, v in reason_str_to_pairs.items() if len(v) >= 2}
# per-sector count of members whose (ticker,reason) is reused elsewhere
for (tk, r), sids in reused_pairs.items():
    for sid in sids:
        sector_dupreason[sid] += 1

# ------------------------------------------------------- e. hierarchy
themes_no_group = [s["exposure_id"] for s in SECTORS
                   if s["exposure_type"] == "theme" and not s.get("group")]
bad_group_refs = []   # (sector, group) where group not an industry id
industries_with_group = []
for s in SECTORS:
    g = s.get("group")
    if s["exposure_type"] == "theme" and g and g not in INDUSTRY_IDS:
        bad_group_refs.append((s["exposure_id"], g))
    if s["exposure_type"] == "industry" and g:
        industries_with_group.append((s["exposure_id"], g))
# industries appearing as members of themes, or theme-ids used as tickers, etc.
all_exposure_ids = {s["exposure_id"] for s in SECTORS}
exposure_id_as_member = []
for s in SECTORS:
    for m in members(s):
        if m["ticker"] in all_exposure_ids:
            exposure_id_as_member.append((s["exposure_id"], m["ticker"]))

# ----------------------------------------------------------- f. naming
REGION_WORDS = ["日本", "美國", "中國", "韓國", "歐", "全球", "海外", "台灣",
                "日", "美", "陸", "亞洲", "東南亞", "印度"]
region_named = []
for s in SECTORS:
    dn = s["display_name"]
    hits = [w for w in REGION_WORDS if w in dn]
    if hits:
        region_named.append((s["exposure_id"], dn, "/".join(sorted(set(hits)))))
# exposure_id prefix scan
odd_prefix = [s["exposure_id"] for s in SECTORS
              if not s["exposure_id"].startswith("sector_")]

# ================================================================ REPORT
def p(*a): print(*a)

p("="*72)
p("SECTOR UNIVERSE AUDIT — mechanical metrics")
p(f"source: {SEED_PATH}")
p(f"sectors: {len(SECTORS)}  ({len(INDUSTRY_IDS)} industry, "
  f"{len(SECTORS)-len(INDUSTRY_IDS)} theme)")
p(f"total member entries: {total_members}  "
  f"unique tickers: {len(ticker_sectors)}")
p("="*72)

p("\n--- a. MEMBER COUNTS ---")
p(f"min={min(sorted_counts)} median={median} max={max(sorted_counts)} "
  f"mean={sum(sorted_counts)/n:.1f}")
p(f"sectors with <4 members ({len(small)}):")
for sid, c in small:
    p(f"   {c:>3}  {sid}")
p(f"sectors with >40 members ({len(large)}):")
for sid, c in large:
    p(f"   {c:>3}  {sid}")

p("\n--- b. TICKER FAN-OUT ---")
p("distribution (sectors-per-ticker : #tickers):")
for k in sorted(fanout_dist):
    p(f"   in {k:>2} sectors : {fanout_dist[k]:>4} tickers")
p("top 20 tickers by sector count:")
for t, c in top_fanout:
    p(f"   {c:>3}  {t:<6} {ticker_name.get(t,'')}")

p("\n--- c. OVERLAP (merge candidates) ---")
p(f"pairs with Jaccard >= 0.5  ({len(jaccard_pairs)}):")
for a, b, j, la, lb, inter in jaccard_pairs:
    p(f"   J={j:<5} inter={inter:>2}  {a} ({la}) <> {b} ({lb})")
p(f"\nsubset pairs (>=90% of smaller inside larger) ({len(subset_pairs)}):")
for sub, sup, cov, ls, lb in subset_pairs:
    p(f"   cov={cov:<5} {sub} ({ls}) ⊆ {sup} ({lb})")

p("\n--- d. REASON QUALITY ---")
p(f"empty/missing reasons: {empty_reason} / {total_members} "
  f"({100*empty_reason/total_members:.0f}%)")
p(f"(ticker,reason) pairs reused across >=2 sectors: {len(reused_pairs)}")
p(f"identical reason STRINGS appearing >=2 times (any ticker): "
  f"{len(reused_str)}")
n_dupreason_members = sum(len(v) for v in reused_pairs.values())
p(f"member entries carrying a reused (ticker,reason): {n_dupreason_members}")
p("top sectors by # of duplicated-reason members:")
for sid, c in sector_dupreason.most_common(20):
    p(f"   {c:>3}  {sid}")
p("sample reused (ticker,reason) [worst 12 by sector-spread]:")
for (tk, r), sids in sorted(reused_pairs.items(),
                            key=lambda x: -len(x[1]))[:12]:
    p(f"   {tk} {ticker_name.get(tk,'')} x{len(sids)}: "
      f"{sids}  :: {r[:40]}")

p("\n--- e. HIERARCHY ---")
p(f"themes with group=None: {len(themes_no_group)}  {themes_no_group}")
p(f"themes with bad group ref (not an industry id): {bad_group_refs}")
p(f"industries carrying a group: {industries_with_group}")
p(f"exposure_id used as a member ticker: {exposure_id_as_member}")

p("\n--- f. NAMING SCAN ---")
p(f"display_names containing region/market words ({len(region_named)}):")
for sid, dn, hits in region_named:
    p(f"   [{hits}]  {sid}  ::  {dn}")
p(f"exposure_ids not starting with 'sector_': {odd_prefix}")

# machine-readable dump for the audit doc
p("\n" + "="*72)
p("JSON-ISH DUMP FOR DOC TABLES (top offenders)")
p("="*72)
p("TOP_FANOUT=" + repr([(t, c, ticker_name.get(t,'')) for t, c in top_fanout]))
p("SMALL=" + repr(small))
p("LARGE=" + repr(large))
p("JACCARD=" + repr(jaccard_pairs))
p("SUBSET=" + repr(subset_pairs))
p("REGION=" + repr(region_named))

# ---- tiny self-check: metrics are internally consistent -------------
assert sum(counts.values()) == total_members, "member count mismatch"
assert all(fanout[t] == len(ticker_sectors[t]) for t in fanout)
assert empty_reason <= total_members
print("\n[selfcheck OK] counts consistent")
