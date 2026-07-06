"""Sector taxonomy curation helpers.

The curation step intentionally reads committed Python seed literals with ``ast``.
It must not import backend modules: this package is used from the pipelines tier and
also runs in CI without backend runtime dependencies.
"""

from __future__ import annotations

import ast
import json
import pprint
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

EMPTY_REASON_BASELINE = 1870
SINGLE_SUB_GROUP_IDS = {"sector_biotech_medical", "sector_construction_realestate"}

REPO_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_BACKEND_SEED = REPO_ROOT / "backend/src/data/sectors_seed.py"
DEFAULT_PIPELINE_SEED = REPO_ROOT / "pipelines/libs/shared/src/shared/sectors_seed_backup.py"
DEFAULT_OVERRIDES_JSON = REPO_ROOT / "pipelines/libs/shared/curation/sector_overrides.json"
DEFAULT_MEMBER_REASONS_JSON = (
    REPO_ROOT / "pipelines/libs/shared/curation/sector_member_reasons.json"
)


@dataclass
class CurateResult:
    seed: list[dict[str, Any]]
    redirects: dict[str, str]
    reasons: dict[str, dict[str, str]]
    applied: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def load_seed_from_py(path: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Read ``SECTORS_SEED`` and optional ``SECTOR_REDIRECTS`` from a Python file."""
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    seed: list[dict[str, Any]] | None = None
    redirects: dict[str, str] = {}
    for stmt in module.body:
        if not isinstance(stmt, ast.Assign):
            continue
        names = {target.id for target in stmt.targets if isinstance(target, ast.Name)}
        if "SECTORS_SEED" in names:
            seed = ast.literal_eval(stmt.value)
        if "SECTOR_REDIRECTS" in names:
            redirects = ast.literal_eval(stmt.value)
    if seed is None:
        raise ValueError(f"{path} does not define SECTORS_SEED")
    return seed, redirects


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return deepcopy(default)
    return json.loads(path.read_text(encoding="utf-8"))


def empty_overrides() -> dict[str, Any]:
    return {
        "exclude": [],
        "include": [],
        "merge": [],
        "reclassify": {},
        "rename": {},
        "descriptions": {},
    }


def curate_seed(
    seed: list[dict[str, Any]],
    *,
    overrides: dict[str, Any] | None = None,
    member_reasons: dict[str, dict[str, str]] | None = None,
    enforce: bool = False,
    blank_duplicate_reasons: bool = False,
    inherited_redirects: dict[str, str] | None = None,
) -> CurateResult:
    """Apply curation inputs and return the emitted seed + sidecar maps."""
    working = deepcopy(seed)
    redirects = dict(inherited_redirects or {})
    applied: list[str] = []
    warnings: list[str] = []

    apply_overrides(working, overrides or empty_overrides(), redirects, applied)
    merge_member_reasons(working, member_reasons or {}, applied)
    if blank_duplicate_reasons:
        blanked = blank_duplicate_reasons_for_non_parent_child_sectors(working)
        if blanked:
            applied.append(f"blank duplicate reasons in {blanked} member rows")

    if enforce:
        apply_industry_rollups(working, applied)

    reasons = extract_reasons(working)
    warnings.extend(validate_seed(working, redirects, enforce=enforce))
    return CurateResult(seed=working, redirects=redirects, reasons=reasons, applied=applied, warnings=warnings)


def apply_overrides(
    seed: list[dict[str, Any]],
    overrides: dict[str, Any],
    redirects: dict[str, str],
    applied: list[str],
) -> None:
    by_id = _by_id(seed)

    for item in overrides.get("exclude") or []:
        eid = str(item.get("exposure_id") or "")
        ticker = _bare_ticker(item.get("ticker"))
        sector = by_id.get(eid)
        if not sector or not ticker:
            continue
        before = len(sector.get("members") or [])
        sector["members"] = [
            m for m in sector.get("members") or []
            if _bare_ticker((m or {}).get("ticker")) != ticker
        ]
        if len(sector["members"]) != before:
            applied.append(f"exclude {ticker} from {eid}")

    for item in overrides.get("include") or []:
        eid = str(item.get("exposure_id") or "")
        member = deepcopy(item.get("member") or {})
        ticker = _bare_ticker(member.get("ticker"))
        sector = by_id.get(eid)
        if not sector or not ticker:
            continue
        member["ticker"] = ticker
        _upsert_member(sector, member)
        applied.append(f"include {ticker} in {eid}")

    for item in overrides.get("merge") or []:
        source_id = str(item.get("from") or item.get("source") or "")
        target_id = str(item.get("into") or item.get("target") or "")
        source = by_id.get(source_id)
        target = by_id.get(target_id)
        if not source or not target or source_id == target_id:
            continue
        for member in source.get("members") or []:
            _upsert_member(target, deepcopy(member))
        target["aliases"] = _dedupe_strings(
            (target.get("aliases") or [])
            + [source.get("display_name") or source_id]
            + (source.get("aliases") or [])
        )
        redirects[source_id] = target_id
        seed[:] = [sector for sector in seed if sector.get("exposure_id") != source_id]
        by_id = _by_id(seed)
        applied.append(f"merge {source_id} into {target_id}")

    for eid, spec in (overrides.get("reclassify") or {}).items():
        sector = by_id.get(str(eid))
        if not sector:
            continue
        if isinstance(spec, str):
            sector["exposure_type"] = spec
        elif isinstance(spec, dict):
            if "exposure_type" in spec:
                sector["exposure_type"] = spec["exposure_type"]
            if "group" in spec:
                sector["group"] = spec["group"]
        applied.append(f"reclassify {eid}")

    for eid, spec in (overrides.get("rename") or {}).items():
        sector = by_id.get(str(eid))
        if not sector:
            continue
        if isinstance(spec, str):
            sector["display_name"] = spec
        elif isinstance(spec, dict) and spec.get("display_name"):
            sector["display_name"] = spec["display_name"]
        applied.append(f"rename {eid}")

    for eid, description in (overrides.get("descriptions") or {}).items():
        sector = by_id.get(str(eid))
        if not sector:
            continue
        sector["description"] = str(description or "").strip()
        applied.append(f"description {eid}")


def merge_member_reasons(
    seed: list[dict[str, Any]],
    member_reasons: dict[str, dict[str, str]],
    applied: list[str],
) -> None:
    for sector in seed:
        eid = str(sector.get("exposure_id") or "")
        curated = member_reasons.get(eid) or {}
        if not curated:
            continue
        for member in sector.get("members") or []:
            ticker = _bare_ticker((member or {}).get("ticker"))
            reason = curated.get(ticker)
            if isinstance(reason, str):
                member["reason"] = reason.strip()
                applied.append(f"reason {eid}/{ticker}")


def blank_duplicate_reasons_for_non_parent_child_sectors(seed: list[dict[str, Any]]) -> int:
    """Blank copied company blurbs that appear in multiple unrelated sectors."""
    by_id = _by_id(seed)
    occurrences: dict[tuple[str, str], list[tuple[str, dict[str, Any]]]] = {}
    for sector in seed:
        eid = str(sector.get("exposure_id") or "")
        for member in sector.get("members") or []:
            ticker = _bare_ticker((member or {}).get("ticker"))
            reason = str((member or {}).get("reason") or "").strip()
            if ticker and reason:
                occurrences.setdefault((ticker, reason), []).append((eid, member))

    tainted: set[tuple[str, str]] = set()
    for key, rows in occurrences.items():
        eids = [eid for eid, _member in rows]
        for i, left in enumerate(eids):
            for right in eids[i + 1:]:
                if not _is_parent_child(by_id[left], by_id[right]):
                    tainted.add(key)
                    break
            if key in tainted:
                break

    blanked = 0
    for key in tainted:
        for _eid, member in occurrences[key]:
            if member.get("reason"):
                member["reason"] = ""
                blanked += 1
    return blanked


def apply_industry_rollups(seed: list[dict[str, Any]], applied: list[str]) -> None:
    children_by_parent: dict[str, list[dict[str, Any]]] = {}
    for sector in seed:
        parent = sector.get("group")
        if parent:
            children_by_parent.setdefault(str(parent), []).append(sector)

    for sector in seed:
        eid = str(sector.get("exposure_id") or "")
        if sector.get("exposure_type") != "industry" or eid in SINGLE_SUB_GROUP_IDS:
            continue
        child_members: dict[str, dict[str, Any]] = {}
        for child in children_by_parent.get(eid, []):
            for member in child.get("members") or []:
                ticker = _bare_ticker((member or {}).get("ticker"))
                if ticker and ticker not in child_members:
                    child_members[ticker] = deepcopy(member)
        if not child_members:
            continue
        existing_order = [
            _bare_ticker((member or {}).get("ticker"))
            for member in sector.get("members") or []
        ]
        ordered = [child_members[t] for t in existing_order if t in child_members]
        ordered.extend(
            member for ticker, member in child_members.items()
            if ticker not in set(existing_order)
        )
        sector["members"] = ordered
        applied.append(f"rollup {eid}")


def validate_seed(
    seed: list[dict[str, Any]],
    redirects: dict[str, str],
    *,
    enforce: bool,
) -> list[str]:
    us = [
        (s.get("exposure_id"), m.get("ticker"))
        for s in seed
        for m in s.get("members") or []
        if (m or {}).get("market") != "TW"
    ]
    empty = [s.get("exposure_id") for s in seed if not s.get("members")]
    if us:
        raise AssertionError(f"US tickers leaked into the TW seed: {us[:10]}")
    if empty:
        raise AssertionError(f"empty sectors: {empty}")

    empty_reasons = sum(
        1 for sector in seed for member in sector.get("members") or []
        if not (member or {}).get("reason")
    )
    if empty_reasons > EMPTY_REASON_BASELINE:
        raise AssertionError(
            f"empty member reasons {empty_reasons} exceed baseline {EMPTY_REASON_BASELINE}"
        )

    for old, new in redirects.items():
        if old == new:
            raise AssertionError(f"redirect {old} points to itself")
    ids = {str(s.get("exposure_id") or "") for s in seed}
    missing_targets = {target for target in redirects.values() if target not in ids}
    if missing_targets:
        raise AssertionError(f"redirect targets missing from seed: {sorted(missing_targets)}")

    warnings: list[str] = []
    if enforce:
        _validate_duplicate_reasons(seed)
        _validate_jaccard(seed)
        warnings.extend(_validate_size_band(seed))
    return warnings


def extract_reasons(seed: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for sector in seed:
        bucket = {
            _bare_ticker(member.get("ticker")): str(member.get("reason")).strip()
            for member in sector.get("members") or []
            if (member or {}).get("reason") and _bare_ticker(member.get("ticker"))
        }
        if bucket:
            out[str(sector.get("exposure_id"))] = bucket
    return out


def emit_seed_py(seed: list[dict[str, Any]], redirects: dict[str, str]) -> str:
    n_ind = sum(1 for s in seed if s["exposure_type"] == "industry")
    n_thm = sum(1 for s in seed if s["exposure_type"] == "theme")
    header = (
        f'"""Database seed data for {len(seed)} TW sectors and themes '
        f'({n_ind} industries + {n_thm} themes).\n\n'
        "Generated from the tide-tw-data curation by\n"
        "pipelines/libs/shared/scripts/build_sectors_seed_from_tide.py — do not hand-edit;\n"
        "re-run that script to regenerate. TW-only (US exposures live in a separate tab).\n"
        '"""\n\n'
    )
    seed_src = pprint.pformat(seed, width=110, sort_dicts=False)
    redirects_src = pprint.pformat(redirects, width=110, sort_dicts=False)
    return f"{header}SECTOR_REDIRECTS = {redirects_src}\n\nSECTORS_SEED = {seed_src}\n"


