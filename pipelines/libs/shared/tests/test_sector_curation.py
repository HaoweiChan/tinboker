from __future__ import annotations

import sys
from pathlib import Path

import pytest
from shared.curation import (
    blank_duplicate_reasons_for_non_parent_child_sectors,
    curate_seed,
    emit_seed_py,
    empty_overrides,
)

REPO = Path(__file__).resolve().parents[4]


def _member(ticker: str, reason: str = "") -> dict:
    return {
        "ticker": ticker,
        "name": ticker,
        "name_en": None,
        "market": "TW",
        "source": "tide",
        "reason": reason,
    }


def _sector(
    exposure_id: str,
    exposure_type: str,
    members: list[dict],
    group: str | None = None,
    display_name: str | None = None,
) -> dict:
    return {
        "exposure_id": exposure_id,
        "exposure_type": exposure_type,
        "display_name": display_name or exposure_id,
        "icon_id": "cpu",
        "color_hex": "#3B82F6",
        "group": group,
        "aliases": [display_name or exposure_id],
        "members": members,
    }


def test_curate_applies_every_override_type_and_reason_file():
    seed = [
        _sector("sector_parent", "industry", [_member("1001", "parent reason")]),
        _sector("sector_child", "theme", [_member("1001", "parent reason"), _member("1002")], "sector_parent"),
        _sector("sector_target", "theme", [_member("2001")], "sector_parent"),
        _sector("sector_source", "theme", [_member("2002")], "sector_parent", "Source Display"),
        _sector("sector_other", "theme", [_member("3001")], "sector_parent"),
    ]
    overrides = {
        "exclude": [{"exposure_id": "sector_child", "ticker": "1002"}],
        "include": [{"exposure_id": "sector_child", "member": _member("1003")}],
        "merge": [{"from": "sector_source", "into": "sector_target"}],
        "reclassify": {"sector_other": {"exposure_type": "industry", "group": None}},
        "rename": {"sector_child": "Renamed Child"},
        "descriptions": {"sector_child": "Child description"},
    }

    result = curate_seed(
        seed,
        overrides=overrides,
        member_reasons={"sector_child": {"1003": "curated reason"}},
        enforce=False,
    )
    by_id = {s["exposure_id"]: s for s in result.seed}

    assert "sector_source" not in by_id
    assert result.redirects == {"sector_source": "sector_target"}
    assert [m["ticker"] for m in by_id["sector_child"]["members"]] == ["1001", "1003"]
    assert by_id["sector_child"]["display_name"] == "Renamed Child"
    assert by_id["sector_child"]["description"] == "Child description"
    assert by_id["sector_other"]["exposure_type"] == "industry"
    assert by_id["sector_other"]["group"] is None
    assert [m["ticker"] for m in by_id["sector_target"]["members"]] == ["2001", "2002"]
    assert by_id["sector_child"]["members"][1]["reason"] == "curated reason"
    assert "Source Display" in by_id["sector_target"]["aliases"]


def test_enforced_rollups_keep_theme_less_industry_rosters():
    seed = [
        _sector("sector_parent", "industry", [_member("9999")]),
        _sector("sector_child_a", "theme", [_member("1001"), _member("1002")], "sector_parent"),
        _sector("sector_child_b", "theme", [_member("1002"), _member("1003")], "sector_parent"),
        _sector("sector_biotech_medical", "industry", [_member("7001")]),
    ]

    result = curate_seed(seed, overrides=empty_overrides(), enforce=True)
    by_id = {s["exposure_id"]: s for s in result.seed}

    assert [m["ticker"] for m in by_id["sector_parent"]["members"]] == ["1001", "1002", "1003"]
    assert [m["ticker"] for m in by_id["sector_biotech_medical"]["members"]] == ["7001"]


