from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "fill_sector_reasons.py"
SPEC = importlib.util.spec_from_file_location("fill_sector_reasons", SCRIPT)
fill = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = fill
SPEC.loader.exec_module(fill)


def _member(ticker: str, reason: str = "", name: str | None = None) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "name": name or ticker,
        "market": "TW",
        "source": "test",
        "reason": reason,
    }


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


class FakeLLM:
    def __init__(self, responses: dict[str, list[dict[str, Any]]]) -> None:
        self.responses = responses
        self.calls: list[str] = []

    def complete_sector(
        self,
        sector: dict[str, Any],
        pending_members: list[dict[str, Any]],
        *,
        needs_description: bool,
    ) -> dict[str, Any]:
        _ = pending_members, needs_description
        eid = sector["exposure_id"]
        self.calls.append(eid)
        return self.responses[eid].pop(0)


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, Any], *, fail: bool = False) -> None:
        self.payload = payload
        self.fail = fail

    def raise_for_status(self) -> None:
        if self.fail:
            raise RuntimeError("boom")

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeHTTPSession:
    def __init__(self) -> None:
        self.posts: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeHTTPResponse:
        _ = url, kwargs
        return FakeHTTPResponse({"sectors": [_sector("sector_a", [_member("1001")])]})

    def post(self, url: str, **kwargs: Any) -> FakeHTTPResponse:
        self.posts.append({"url": url, **kwargs})
        return FakeHTTPResponse({"draft_id": 7, "diff": {"changed": 1}})


def test_detect_work_skips_industry_rollup_comembers_but_fills_other_industry_members():
    sectors = [
        _sector(
            "sector_parent",
            [_member("1001"), _member("2002")],
            exposure_type="industry",
            description="",
        ),
        _sector("sector_child", [_member("1001")], group="sector_parent"),
    ]

    work, skipped = fill.detect_work(sectors)

    assert skipped == 1
    parent = next(item for item in work if item.sector["exposure_id"] == "sector_parent")
    assert [m["ticker"] for m in parent.pending_members] == ["2002"]
    assert parent.needs_description is True


def test_detect_work_only_and_resume_skip_already_filled():
    sectors = [
        _sector("sector_done", [_member("1001", "already")], description="already"),
        _sector("sector_pending", [_member("2002")], description=""),
    ]

    work, skipped = fill.detect_work(sectors, only="sector_done")

    assert skipped == 0
    assert work == []


def test_openrouter_retries_and_parses_strict_json():
    class RetrySession:
        def __init__(self) -> None:
            self.calls = 0

        def post(self, *args: Any, **kwargs: Any) -> FakeHTTPResponse:
            _ = args, kwargs
            self.calls += 1
            if self.calls < 3:
                return FakeHTTPResponse({}, fail=True)
            return FakeHTTPResponse({
                "choices": [
                    {
                        "message": {
                            "content": '{"description":"描述","reasons":{"1001":"具體理由"}}'
                        }
                    }
                ]
            })

    session = RetrySession()
    client = fill.OpenRouterClient(api_key="secret", model="model", session=session, sleep=lambda _: None)

    result = client.complete_sector(_sector("sector_a", [_member("1001")]), [_member("1001")], needs_description=True)

    assert session.calls == 3
    assert result["reasons"]["1001"] == "具體理由"


def test_distinctness_reasks_once_and_payload_is_reasons_only_merge_shape():
    sectors = [
        _sector("sector_a", [_member("2330", name="台積電")]),
        _sector("sector_b", [_member("2330", name="台積電")]),
    ]
    work, skipped = fill.detect_work(sectors)
    llm = FakeLLM({
        "sector_a": [{"description": "", "reasons": {"2330": "相同理由"}}],
        "sector_b": [
            {"description": "", "reasons": {"2330": "相同理由"}},
            {"description": "", "reasons": {"2330": "不同理由"}},
        ],
    })

    result = fill.build_fill_payload(sectors, work, skipped_rollup_members=skipped, llm=llm)

    assert llm.calls == ["sector_a", "sector_b", "sector_b"]
    assert result.flagged_pairs == []
    assert result.payload["actor"] == "bot:reasons-fill"
    assert result.payload["full"] is False
    sector_b = next(s for s in result.payload["sectors"] if s["exposure_id"] == "sector_b")
    assert sector_b["members"] == [{**_member("2330", name="台積電"), "reason": "不同理由"}]


def test_description_only_payload_omits_members():
    sectors = [_sector("sector_desc", [_member("1001", "already")], description="")]
    work, skipped = fill.detect_work(sectors)
    llm = FakeLLM({"sector_desc": [{"description": "新描述", "reasons": {}}]})

    result = fill.build_fill_payload(sectors, work, skipped_rollup_members=skipped, llm=llm)

    assert result.descriptions_filled == 1
    assert result.payload["sectors"] == [{"exposure_id": "sector_desc", "description": "新描述"}]


def test_fetch_and_post_use_admin_api_shape():
    session = FakeHTTPSession()

    sectors = fill.fetch_taxonomy(session, "https://api.example", "token")
    draft = fill.post_bulk_draft(session, "https://api.example", "token", {"sectors": []})

    assert sectors[0]["exposure_id"] == "sector_a"
    assert draft["draft_id"] == 7
    assert session.posts[0]["url"] == "https://api.example/api/admin/taxonomy/bulk"
    assert session.posts[0]["headers"]["Authorization"] == "Bearer token"