def curate_artifacts(
    *,
    backend_seed_path: Path = DEFAULT_BACKEND_SEED,
    pipeline_seed_path: Path = DEFAULT_PIPELINE_SEED,
    overrides_path: Path = DEFAULT_OVERRIDES_JSON,
    member_reasons_path: Path = DEFAULT_MEMBER_REASONS_JSON,
    enforce: bool = False,
    blank_duplicate_reasons: bool = False,
) -> CurateResult:
    seed, redirects = load_seed_from_py(backend_seed_path)
    result = curate_seed(
        seed,
        overrides=load_json(overrides_path, empty_overrides()),
        member_reasons=load_json(member_reasons_path, {}),
        enforce=enforce,
        blank_duplicate_reasons=blank_duplicate_reasons,
        inherited_redirects=redirects,
    )
    seed_src = emit_seed_py(result.seed, result.redirects)
    _write_if_changed(backend_seed_path, seed_src)
    _write_if_changed(pipeline_seed_path, seed_src)
    return result


def _write_if_changed(path: Path, content: str) -> None:
    old = path.read_text(encoding="utf-8") if path.exists() else None
    if old != content:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _validate_duplicate_reasons(seed: list[dict[str, Any]]) -> None:
    seen: dict[tuple[str, str], list[str]] = {}
    for sector in seed:
        eid = str(sector.get("exposure_id") or "")
        for member in sector.get("members") or []:
            ticker = _bare_ticker((member or {}).get("ticker"))
            reason = str((member or {}).get("reason") or "").strip()
            if ticker and reason:
                seen.setdefault((ticker, reason), []).append(eid)
    offenders = []
    by_id = _by_id(seed)
    for (ticker, reason), eids in seen.items():
        for i, left in enumerate(eids):
            for right in eids[i + 1:]:
                if not _is_parent_child(by_id[left], by_id[right]):
                    offenders.append(f"{ticker}: {left}, {right}: {reason}")
    if offenders:
        raise AssertionError("duplicate non-empty member reasons:\n" + "\n".join(offenders))


