from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = REPO / "pipelines/libs/shared/scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import audit_sector_universe as audit  # noqa: E402


def _member(ticker: str, reason: str = "", name: str | None = None) -> dict[str, Any]:
    return {"ticker": ticker, "name": name or ticker, "market": "TW", "reason": reason}


def _sector(
    exposure_id: str,
    members: list[dict[str, Any]],
    *,
    exposure_type: str = "theme",
    group: str | None = None,
    description: str = "desc",
) -> dict[str, Any]:
    return {
        "exposure_id": exposure_id,
        "display_name": exposure_id,
        "exposure_type": exposure_type,
        "description": description,
        "group": group,
        "members": members,
    }


# --------------------------------------------------------------------------- metrics


def test_member_counts_and_small_large_buckets():
    sectors = [
        _sector("sector_tiny", [_member("1001", "r")]),
        _sector("sector_normal", [_member(str(1000 + i), "r") for i in range(5)]),
    ]
    m = audit.compute_metrics(sectors)
    assert m["sector_count"] == 2
    assert m["counts"]["min"] == 1
    assert m["counts"]["max"] == 5
    assert ("sector_tiny", 1) in m["small_sectors"]
    assert m["large_sectors"] == []


def test_fanout_counts_sectors_per_ticker():
    sectors = [
        _sector("sector_a", [_member("2330", "r", name="TSMC")]),
        _sector("sector_b", [_member("2330", "r", name="TSMC")]),
    ]
    m = audit.compute_metrics(sectors)
    fanout_map = {t: c for t, c, _name in m["top_fanout"]}
    assert fanout_map["2330"] == 2


def test_jaccard_overlap_exempts_parent_child_pair():
    # Industry rolls up its child theme's full membership -> Jaccard == 1.0, but
    # parent/child pairs must be exempted from the merge-candidate signal.
    parent = _sector(
        "sector_industry",
        [_member("1001", "r"), _member("1002", "r")],
        exposure_type="industry",
    )
    child = _sector("sector_theme", [_member("1001", "r"), _member("1002", "r")], group="sector_industry")
    m = audit.compute_metrics([parent, child])
    assert m["jaccard_pairs"] == []
    assert m["subset_pairs"] == []


def test_jaccard_overlap_flags_non_parent_child_duplicate():
    a = _sector("sector_a", [_member("1001", "r"), _member("1002", "r")])
    b = _sector("sector_b", [_member("1001", "r"), _member("1002", "r")])
    m = audit.compute_metrics([a, b])
    assert len(m["jaccard_pairs"]) == 1
    assert m["jaccard_pairs"][0][2] == 1.0


def test_duplicate_reason_exempts_parent_child():
    parent = _sector(
        "sector_industry",
        [_member("1001", "same reason")],
        exposure_type="industry",
    )
    child = _sector("sector_theme", [_member("1001", "same reason")], group="sector_industry")
    m = audit.compute_metrics([parent, child])
    assert m["reused_pairs"] == {}


def test_duplicate_reason_flags_non_parent_child():
    a = _sector("sector_a", [_member("1001", "same reason")])
    b = _sector("sector_b", [_member("1001", "same reason")])
    m = audit.compute_metrics([a, b])
    assert ("1001", "same reason") in m["reused_pairs"]
    assert set(m["reused_pairs"][("1001", "same reason")]) == {"sector_a", "sector_b"}


def test_empty_reasons_and_descriptions_counted():
    sectors = [
        _sector("sector_a", [_member("1001", ""), _member("1002", "r")], description=""),
    ]
    m = audit.compute_metrics(sectors)
    assert m["empty_reason"] == 1
    assert m["empty_descriptions"] == 1


def test_hierarchy_checks():
    sectors = [
        _sector("sector_industry", [_member("1001", "r")], exposure_type="industry"),
        _sector("sector_no_group", [_member("1002", "r")], group=None),
        _sector("sector_bad_group", [_member("1003", "r")], group="not_an_industry"),
    ]
    m = audit.compute_metrics(sectors)
    assert "sector_no_group" in m["themes_no_group"]
    assert ("sector_bad_group", "not_an_industry") in m["bad_group_refs"]


def test_render_report_is_nonempty_markdown():
    sectors = [_sector("sector_a", [_member("1001", "r")])]
    m = audit.compute_metrics(sectors)
    report = audit.render_report(m, source="https://example.com/snapshot")
    assert report.startswith("# Sector Universe Audit")
    assert "sector_count" not in report  # rendered, not the raw key


# --------------------------------------------------------------------------- judge


class _FakeResponse:
    def __init__(self, content: str) -> None:
        self._content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {"choices": [{"message": {"content": self._content}}]}


class _FakeSession:
    def __init__(self, contents: list[str]) -> None:
        self._contents = list(contents)
        self.calls = 0

    def post(self, *args: Any, **kwargs: Any) -> _FakeResponse:
        self.calls += 1
        return _FakeResponse(self._contents.pop(0))


def test_judge_parses_strict_json():
    session = _FakeSession(['{"failing_members": [{"ticker": "1001", "justification": "no fit"}]}'])
    judge = audit.OpenRouterJudge(api_key="k", model="m", session=session, sleep=lambda _s: None)
    result = judge.judge_sector({"exposure_id": "sector_a", "display_name": "A", "members": []})
    assert result["failing_members"][0]["ticker"] == "1001"
    assert session.calls == 1


def test_judge_strips_markdown_fences():
    session = _FakeSession(['```json\n{"failing_members": []}\n```'])
    judge = audit.OpenRouterJudge(api_key="k", model="m", session=session, sleep=lambda _s: None)
    result = judge.judge_sector({"exposure_id": "sector_a", "members": []})
    assert result["failing_members"] == []


def test_judge_retries_then_raises():
    session = _FakeSession(["not json", "still not json", "nope"])
    judge = audit.OpenRouterJudge(api_key="k", model="m", session=session, sleep=lambda _s: None)
    with pytest.raises(RuntimeError):
        judge.judge_sector({"exposure_id": "sector_a", "members": []})
    assert session.calls == 3


def test_judge_retries_then_succeeds():
    session = _FakeSession(["not json", '{"failing_members": []}'])
    judge = audit.OpenRouterJudge(api_key="k", model="m", session=session, sleep=lambda _s: None)
    result = judge.judge_sector({"exposure_id": "sector_a", "members": []})
    assert result["failing_members"] == []
    assert session.calls == 2


# --------------------------------------------------------------------------- guard


def test_guard_refuses_path_inside_repo():
    with pytest.raises(SystemExit):
        audit.guard_out_path(REPO / "docs" / "leaked_taxonomy.md", repo_root=REPO)


def test_guard_allows_tmp_path():
    out = audit.guard_out_path(Path("/tmp/sector_audit_test.md"), repo_root=REPO)
    assert str(out).startswith(("/tmp/", "/private/tmp/"))


def test_guard_allows_explicit_repo_out_escape():
    out = audit.guard_out_path(REPO / "docs" / "leaked_taxonomy.md", repo_root=REPO, allow_repo_out=True)
    assert out == (REPO / "docs" / "leaked_taxonomy.md").resolve()


def test_guard_allows_paths_outside_repo_and_outside_tmp(tmp_path):
    outside = tmp_path / "sector_audit.md"  # pytest tmp_path is not under this repo
    out = audit.guard_out_path(outside, repo_root=REPO)
    assert out == outside.resolve()
