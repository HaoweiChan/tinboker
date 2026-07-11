#!/usr/bin/env python3
"""Sector-universe data-quality audit — reads the LIVE taxonomy from the admin API.

Productized version of ``docs/fix-plans/assets/audit_sectors.py`` (which read the old
git-committed seed). v3 moved the taxonomy into Postgres (``tag_registry``), so this
reads ``GET /api/admin/taxonomy/snapshot`` instead — same base-URL/admin-token
conventions as ``scripts/fill_sector_reasons.py``.

Computes the same mechanical metrics as the original: member counts, ticker fan-out,
Jaccard/subset overlap between sectors (merge-candidate signal), duplicate-reason
detection, hierarchy checks, and empty reasons/descriptions counts. Overlap and
duplicate-reason checks exempt parent-child (industry/theme ``group``) pairs, because
an industry intentionally rolls up its child theme's members and reasons.

Report-only: this script never writes to the API/DB. Output is a markdown report at
``--out``, which is NEVER a path inside this repo (G6 — nothing taxonomy-shaped is
committed to this public repo). Use ``/tmp`` or any path outside the working tree.

``--judge`` adds one OpenRouter LLM call per sector, asking it to flag members that
fail the sector's own stated inclusion criterion (report-only, same as the mechanical
metrics).

Usage:
  TINBOKER_API_BASE_URL=https://dev-api.tinboker.com \\
  TINBOKER_ADMIN_TOKEN=<admin JWT> \\
  python audit_sector_universe.py --out /tmp/sector_audit.md
  python audit_sector_universe.py --out /tmp/sector_audit.md --judge --only sector_power_semiconductor
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any, Protocol

import requests

REPO_ROOT = Path(__file__).resolve().parents[4]
BASE_URL_ENV = "TINBOKER_API_BASE_URL"
TOKEN_ENV = "TINBOKER_ADMIN_TOKEN"
MODEL_ENV = "SECTOR_REASONS_MODEL"
OPENROUTER_KEY_ENV = "OPENROUTER_API_KEY"
GCP_PROJECT = "gen-lang-client-0901363254"
DEFAULT_MODEL = "deepseek/deepseek-v4-pro"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class JudgeClient(Protocol):
    def judge_sector(self, sector: dict[str, Any]) -> dict[str, Any]:
        ...


# --------------------------------------------------------------------------- fetch


def fetch_taxonomy(session: requests.sessions.Session, base_url: str, token: str) -> list[dict[str, Any]]:
    response = session.get(
        f"{base_url}/api/admin/taxonomy/snapshot",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    sectors = payload.get("sectors")
    if not isinstance(sectors, list):
        raise RuntimeError("taxonomy snapshot response missing sectors list")
    return sectors


# ------------------------------------------------------------------------- metrics


def compute_metrics(sectors: list[dict[str, Any]]) -> dict[str, Any]:
    """Mechanical metrics — pure function of the sectors list, no I/O."""
    by_id = {str(s.get("exposure_id") or ""): s for s in sectors}
    industry_ids = {eid for eid, s in by_id.items() if s.get("exposure_type") == "industry"}

    def members(s: dict[str, Any]) -> list[dict[str, Any]]:
        return [m for m in (s.get("members") or []) if isinstance(m, dict)]

    def sector_tickers(s: dict[str, Any]) -> set[str]:
        return {_ticker(m) for m in members(s) if _ticker(m)}

    # a. member counts
    counts = {eid: len(members(s)) for eid, s in by_id.items()}
    sorted_counts = sorted(counts.values())
    n = len(sorted_counts)
    median = 0.0
    if n:
        median = float(sorted_counts[n // 2] if n % 2 else
                        (sorted_counts[n // 2 - 1] + sorted_counts[n // 2]) / 2)
    small = sorted((eid, c) for eid, c in counts.items() if c < 4)
    large = sorted(((eid, c) for eid, c in counts.items() if c > 40), key=lambda x: -x[1])

    # b. ticker fan-out
    ticker_sectors: dict[str, set[str]] = defaultdict(set)
    ticker_name: dict[str, str] = {}
    for eid, s in by_id.items():
        for m in members(s):
            t = _ticker(m)
            if not t:
                continue
            ticker_sectors[t].add(eid)
            ticker_name.setdefault(t, str(m.get("name") or ""))
    fanout = {t: len(v) for t, v in ticker_sectors.items()}
    fanout_dist = Counter(fanout.values())
    top_fanout = sorted(fanout.items(), key=lambda x: -x[1])[:20]

    # c. overlaps (merge candidates) — parent-child pairs exempted
    id_to_tickers = {eid: sector_tickers(s) for eid, s in by_id.items()}
    jaccard_pairs: list[tuple[str, str, float, int, int, int]] = []
    subset_pairs: list[tuple[str, str, float, int, int]] = []
    for a, b in combinations(sorted(by_id), 2):
        if _is_parent_child(by_id[a], by_id[b]):
            continue
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
        small_set, big_set = (A, B) if len(A) <= len(B) else (B, A)
        small_id, big_id = (a, b) if len(A) <= len(B) else (b, a)
        cov = inter / len(small_set)
        if cov >= 0.9 and len(small_set) < len(big_set):
            subset_pairs.append((small_id, big_id, round(cov, 3), len(small_set), len(big_set)))
    jaccard_pairs.sort(key=lambda x: -x[2])
    subset_pairs.sort(key=lambda x: -x[2])

    # d. reason quality — duplicate detection with parent-child exemption
    empty_reason = 0
    total_members = 0
    reason_to_sectors: dict[tuple[str, str], set[str]] = defaultdict(set)
    for eid, s in by_id.items():
        for m in members(s):
            total_members += 1
            r = _text(m.get("reason"))
            if not r:
                empty_reason += 1
            else:
                t = _ticker(m)
                if t:
                    reason_to_sectors[(t, r)].add(eid)
    reused_pairs: dict[tuple[str, str], set[str]] = {}
    for key, sids in reason_to_sectors.items():
        effective = _drop_exempt_parents(sids, by_id)
        if len(effective) >= 2:
            reused_pairs[key] = effective
    empty_descriptions = sum(1 for s in by_id.values() if not _text(s.get("description")))

    # e. hierarchy checks
    themes_no_group = sorted(
        eid for eid, s in by_id.items() if s.get("exposure_type") == "theme" and not s.get("group")
    )
    bad_group_refs = sorted(
        (eid, str(s.get("group")))
        for eid, s in by_id.items()
        if s.get("exposure_type") == "theme" and s.get("group") and s.get("group") not in industry_ids
    )
    industries_with_group = sorted(
        (eid, str(s.get("group"))) for eid, s in by_id.items()
        if s.get("exposure_type") == "industry" and s.get("group")
    )
    exposure_id_as_member = sorted(
        (eid, t)
        for eid, s in by_id.items()
        for m in members(s)
        for t in [_ticker(m)]
        if t in by_id
    )

    return {
        "sector_count": len(by_id),
        "industry_count": len(industry_ids),
        "theme_count": len(by_id) - len(industry_ids),
        "total_members": total_members,
        "unique_tickers": len(ticker_sectors),
        "counts": {"min": min(sorted_counts) if sorted_counts else 0,
                   "median": median,
                   "max": max(sorted_counts) if sorted_counts else 0,
                   "mean": (sum(sorted_counts) / n) if n else 0.0},
        "small_sectors": small,
        "large_sectors": large,
        "fanout_dist": dict(sorted(fanout_dist.items())),
        "top_fanout": [(t, c, ticker_name.get(t, "")) for t, c in top_fanout],
        "jaccard_pairs": jaccard_pairs,
        "subset_pairs": subset_pairs,
        "empty_reason": empty_reason,
        "empty_descriptions": empty_descriptions,
        "reused_pairs": {k: sorted(v) for k, v in reused_pairs.items()},
        "themes_no_group": themes_no_group,
        "bad_group_refs": bad_group_refs,
        "industries_with_group": industries_with_group,
        "exposure_id_as_member": exposure_id_as_member,
    }


def _is_parent_child(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_id, right_id = left.get("exposure_id"), right.get("exposure_id")
    left_parent, right_parent = left.get("group"), right.get("group")
    return left_parent == right_id or right_parent == left_id


def _drop_exempt_parents(sids: set[str], by_id: dict[str, dict[str, Any]]) -> set[str]:
    """Drop an industry parent from a reused-reason set when a child theme also has it.

    An industry rolling up its child theme's reason is expected (server-side
    parent-child exemption) — the child theme is the source of truth.
    """
    effective = set(sids)
    for sid in list(effective):
        parent = (by_id.get(sid) or {}).get("group")
        if parent and parent in effective:
            effective.discard(parent)
    return effective


# --------------------------------------------------------------------------- judge


class OpenRouterJudge:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        session: requests.sessions.Session | None = None,
        sleep: Any = time.sleep,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.session = session or requests.Session()
        self.sleep = sleep

    def judge_sector(self, sector: dict[str, Any]) -> dict[str, Any]:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _judge_system_prompt()},
                {"role": "user", "content": _judge_user_prompt(sector)},
            ],
            "temperature": 0.0,
            "reasoning": {"enabled": False},
            "response_format": {"type": "json_object"},
        }
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self.session.post(
                    OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                    timeout=90,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                return _parse_judge_json(content)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                print(
                    f"OpenRouter judge error for {sector.get('exposure_id')} "
                    f"(attempt {attempt + 1}/3): {exc}",
                    file=sys.stderr,
                )
                if attempt < 2:
                    self.sleep(2**attempt)
        raise RuntimeError(f"OpenRouter judge failed for {sector.get('exposure_id')}: {last_error}")


def _judge_system_prompt() -> str:
    return (
        "你是台灣股票產業分類的品管審核員。你會收到一個產業/題材的名稱、描述與成分股清單"
        "（含每檔股票的納入理由）。請只依據該題材「自己陳述」的納入標準，找出理由不足以"
        "支撐其屬於此題材的成分股。只輸出嚴格 JSON："
        '{"failing_members": [{"ticker": "2330", "justification": "..."}]}。'
        "若沒有不合格的成分股，回傳 {\"failing_members\": []}。justification 使用繁體中文，一句話。"
    )


def _judge_user_prompt(sector: dict[str, Any]) -> str:
    members = "\n".join(
        f"- {_ticker(m)} {m.get('name') or ''}：{_text(m.get('reason')) or '（無理由）'}"
        for m in (sector.get("members") or [])
        if isinstance(m, dict)
    )
    return (
        f"產業/題材 ID：{sector.get('exposure_id')}\n"
        f"名稱：{sector.get('display_name')}\n"
        f"描述：{sector.get('description') or '（空白）'}\n"
        f"成分股與理由：\n{members}\n\n"
        "只輸出 JSON，不要 markdown，不要額外說明。"
    )


def _parse_judge_json(content: str) -> dict[str, Any]:
    text = str(content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    parsed = json.loads(text)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("failing_members"), list):
        raise ValueError("judge response must be an object with a failing_members list")
    return parsed


# --------------------------------------------------------------------------- report


def render_report(
    metrics: dict[str, Any],
    *,
    source: str,
    judge_results: dict[str, dict[str, Any]] | None = None,
) -> str:
    lines: list[str] = []

    def p(line: str = "") -> None:
        lines.append(line)

    p("# Sector Universe Audit")
    p(f"source: `{source}`")
    p(
        f"sectors: {metrics['sector_count']} "
        f"({metrics['industry_count']} industry, {metrics['theme_count']} theme)"
    )
    p(f"total member entries: {metrics['total_members']}  unique tickers: {metrics['unique_tickers']}")

    p("\n## a. Member counts")
    c = metrics["counts"]
    p(f"min={c['min']} median={c['median']} max={c['max']} mean={c['mean']:.1f}")
    p(f"\nsectors with <4 members ({len(metrics['small_sectors'])}):")
    for eid, cnt in metrics["small_sectors"]:
        p(f"- {cnt:>3}  {eid}")
    p(f"\nsectors with >40 members ({len(metrics['large_sectors'])}):")
    for eid, cnt in metrics["large_sectors"]:
        p(f"- {cnt:>3}  {eid}")

    p("\n## b. Ticker fan-out")
    p("distribution (sectors-per-ticker : #tickers):")
    for k, v in metrics["fanout_dist"].items():
        p(f"- in {k} sectors : {v} tickers")
    p("\ntop 20 tickers by sector count:")
    for t, cnt, name in metrics["top_fanout"]:
        p(f"- {cnt:>3}  {t} {name}")

    p("\n## c. Overlap (merge candidates, parent-child exempted)")
    p(f"pairs with Jaccard >= 0.5 ({len(metrics['jaccard_pairs'])}):")
    for a, b, jac, la, lb, inter in metrics["jaccard_pairs"]:
        p(f"- J={jac} inter={inter}  {a} ({la}) <> {b} ({lb})")
    p(f"\nsubset pairs (>=90% of smaller inside larger) ({len(metrics['subset_pairs'])}):")
    for sub, sup, cov, ls, lb in metrics["subset_pairs"]:
        p(f"- cov={cov}  {sub} ({ls}) ⊆ {sup} ({lb})")

    p("\n## d. Reason quality")
    total = metrics["total_members"] or 1
    p(
        f"empty/missing reasons: {metrics['empty_reason']} / {metrics['total_members']} "
        f"({100 * metrics['empty_reason'] / total:.0f}%)"
    )
    p(f"empty descriptions: {metrics['empty_descriptions']}")
    p(f"\n(ticker,reason) pairs reused across >=2 non-parent-child sectors: {len(metrics['reused_pairs'])}")
    for (ticker, reason), sids in sorted(metrics["reused_pairs"].items(), key=lambda x: -len(x[1]))[:12]:
        p(f"- {ticker} x{len(sids)}: {sids} :: {reason[:60]}")

    p("\n## e. Hierarchy")
    p(f"themes with group=None: {metrics['themes_no_group']}")
    p(f"themes with bad group ref (not an industry id): {metrics['bad_group_refs']}")
    p(f"industries carrying a group: {metrics['industries_with_group']}")
    p(f"exposure_id used as a member ticker: {metrics['exposure_id_as_member']}")

    if judge_results is not None:
        p("\n## f. LLM judge — members failing the sector's own inclusion criterion")
        any_flagged = False
        for eid, result in sorted(judge_results.items()):
            failing = result.get("failing_members") or []
            if not failing:
                continue
            any_flagged = True
            p(f"\n### {eid}")
            for item in failing:
                p(f"- {item.get('ticker')}: {item.get('justification')}")
        if not any_flagged:
            p("\nno flagged members.")

    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- guard


def guard_out_path(out_path: Path, *, repo_root: Path = REPO_ROOT, allow_repo_out: bool = False) -> Path:
    """G6: refuse to write the report inside this public repo's working tree.

    Allowed: anywhere under /tmp (or /private/tmp on macOS), or an explicit
    ``--allow-repo-out`` override (undocumented escape hatch — not for routine use).
    """
    resolved = out_path.resolve()
    if allow_repo_out:
        return resolved
    resolved_str = str(resolved)
    if resolved_str.startswith("/tmp/") or resolved_str.startswith("/private/tmp/") or resolved_str in ("/tmp", "/private/tmp"):
        return resolved
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        return resolved
    raise SystemExit(
        f"Refusing --out inside the repo working tree ({resolved}). "
        "G6: nothing taxonomy-shaped is ever committed to this public repo — "
        "write the report to /tmp or another path outside the repo."
    )


# --------------------------------------------------------------------------- main


def main() -> int:
    args = _parse_args()
    out_path = guard_out_path(Path(args.out), allow_repo_out=args.allow_repo_out)
    base_url = _required_env(BASE_URL_ENV).rstrip("/")
    token = _required_env(TOKEN_ENV)
    session = requests.Session()
    sectors = fetch_taxonomy(session, base_url, token)
    # Metrics always run on the full universe — overlap/fan-out need full-universe
    # context; --only narrows the (expensive) --judge pass only.
    metrics = compute_metrics(sectors)

    judge_results: dict[str, dict[str, Any]] | None = None
    if args.judge:
        judge = OpenRouterJudge(api_key=_secret(OPENROUTER_KEY_ENV), model=os.getenv(MODEL_ENV, DEFAULT_MODEL))
        targets = [s for s in sectors if not args.only or s.get("exposure_id") == args.only]
        judge_results = {str(s.get("exposure_id")): judge.judge_sector(s) for s in targets}

    report = render_report(metrics, source=f"{base_url}/api/admin/taxonomy/snapshot", judge_results=judge_results)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"Wrote report: {out_path}")
    return 0


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
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"Could not read secret {name}: {exc}") from exc


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required env var: {name}")
    return value


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="markdown report output path (never inside this repo)")
    parser.add_argument("--judge", action="store_true", help="also run one LLM judge call per sector")
    parser.add_argument("--only", help="limit --judge to a single exposure_id")
    parser.add_argument("--allow-repo-out", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def _ticker(member: dict[str, Any]) -> str:
    return str(member.get("ticker") or "").strip().upper().split(".")[0]


def _text(value: Any) -> str:
    return str(value or "").strip()


if __name__ == "__main__":
    raise SystemExit(main())