def _validate_jaccard(seed: list[dict[str, Any]]) -> None:
    by_id = _by_id(seed)
    ticker_sets = {
        eid: {
            _bare_ticker((member or {}).get("ticker"))
            for member in sector.get("members") or []
            if _bare_ticker((member or {}).get("ticker"))
        }
        for eid, sector in by_id.items()
    }
    offenders = []
    ids = list(by_id)
    for i, left in enumerate(ids):
        for right in ids[i + 1:]:
            if _is_parent_child(by_id[left], by_id[right]):
                continue
            a = ticker_sets[left]
            b = ticker_sets[right]
            if not a or not b:
                continue
            score = len(a & b) / len(a | b)
            if score >= 0.8:
                offenders.append(f"{left} / {right}: {score:.2f}")
    if offenders:
        raise AssertionError("redundant sector membership (Jaccard >= 0.8):\n" + "\n".join(offenders))


def _validate_size_band(seed: list[dict[str, Any]]) -> list[str]:
    warnings = []
    for sector in seed:
        if sector.get("exposure_type") != "theme":
            continue
        size = len(sector.get("members") or [])
        if size < 4 or size > 40:
            warnings.append(f"POL-5 theme size warning: {sector.get('exposure_id')} has {size} members")
    return warnings


def _is_parent_child(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_id = str(left.get("exposure_id") or "")
    right_id = str(right.get("exposure_id") or "")
    return left.get("group") == right_id or right.get("group") == left_id


def _by_id(seed: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(sector.get("exposure_id") or ""): sector for sector in seed}


def _bare_ticker(value: Any) -> str:
    return str(value or "").strip().upper().split(".")[0]


def _upsert_member(sector: dict[str, Any], member: dict[str, Any]) -> None:
    ticker = _bare_ticker(member.get("ticker"))
    members = sector.setdefault("members", [])
    for idx, existing in enumerate(members):
        if _bare_ticker((existing or {}).get("ticker")) == ticker:
            members[idx] = member
            return
    members.append(member)


def _dedupe_strings(values: list[Any]) -> list[str]:
    out = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            out.append(text)
            seen.add(text)
    return out
