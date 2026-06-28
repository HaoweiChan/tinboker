#!/usr/bin/env python3
"""Backfill: fix foreign-ticker TWSE collisions in episode summaries.

Problem: the podcast writer emitted `[Label](#ticker:NNNN)` for foreign (esp.
Japanese) companies using their home-exchange 4-digit codes.  The frontend
resolves any bare numeric code as `.TW`, so e.g. Disco 6146 appeared as TWSE
耕興.  PR #321 fixed the writer prompts; this script cleans up pre-existing
episodes.

Logic:
  - Find `[label](#ticker:NNNN)` where NNNN is 3-6 digits (TW-shaped).
  - Look up the TWSE name for NNNN.  If the label does NOT match the TW
    name or its aliases → collision.  Rewrite to plain `label` and drop
    from related_tickers.
  - Leave alphanumeric tickers (NVDA, ASML, 2330 with matching label) alone.
  - Opportunistically fix "Corpus" → "CoPoS" in summary_content + key_insights.

Usage:
    python scripts/backfill_ticker_collision.py            # dry-run (preview only)
    python scripts/backfill_ticker_collision.py --apply    # actually PATCH Firestore
    python scripts/backfill_ticker_collision.py --podcast my-podcast --apply
    python scripts/backfill_ticker_collision.py --api https://staging-api.tinboker.com --apply

Writes to SHARED prod Firestore (staging API is gated to the same DB).
Back up logic: original summary_content + related_tickers printed before each patch.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from typing import Optional

try:
    import requests
except ImportError:
    print("pip install requests", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------
# Matches [label](#ticker:NNNN) where NNNN is 3–6 digits (possible TWSE code)
_NUMERIC_TICKER_RE = re.compile(r"\[([^\]]+)\]\(#ticker:(\d{3,6})\)")
# Whole-word "Corpus" for the CoPoS text fix
_CORPUS_RE = re.compile(r"\bCorpus\b")


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _get_dev_bypass_token() -> str:
    result = subprocess.run(
        [
            "gcloud", "secrets", "versions", "access", "latest",
            "--secret=DEV_BYPASS_TOKEN",
            "--project=gen-lang-client-0901363254",
        ],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def _mint_jwt(api_base: str, dev_token: str) -> str:
    r = requests.post(
        f"{api_base}/api/auth/dev-token",
        json={"token": dev_token},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["token"]


def _auth_headers(jwt: str) -> dict:
    return {"Authorization": f"Bearer {jwt}"}


def _get_podcasts(api_base: str, jwt: str) -> list[dict]:
    r = requests.get(f"{api_base}/api/podcast", headers=_auth_headers(jwt), timeout=15)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else data.get("podcasts", [])


def _get_episodes_page(
    api_base: str, jwt: str, podcast_name: str, limit: int, offset: int
) -> tuple[list[dict], bool]:
    r = requests.get(
        f"{api_base}/api/podcast/{podcast_name}/episodes",
        params={"limit": limit, "offset": offset, "include_content": "true"},
        headers=_auth_headers(jwt),
        timeout=60,
    )
    r.raise_for_status()
    body = r.json()
    if isinstance(body, list):
        return body, len(body) == limit
    eps = body.get("episodes", [])
    return eps, body.get("hasMore", False) and len(eps) == limit


def _iter_episodes(api_base: str, jwt: str, podcast_name: str) -> list[dict]:
    episodes: list[dict] = []
    limit = 50  # smaller pages — each episode may fetch from GCS server-side
    offset = 0
    while True:
        page, has_more = _get_episodes_page(api_base, jwt, podcast_name, limit, offset)
        episodes.extend(page)
        if not has_more:
            break
        offset += limit
        time.sleep(0.3)
    return episodes


def _batch_tw_translations(api_base: str, jwt: str, tickers: list[str]) -> dict[str, dict]:
    """Returns {ticker: item_dict} for the TW market, in chunks of 50."""
    if not tickers:
        return {}
    out: dict[str, dict] = {}
    for i in range(0, len(tickers), 50):
        chunk = tickers[i : i + 50]
        r = requests.get(
            f"{api_base}/api/stocks/translations/batch",
            params={"tickers": ",".join(chunk), "market": "TW"},
            headers=_auth_headers(jwt),
            timeout=15,
        )
        r.raise_for_status()
        for item in r.json().get("items", []):
            out[item["ticker"]] = item
        time.sleep(0.1)
    return out


def _patch_episode(
    api_base: str, jwt: str, podcast_name: str, episode_id: str, updates: dict
) -> None:
    r = requests.patch(
        f"{api_base}/api/podcast/{podcast_name}/episodes/{episode_id}",
        json=updates,
        headers={**_auth_headers(jwt), "Content-Type": "application/json"},
        timeout=30,
    )
    r.raise_for_status()


# ---------------------------------------------------------------------------
# Collision detection
# ---------------------------------------------------------------------------

def _normalize(s: Optional[str]) -> str:
    # Lowercase + unify 臺/台 + strip dashes (common in KY company names like 世芯-KY)
    return (s or "").strip().lower().replace("臺", "台").replace("-", "").replace("－", "")


def _label_matches_tw(label: str, sym: str, tw_item: Optional[dict]) -> tuple[bool, str]:
    """Return (matches, reason) — matches=True means NOT a collision.

    Checks in order:
    1. Self-referential: label IS the ticker code (e.g. [0050](#ticker:0050))
    2. Exact match against name_zh_tw / name_en / display_name / aliases
    3. Partial/substring match — handles abbreviations (南亞科 ≈ 南亞科技,
       矽品 ≈ 矽品精密) and English label vs Chinese TW name (Samsung ≈ Samsung Electronics)
    4. 2-char CJK first-char heuristic — handles terse abbreviations like
       南電 ≈ 南亞電路板 and 士電 ≈ 士林電機 where the full name is not a substring
    """
    norm_label = _normalize(label)
    # 1. Self-ref: [0050](#ticker:0050) — the label IS the ticker code
    if norm_label == sym.lower():
        return True, "self-ref"
    if not tw_item:
        return False, "no TW translation"
    if not norm_label or len(norm_label) < 2:
        return False, "label too short"
    candidates: dict[str, str] = {}  # normalized → source
    for field in ("name_zh_tw", "name_en", "display_name"):
        v = _normalize(tw_item.get(field) or "")
        if v:
            candidates[v] = field
    for alias in tw_item.get("aliases") or []:
        v = _normalize(alias)
        if v:
            candidates[v] = "alias"
    # 2. Exact match
    if norm_label in candidates:
        return True, f"exact:{candidates[norm_label]}"
    # 3. Partial match: label is substring of a candidate, or vice versa
    for candidate, src in candidates.items():
        if len(candidate) >= 2 and norm_label in candidate:
            return True, f"label-in:{src}"
        if len(norm_label) >= 2 and candidate in norm_label:
            return True, f"candidate-in:{src}"
    # 4. 2-char CJK first-char heuristic: terse abbreviations share the first character
    #    e.g. 南電 (南…) ≈ 南亞電路板, 士電 (士…) ≈ 士林電機
    #    Only applied to 2-char labels to avoid false negatives on 3-char mismatches
    #    like [台達電](#ticker:2330) where 台 also appears in 台積電.
    if len(norm_label) == 2:
        for candidate in candidates:
            if candidate and norm_label[0] == candidate[0]:
                return True, f"2char-abbrev:{norm_label[0]}"
    # 5. 3-char first-2-chars: handles abbreviations where 1 char is dropped/different
    #    e.g. 中美晶 ≈ 中美矽晶 (5483), 方土昶 ≈ 方土霖 (6265 typo)
    if len(norm_label) == 3:
        for candidate in candidates:
            if len(candidate) >= 3 and norm_label[:2] == candidate[:2]:
                return True, f"3char-prefix2:{norm_label[:2]}"
    # 6. 4-char+ prefix: long names that share a 4-char company prefix
    #    e.g. 國泰永續高股息 ≈ 國泰永續ESG高息 (00878)
    if len(norm_label) >= 4:
        for candidate in candidates:
            if len(candidate) >= 4 and norm_label[:4] == candidate[:4]:
                return True, f"4char-prefix:{norm_label[:4]}"
    return False, f"mismatch (tw={list(candidates.keys())[:2]})"


def _fix_summary(text: str, tw_lookup: dict) -> tuple[str, dict[str, str]]:
    """Rewrite colliding numeric tickers to plain text.

    Returns (new_text, {sym: reason}) for every colliding SYM.
    """
    colliding: dict[str, str] = {}

    def _replacer(m: re.Match) -> str:
        label, sym = m.group(1), m.group(2)
        matches, reason = _label_matches_tw(label, sym, tw_lookup.get(sym))
        if matches:
            return m.group(0)  # real TW ticker, keep
        # Collision — flatten to plain label
        colliding[sym] = f"label={label!r} {reason}"
        return label

    return _NUMERIC_TICKER_RE.sub(_replacer, text), colliding


def _fix_corpus(text: str) -> str:
    return _CORPUS_RE.sub("CoPoS", text)


def _build_patch(episode: dict, tw_lookup: dict) -> Optional[dict]:
    """
    Return a partial-update dict for the episode, or None if no change needed.
    Back-up fields are printed by the caller before any PATCH is sent.
    """
    summary = episode.get("summary_content") or ""
    key_insights: list[str] = list(episode.get("key_insights") or [])
    related_tickers: list[str] = list(episode.get("related_tickers") or [])

    # 1. Fix numeric ticker collisions in summary
    new_summary, colliding = _fix_summary(summary, tw_lookup)  # colliding: {sym: reason}

    # 2. CoPoS text fix in summary
    new_summary = _fix_corpus(new_summary)

    # 3. CoPoS text fix in key_insights (List[str])
    new_insights = [_fix_corpus(s) for s in key_insights]

    # 4. Drop colliding syms from related_tickers
    new_tickers = [t for t in related_tickers if t not in colliding]

    changed = (
        new_summary != summary
        or new_insights != key_insights
        or new_tickers != related_tickers
    )
    if not changed:
        return None

    patch: dict = {}
    if new_summary != summary:
        patch["summary_content"] = new_summary
    if new_insights != key_insights:
        patch["key_insights"] = new_insights
    if new_tickers != related_tickers:
        patch["related_tickers"] = new_tickers
    # Internal-only key (stripped before PATCH API call) for preview display
    if colliding:
        patch["_collision_reasons"] = colliding
    return patch


# ---------------------------------------------------------------------------
# Diff display
# ---------------------------------------------------------------------------

def _show_diff(old: str, new: str, label: str, max_lines: int = 6) -> None:
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    shown = 0
    for i, (o, n) in enumerate(zip(old_lines, new_lines)):
        if o != n and shown < max_lines:
            print(f"      {label} L{i+1} OLD: {o[:120]}")
            print(f"      {label} L{i+1} NEW: {n[:120]}")
            shown += 1
    if shown == max_lines:
        print(f"      ... (truncated)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually PATCH Firestore (default: dry-run preview only)",
    )
    parser.add_argument("--podcast", help="Limit to a single podcast name")
    parser.add_argument(
        "--api", default="https://staging-api.tinboker.com",
        help="API base URL (default: staging)",
    )
    args = parser.parse_args()

    print(f"API base : {args.api}")
    print(f"Mode     : {'APPLY (writes to Firestore)' if args.apply else 'DRY-RUN (no writes)'}")
    print()

    print("Fetching DEV_BYPASS_TOKEN from GSM …")
    dev_token = _get_dev_bypass_token()
    print("Minting JWT …")
    jwt = _mint_jwt(args.api, dev_token)
    print("Auth OK.\n")

    print("Fetching podcasts …")
    podcasts = _get_podcasts(args.api, jwt)
    if args.podcast:
        podcasts = [p for p in podcasts if p.get("name") == args.podcast]
    print(f"Podcasts to scan: {[p.get('name', '?') for p in podcasts]}\n")

    total_patched = 0
    total_skipped = 0

    for podcast in podcasts:
        pname = podcast.get("name", "?")
        print(f"{'='*60}")
        print(f"Podcast: {pname}")
        print(f"Fetching episodes (with summary_content) …")
        episodes = _iter_episodes(args.api, jwt, pname)
        print(f"  {len(episodes)} episodes")

        # Collect all numeric ticker codes mentioned across this podcast's episodes
        all_numeric_syms: set[str] = set()
        for ep in episodes:
            for m in _NUMERIC_TICKER_RE.finditer(ep.get("summary_content") or ""):
                all_numeric_syms.add(m.group(2))
        print(f"  Unique numeric ticker codes: {sorted(all_numeric_syms)}")

        # Batch-resolve TW names
        tw_lookup = _batch_tw_translations(args.api, jwt, list(all_numeric_syms))
        print(
            f"  TW translations found: "
            + ", ".join(f"{k}={tw_lookup[k].get('name_zh_tw') or tw_lookup[k].get('name_en')}"
                        for k in sorted(tw_lookup))
        )
        print()

        for ep in episodes:
            ep_id = ep.get("id") or ep.get("episode_id") or "?"
            ep_title = (ep.get("episode_title") or ep.get("title") or "?")[:70]

            patch = _build_patch(ep, tw_lookup)
            if patch is None:
                continue

            # ---- PREVIEW ----
            print(f"  [CHANGE] {ep_id}")
            print(f"    Title : {ep_title}")
            print(f"    Fields: {list(patch.keys())}")

            if "related_tickers" in patch:
                old_rt = ep.get("related_tickers") or []
                print(f"    related_tickers : {old_rt}")
                print(f"                → {patch['related_tickers']}")
                # Show why each ticker was dropped
                dropped = set(old_rt) - set(patch["related_tickers"])
                for sym in dropped:
                    reason = patch.get("_collision_reasons", {}).get(sym, "?")
                    print(f"      dropped {sym}: {reason}")

            if "summary_content" in patch:
                old_sum = ep.get("summary_content") or ""
                _show_diff(old_sum, patch["summary_content"], "summary")

            if "key_insights" in patch:
                old_ki = ep.get("key_insights") or []
                for i, (o, n) in enumerate(zip(old_ki, patch["key_insights"])):
                    if o != n:
                        print(f"    key_insight[{i}] OLD: {o[:120]}")
                        print(f"    key_insight[{i}] NEW: {n[:120]}")

            # ---- BACKUP (printed to stdout for reference) ----
            print(f"    BACKUP summary_content[0:200]: "
                  f"{(ep.get('summary_content') or '')[:200]!r}")
            print(f"    BACKUP related_tickers: {ep.get('related_tickers')!r}")

            if args.apply:
                try:
                    api_patch = {k: v for k, v in patch.items() if not k.startswith("_")}
                    _patch_episode(args.api, jwt, pname, ep_id, api_patch)
                    print(f"    ✓ PATCHED")
                    total_patched += 1
                    time.sleep(0.4)  # gentle rate-limit
                except Exception as e:
                    print(f"    ✗ ERROR: {e}")
                    total_skipped += 1
            else:
                print(f"    (dry-run — skipped)")
                total_skipped += 1

            print()

    print(f"\n{'='*60}")
    print(f"Done.  Patched: {total_patched}  Skipped/dry-run: {total_skipped}")
    if not args.apply:
        print("Re-run with --apply to write changes to Firestore.")


if __name__ == "__main__":
    main()
