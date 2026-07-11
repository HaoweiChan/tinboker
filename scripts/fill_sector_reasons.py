#!/usr/bin/env python3
"""Draft-fill missing sector descriptions and member reasons through the admin API.

This operator helper reads the live taxonomy, asks OpenRouter only for missing text,
posts a bulk draft as ``bot:reasons-fill``, prints review samples, and stops. It never
publishes.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any, Protocol

import requests

BASE_URL_ENV = "TINBOKER_API_BASE_URL"
TOKEN_ENV = "TINBOKER_ADMIN_TOKEN"
MODEL_ENV = "SECTOR_REASONS_MODEL"
OPENROUTER_KEY_ENV = "OPENROUTER_API_KEY"
GCP_PROJECT = "gen-lang-client-0901363254"
DEFAULT_MODEL = "deepseek/deepseek-v4-pro"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
ACTOR = "bot:reasons-fill"


class LLMClient(Protocol):
    def complete_sector(
        self,
        sector: dict[str, Any],
        pending_members: list[dict[str, Any]],
        *,
        needs_description: bool,
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class WorkItem:
    sector: dict[str, Any]
    pending_members: list[dict[str, Any]]
    needs_description: bool


@dataclass(frozen=True)
class FillResult:
    payload: dict[str, Any]
    review_samples: list[dict[str, str]]
    flagged_pairs: list[dict[str, str]]
    reasons_filled: int
    descriptions_filled: int
    skipped_rollup_members: int


class OpenRouterClient:
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

    def complete_sector(
        self,
        sector: dict[str, Any],
        pending_members: list[dict[str, Any]],
        *,
        needs_description: bool,
    ) -> dict[str, Any]:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": _system_prompt()},
                {
                    "role": "user",
                    "content": _user_prompt(
                        sector,
                        pending_members,
                        needs_description=needs_description,
                    ),
                },
            ],
            "temperature": 0.2,
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
                return _parse_llm_json(content)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                print(
                    f"OpenRouter error for {sector.get('exposure_id')} "
                    f"(attempt {attempt + 1}/3): {exc}",
                    file=sys.stderr,
                )
                if attempt < 2:
                    self.sleep(2**attempt)
        raise RuntimeError(f"OpenRouter failed for {sector.get('exposure_id')}: {last_error}")


def main() -> int:
    args = _parse_args()
    base_url = _required_env(BASE_URL_ENV).rstrip("/")
    token = _required_env(TOKEN_ENV)
    api = requests.Session()
    sectors = fetch_taxonomy(api, base_url, token)
    work, skipped = detect_work(sectors, only=args.only)
    if not work:
        print("No missing sector descriptions or member reasons found.")
        return 0

    llm = OpenRouterClient(
        api_key=_secret(OPENROUTER_KEY_ENV),
        model=os.getenv(MODEL_ENV, DEFAULT_MODEL),
    )
    result = build_fill_payload(sectors, work, skipped_rollup_members=skipped, llm=llm)
    if not result.payload["sectors"]:
        print("No draftable changes were generated.")
        return 0

    draft = post_bulk_draft(api, base_url, token, result.payload)
    _print_report(draft, result, base_url)
    return 0


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


def detect_work(
    sectors: list[dict[str, Any]],
    *,
    only: str | None = None,
) -> tuple[list[WorkItem], int]:
    by_id = {str(s.get("exposure_id") or ""): s for s in sectors}
    children_by_parent: dict[str, list[dict[str, Any]]] = {}
    for sector in sectors:
        parent = str(sector.get("group") or sector.get("parent_id") or "")
        if parent:
            children_by_parent.setdefault(parent, []).append(sector)

    work: list[WorkItem] = []
    skipped_rollups = 0
    for sector in sectors:
        eid = str(sector.get("exposure_id") or "")
        if only and eid != only:
            continue
        child_tickers = _child_tickers(children_by_parent.get(eid, []))
        pending: list[dict[str, Any]] = []
        for member in [m for m in sector.get("members") or [] if isinstance(m, dict)]:
            if _text(member.get("reason")):
                continue
            ticker = _ticker(member)
            is_rollup_reuse = (
                sector.get("exposure_type") == "industry"
                and ticker
                and ticker in child_tickers
            )
            if is_rollup_reuse:
                skipped_rollups += 1
                continue
            pending.append(member)
        needs_description = not _text(sector.get("description"))
        if pending or needs_description:
            work.append(WorkItem(sector=by_id[eid], pending_members=pending, needs_description=needs_description))
    return work, skipped_rollups


def build_fill_payload(
    sectors: list[dict[str, Any]],
    work: list[WorkItem],
    *,
    skipped_rollup_members: int,
    llm: LLMClient,
) -> FillResult:
    by_id = {str(s.get("exposure_id") or ""): s for s in sectors}
    changes: dict[str, dict[str, Any]] = {}
    generated: dict[str, dict[str, str]] = {}

    for item in work:
        _apply_llm_result(
            item,
            llm.complete_sector(item.sector, item.pending_members, needs_description=item.needs_description),
            changes,
            generated,
        )

    duplicate_pairs = _duplicate_reason_pairs(sectors, changes)
    reasked: set[str] = set()
    for pair in duplicate_pairs:
        eid = pair["right_exposure_id"]
        if eid in reasked:
            continue
        item = next((w for w in work if str(w.sector.get("exposure_id")) == eid), None)
        if item is None:
            continue
        reasked.add(eid)
        _apply_llm_result(
            item,
            llm.complete_sector(item.sector, item.pending_members, needs_description=item.needs_description),
            changes,
            generated,
        )

    flagged_pairs = _duplicate_reason_pairs(sectors, changes)
    sector_payloads = [_sector_payload(by_id[eid], change) for eid, change in sorted(changes.items())]
    review_rows = [
        {"sector": str(by_id[eid].get("display_name") or eid), "ticker": ticker, "reason": reason}
        for eid, reasons in generated.items()
        for ticker, reason in reasons.items()
    ]
    samples = random.sample(review_rows, min(12, len(review_rows))) if review_rows else []
    return FillResult(
        payload={
            "full": False,
            "actor": ACTOR,
            "entry": "Fill missing sector descriptions and member reasons",
            "rationale": "M3 reasons/descriptions fill via operator-reviewed LLM draft.",
            "sectors": sector_payloads,
        },
        review_samples=samples,
        flagged_pairs=flagged_pairs,
        reasons_filled=sum(len(reasons) for reasons in generated.values()),
        descriptions_filled=sum(1 for change in changes.values() if change.get("description")),
        skipped_rollup_members=skipped_rollup_members,
    )


def post_bulk_draft(
    session: requests.sessions.Session,
    base_url: str,
    token: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    response = session.post(
        f"{base_url}/api/admin/taxonomy/bulk",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def _apply_llm_result(
    item: WorkItem,
    result: dict[str, Any],
    changes: dict[str, dict[str, Any]],
    generated: dict[str, dict[str, str]],
) -> None:
    eid = str(item.sector.get("exposure_id") or "")
    change = dict(changes.get(eid) or {})
    if item.needs_description:
        description = _text(result.get("description"))
        if description:
            change["description"] = description
    wanted = {_ticker(m) for m in item.pending_members if _ticker(m)}
    raw_reasons = result.get("reasons") if isinstance(result.get("reasons"), dict) else {}
    normalized = {
        str(key).strip().upper().split()[0].split(".")[0]: _text(value)
        for key, value in raw_reasons.items()
        if _text(value)
    }
    reasons: dict[str, str] = {}
    for member in item.pending_members:
        ticker = _ticker(member)
        reason = normalized.get(ticker)
        if ticker in wanted and reason:
            reasons[ticker] = reason
    if reasons:
        change["reasons"] = reasons
        generated[eid] = reasons
    if change:
        changes[eid] = change


def _sector_payload(sector: dict[str, Any], change: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"exposure_id": sector.get("exposure_id")}
    if change.get("description"):
        out["description"] = change["description"]
    reasons = change.get("reasons") or {}
    if reasons:
        members = []
        for member in sector.get("members") or []:
            copied = dict(member)
            ticker = _ticker(copied)
            if ticker in reasons:
                copied["reason"] = reasons[ticker]
            members.append(copied)
        out["members"] = members
    return out


def _duplicate_reason_pairs(
    sectors: list[dict[str, Any]],
    changes: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    proposed = []
    for sector in sectors:
        eid = str(sector.get("exposure_id") or "")
        copied = dict(sector)
        change = changes.get(eid) or {}
        if change.get("description"):
            copied["description"] = change["description"]
        if change.get("reasons"):
            copied["members"] = [
                {**m, "reason": change["reasons"].get(_ticker(m), m.get("reason"))}
                for m in sector.get("members") or []
            ]
        proposed.append(copied)

    by_id = {str(s.get("exposure_id") or ""): s for s in proposed}
    seen: dict[tuple[str, str], list[str]] = {}
    for sector in proposed:
        eid = str(sector.get("exposure_id") or "")
        for member in sector.get("members") or []:
            ticker = _ticker(member)
            reason = _text(member.get("reason"))
            if ticker and reason:
                seen.setdefault((ticker, reason), []).append(eid)

    pairs: list[dict[str, str]] = []
    for (ticker, reason), eids in seen.items():
        for i, left in enumerate(eids):
            for right in eids[i + 1:]:
                if _is_parent_child(by_id[left], by_id[right]):
                    continue
                pairs.append({
                    "ticker": ticker,
                    "reason": reason,
                    "left_exposure_id": left,
                    "right_exposure_id": right,
                    "left_display_name": str(by_id[left].get("display_name") or left),
                    "right_display_name": str(by_id[right].get("display_name") or right),
                })
    return pairs


def _child_tickers(children: list[dict[str, Any]]) -> set[str]:
    return {
        _ticker(member)
        for child in children
        for member in child.get("members") or []
        if _ticker(member)
    }


def _is_parent_child(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_id = str(left.get("exposure_id") or "")
    right_id = str(right.get("exposure_id") or "")
    left_parent = str(left.get("group") or left.get("parent_id") or "")
    right_parent = str(right.get("group") or right.get("parent_id") or "")
    return left_parent == right_id or right_parent == left_id


def _system_prompt() -> str:
    return (
        "你是台灣股票產業分類編輯。請只輸出嚴格 JSON："
        '{"description": "...", "reasons": {"2330": "..."}}。'
        "所有文字使用繁體中文，不要投資建議，不要股價預測。"
    )


def _user_prompt(
    sector: dict[str, Any],
    pending_members: list[dict[str, Any]],
    *,
    needs_description: bool,
) -> str:
    members = "\n".join(
        f"- {_ticker(m)} {m.get('name') or ''}".rstrip()
        for m in sector.get("members") or []
    )
    pending = ", ".join(_ticker(m) for m in pending_members if _ticker(m)) or "無"
    description_instruction = (
        "description 欄位請寫 1-2 句，說明題材是什麼與納入標準，且必須寫明台灣在此題材的真實角色。"
        "例如台灣不生產 HBM，題材追蹤的是供應鏈受惠者。"
        if needs_description
        else "description 欄位請回傳既有描述，不要改寫。"
    )
    return (
        f"產業/題材 ID：{sector.get('exposure_id')}\n"
        f"名稱：{sector.get('display_name')}\n"
        f"類型：{sector.get('exposure_type')}\n"
        f"目前描述：{sector.get('description') or '（空白）'}\n"
        f"完整成分股：\n{members}\n\n"
        f"需要補理由的股票代號：{pending}\n"
        "每檔理由說明「這檔為什麼屬於這個產業/題材」，1-2 句，禁止泛用公司簡介；"
        "請具體點出產品、供應鏈位置、需求來源或分類依據。\n"
        f"{description_instruction}\n"
        "只輸出 JSON，不要 markdown，不要額外說明。"
    )


def _parse_llm_json(content: str) -> dict[str, Any]:
    text = str(content or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    parsed = json.loads(text)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("reasons", {}), dict):
        raise ValueError("LLM response must be an object with a reasons object")
    return parsed


def _print_report(draft: dict[str, Any], result: FillResult, base_url: str) -> None:
    draft_id = draft["draft_id"]
    print(f"draft_id: {draft_id}")
    print("diff:")
    print(json.dumps(draft.get("diff", {}), ensure_ascii=False, indent=2))
    print(
        "counts: "
        f"reasons_filled={result.reasons_filled}, "
        f"descriptions_filled={result.descriptions_filled}, "
        f"skipped_rollup_members={result.skipped_rollup_members}, "
        f"flagged_pairs={len(result.flagged_pairs)}"
    )
    print("\nREVIEW SHEET")
    for row in result.review_samples:
        print(f"- {row['sector']} / {row['ticker']}: {row['reason']}")
    if result.flagged_pairs:
        print("\nFLAGGED PAIRS")
        for pair in result.flagged_pairs:
            print(
                "- "
                f"{pair['ticker']}: {pair['left_display_name']} ({pair['left_exposure_id']}) "
                f"vs {pair['right_display_name']} ({pair['right_exposure_id']}) "
                f"=> {pair['reason']}"
            )
    print("\nReview the draft above. To publish explicitly, run:")
    print(
        "curl -X POST "
        f"\"{base_url}/api/admin/taxonomy/bulk/{draft_id}/publish\" "
        f"-H \"Authorization: Bearer ${TOKEN_ENV}\""
    )


def _secret(name: str) -> str:
    val = os.getenv(name)
    if val:
        return val
    try:
        return subprocess.run(
            [
                "gcloud",
                "secrets",
                "versions",
                "access",
                "latest",
                f"--secret={name}",
                f"--project={GCP_PROJECT}",
            ],
            capture_output=True,
            text=True,
            check=True,
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
    parser.add_argument("--only", help="fill only one exposure_id; reruns skip already-filled work")
    return parser.parse_args()


def _ticker(member: dict[str, Any]) -> str:
    return str(member.get("ticker") or "").strip().upper().split(".")[0]


def _text(value: Any) -> str:
    return str(value or "").strip()


if __name__ == "__main__":
    raise SystemExit(main())
