"""Backend copy of the sector taxonomy POL validators.

The pipelines tier owns a bootstrap fixture and engine tests, but production writes
now enter through the backend admin API. Keeping this copy local avoids a runtime
cross-tier import while preserving the same write-time invariants.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

EMPTY_REASON_BASELINE = 1870
REQUIRE_MEMBER_REASONS_ENV = "TAXONOMY_REQUIRE_MEMBER_REASONS"


@dataclass
class TaxonomyValidationError(Exception):
    """Validation failure with machine-readable offender strings for 422 responses."""

    rule: str
    offenders: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        joined = ", ".join(self.offenders[:10])
        return f"{self.rule}: {joined}" if joined else self.rule


def validate_taxonomy(
    sectors: list[dict[str, Any]],
    redirects: dict[str, str] | None = None,
    *,
    enforce: bool = True,
    previous_sectors: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Validate the full would-be published taxonomy state.

    Returns non-blocking warnings. Raises TaxonomyValidationError for hard POL
    violations so API callers can see the exact offending sector/ticker pairs.
    """
    redirects = redirects or {}
    us = [
        f"{sector.get('exposure_id')}/{member.get('ticker')}"
        for sector in sectors
        for member in sector.get("members") or []
        if (member or {}).get("market") != "TW"
    ]
    if us:
        raise TaxonomyValidationError("US tickers leaked into the TW taxonomy", us[:10])

    empty = [str(s.get("exposure_id") or "") for s in sectors if not s.get("members")]
    if empty:
        raise TaxonomyValidationError("empty sectors", empty)

    empty_reasons = sum(
        1
        for sector in sectors
        for member in sector.get("members") or []
        if not (member or {}).get("reason")
    )
    if empty_reasons > EMPTY_REASON_BASELINE:
        raise TaxonomyValidationError(
            f"empty member reasons {empty_reasons} exceed baseline {EMPTY_REASON_BASELINE}",
            [str(empty_reasons)],
        )
    if _require_member_reasons():
        _validate_new_members_have_reasons(sectors, previous_sectors or [])

    self_redirects = [old for old, new in redirects.items() if old == new]
    if self_redirects:
        raise TaxonomyValidationError("redirect points to itself", self_redirects)

    ids = {str(s.get("exposure_id") or "") for s in sectors}
    missing_targets = sorted({target for target in redirects.values() if target not in ids})
    if missing_targets:
        raise TaxonomyValidationError("redirect targets missing from taxonomy", missing_targets)

    warnings: list[str] = []
    if enforce:
        _validate_duplicate_reasons(sectors)
        _validate_jaccard(sectors)
        warnings.extend(_validate_size_band(sectors))
    return warnings


def _validate_new_members_have_reasons(
    sectors: list[dict[str, Any]],
    previous_sectors: list[dict[str, Any]],
) -> None:
    previous_keys = {
        _member_identity(sector, member)
        for sector in previous_sectors
        for member in sector.get("members") or []
    }
    offenders = [
        f"{sector.get('exposure_id')}/{member.get('ticker')}"
        for sector in sectors
        for member in sector.get("members") or []
        if _member_identity(sector, member) not in previous_keys
        and not str((member or {}).get("reason") or "").strip()
    ]
    if offenders:
        raise TaxonomyValidationError("new members require non-empty reasons", offenders[:50])


def _validate_duplicate_reasons(sectors: list[dict[str, Any]]) -> None:
    seen: dict[tuple[str, str], list[str]] = {}
    for sector in sectors:
        eid = str(sector.get("exposure_id") or "")
        for member in sector.get("members") or []:
            ticker = _bare_ticker((member or {}).get("ticker"))
            reason = str((member or {}).get("reason") or "").strip()
            if ticker and reason:
                seen.setdefault((ticker, reason), []).append(eid)

    offenders: list[str] = []
    by_id = _by_id(sectors)
    for (ticker, reason), eids in seen.items():
        for i, left in enumerate(eids):
            for right in eids[i + 1:]:
                if not _is_parent_child(by_id[left], by_id[right]):
                    offenders.append(f"{ticker}: {left}, {right}: {reason}")
    if offenders:
        raise TaxonomyValidationError("duplicate non-empty member reasons", offenders)


def _validate_jaccard(sectors: list[dict[str, Any]]) -> None:
    by_id = _by_id(sectors)
    ticker_sets = {
        eid: {
            _bare_ticker((member or {}).get("ticker"))
            for member in sector.get("members") or []
            if _bare_ticker((member or {}).get("ticker"))
        }
        for eid, sector in by_id.items()
    }
    offenders: list[str] = []
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
        raise TaxonomyValidationError("redundant sector membership (Jaccard >= 0.8)", offenders)


def _validate_size_band(sectors: list[dict[str, Any]]) -> list[str]:
    warnings = []
    for sector in sectors:
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


def _by_id(sectors: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(sector.get("exposure_id") or ""): sector for sector in sectors}


def _bare_ticker(value: Any) -> str:
    return str(value or "").strip().upper().split(".")[0]


def _member_identity(sector: dict[str, Any], member: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(sector.get("exposure_id") or ""),
        _bare_ticker((member or {}).get("ticker")),
        str((member or {}).get("market") or "").upper(),
    )


def _require_member_reasons() -> bool:
    return str(os.getenv(REQUIRE_MEMBER_REASONS_ENV) or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