def test_enforced_duplicate_reason_allows_parent_child_only():
    allowed = [
        _sector("sector_parent", "industry", [_member("1001", "same reason")]),
        _sector("sector_child", "theme", [_member("1001", "same reason")], "sector_parent"),
    ]
    curate_seed(allowed, overrides=empty_overrides(), enforce=True)

    rejected = allowed + [
        _sector("sector_peer", "theme", [_member("1001", "same reason")]),
    ]
    with pytest.raises(AssertionError, match="duplicate non-empty"):
        curate_seed(rejected, overrides=empty_overrides(), enforce=True)


def test_blank_duplicate_reasons_blanks_every_tainted_occurrence():
    seed = [
        _sector("sector_parent", "industry", [_member("1001", "same reason")]),
        _sector("sector_child", "theme", [_member("1001", "same reason")], "sector_parent"),
        _sector("sector_peer", "theme", [_member("1001", "same reason")]),
        _sector("sector_clean", "theme", [_member("1002", "same reason")]),
    ]

    result = curate_seed(
        seed,
        overrides=empty_overrides(),
        blank_duplicate_reasons=True,
        enforce=False,
    )
    by_id = {s["exposure_id"]: s for s in result.seed}

    assert by_id["sector_parent"]["members"][0]["reason"] == ""
    assert by_id["sector_child"]["members"][0]["reason"] == ""
    assert by_id["sector_peer"]["members"][0]["reason"] == ""
    assert by_id["sector_clean"]["members"][0]["reason"] == "same reason"
    assert "blank duplicate reasons in 3 member rows" in result.applied


def test_blank_duplicate_reasons_leaves_parent_child_only_copy():
    seed = [
        _sector("sector_parent", "industry", [_member("1001", "same reason")]),
        _sector("sector_child", "theme", [_member("1001", "same reason")], "sector_parent"),
    ]

    assert blank_duplicate_reasons_for_non_parent_child_sectors(seed) == 0
    assert seed[0]["members"][0]["reason"] == "same reason"
    assert seed[1]["members"][0]["reason"] == "same reason"


def test_enforced_jaccard_allows_parent_child_only():
    allowed = [
        _sector("sector_parent", "industry", [_member("1001"), _member("1002")]),
        _sector("sector_child", "theme", [_member("1001"), _member("1002")], "sector_parent"),
    ]
    curate_seed(allowed, overrides=empty_overrides(), enforce=True)

    rejected = allowed + [
        _sector("sector_peer", "theme", [_member("1001"), _member("1002")]),
    ]
    with pytest.raises(AssertionError, match="Jaccard"):
        curate_seed(rejected, overrides=empty_overrides(), enforce=True)


def test_tide_builder_final_stage_calls_curate_without_tide(tmp_path, monkeypatch):
    scripts_dir = REPO / "pipelines/libs/shared/scripts"
    sys.path.insert(0, str(scripts_dir))
    import build_sectors_seed_from_tide as builder

    backend_seed = tmp_path / "sectors_seed.py"
    pipeline_seed = tmp_path / "sectors_seed_backup.py"
    overrides_json = tmp_path / "sector_overrides.json"
    member_reasons_json = tmp_path / "sector_member_reasons.json"
    base_seed = [_sector("sector_a", "theme", [_member("1001")])]
    backend_seed.write_text(emit_seed_py(base_seed, {}), encoding="utf-8")
    pipeline_seed.write_text("", encoding="utf-8")
    overrides_json.write_text('{"rename": {"sector_a": "Renamed"}}', encoding="utf-8")
    member_reasons_json.write_text('{"sector_a": {"1001": "reason"}}', encoding="utf-8")

    monkeypatch.setattr(builder, "BACKEND_SEED", backend_seed)
    monkeypatch.setattr(builder, "PIPELINE_SEED", pipeline_seed)
    monkeypatch.setattr(builder, "DEFAULT_OVERRIDES_JSON", overrides_json)
    monkeypatch.setattr(builder, "DEFAULT_MEMBER_REASONS_JSON", member_reasons_json)
    monkeypatch.setattr(builder, "build", lambda _tide: base_seed)
    monkeypatch.setattr(sys, "argv", ["build_sectors_seed_from_tide.py", "--write"])

    assert builder.main() is None
    assert "Renamed" in backend_seed.read_text(encoding="utf-8")
