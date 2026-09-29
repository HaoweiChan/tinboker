"""Fail-closed source contracts and the approved weekly card layout."""
from copy import deepcopy
from unittest.mock import patch

import pytest
from podcast import weekly_editorial as weekly


def material():
    return {"week": "2026-W38", "start": "2026-09-14", "end": "2026-09-20",
            "episodes": [{"episode_id": f"episode_{i}", "podcast_name": "財報狗", "title": "本週節目", "date": "2026-09-17", "summary": "部分算力服務漲價，大客戶合約尚未調價。" * 10} for i in range(3)]}


def candidate():
    return {"post": "部分算力服務調價，並不代表所有客戶一起調價。" * 14,
            "cards": [{"title": f"算力合約需要分開看{i}", "claims": [
                {"heading": "隨用隨付價格", "body": "部分算力服務已經調高價格，但不是全部合約一起調價。", "episode_id": f"episode_{i}", "quote": "部分算力服務漲價，大客戶合約尚未調價。"},
                {"heading": "大客戶合約", "body": "大客戶合約尚未同步調高價格，不能一概而論。", "episode_id": f"episode_{i}", "quote": "部分算力服務漲價，大客戶合約尚未調價。"}],
                "viewpoint": {"heading": "漲价範圍決定受惠程度", "body": "部分服務漲價、大客戶合約未動，不能把局部服務的漲幅套到整家公司收入。", "episode_ids": [f"episode_{i}"]}} for i in range(3)]}


def approved_review():
    return {"approved": True, "issues": [], "checks": [
        {"path": path, "supported": True, "reason": "原文保留調价範圍與合約條件，並未推定新事實。",
         "evidence": [{"episode_id": "episode_0", "quote": "部分算力服務漲價，大客戶合約尚未調價。"}]}
        for path in sorted(weekly.REVIEW_PATHS)]}


@pytest.mark.parametrize("change", [
    lambda m: m["episodes"][0].update(date=None),
    lambda m: m["episodes"].append(None),
    lambda m: m.update(start="2026-09-15"),
    lambda m: m["episodes"][0].update(date="2026-09-21"),
    lambda m: m["episodes"][0].update(episode_id="../escape"),
    lambda m: m["episodes"][0].update(summary="too short"),
    lambda m: m["episodes"][0].update(episode_id="episode_1"),
])
def test_source_validation_runs_before_model(change, tmp_path):
    source = material()
    change(source)
    with patch.object(weekly, "invoke_json") as call, pytest.raises(ValueError):
        weekly.generate_editorial(source, tmp_path)
    call.assert_not_called()


@pytest.mark.parametrize("change", [
    lambda d: d["cards"][0]["claims"][0].update(episode_id="invented"),
    lambda d: d["cards"][0]["claims"][0].update(quote="沒有出現在任何來源的完整一句話。"),
    lambda d: d["cards"][0].update(viewpoint={}),
    lambda d: d["cards"][0]["viewpoint"].update(episode_ids=["episode_1"]),
    lambda d: d["cards"][0]["viewpoint"].update(body="市場變化還需持續關注，未來應保持彈性並觀察各公司的交付能力。"),
])
def test_unfounded_output_fails_closed(change):
    draft = candidate()
    change(draft)
    with pytest.raises(ValueError):
        weekly.validate_editorial(draft, material())


def test_review_rejection_and_cache_prevent_extra_spend(tmp_path):
    with patch.object(weekly, "_model_name", return_value="test"), patch.object(weekly, "invoke_json", side_effect=[candidate(), {"approved": False, "issues": ["claims duplicate"]}, candidate()]) as call:
        for _ in range(2):
            with pytest.raises(ValueError, match="review failed"):
                weekly.generate_editorial(material(), tmp_path)
        assert call.call_count == 3


def test_deck_has_three_source_and_viewpoint_panels():
    draft = deepcopy(candidate())
    markdown, css = weekly.build_deck(draft, material())
    assert '週報 W38｜09/14–09/20' in markdown
    assert markdown.count('聽播客觀點') == 3
    assert markdown.count('綜合節目內容') == 3
    assert markdown.count('財報狗 09/17') == 6
    assert markdown.count('_class: focus-list') == 3
    assert '1080px 1080px' in css and 'overflow:visible' in css


def test_one_repair_only_and_all_calls_cached(tmp_path):
    oversized = candidate()
    oversized["post"] *= 3
    with patch.object(weekly, "_model_name", return_value="test"), patch.object(weekly, "invoke_json", side_effect=[oversized, candidate(), approved_review()]) as call:
        for _ in range(2):
            assert weekly.generate_editorial(material(), tmp_path)["review"]["approved"]
        assert call.call_count == 3


def test_repair_still_invalid_does_not_review(tmp_path):
    oversized = candidate()
    oversized["cards"][0]["claims"][0]["body"] *= 5
    with patch.object(weekly, "_model_name", return_value="test"), patch.object(weekly, "invoke_json", return_value=oversized) as call:
        with pytest.raises(ValueError):
            weekly.generate_editorial(material(), tmp_path)
        assert call.call_count == 2


def test_quote_matches_visible_markdown_without_losing_prose():
    source = material()
    for ep in source["episodes"]:
        ep["summary"] = ep["summary"].replace("算力", "[算力](#ticker:NVDA)")
    assert weekly.validate_editorial(candidate(), source)["cards"]
    bad = candidate()
    bad["cards"][0]["claims"][0]["quote"] = "部分算力服務沒有漲價，大客戶合約尚未調價。"
    with pytest.raises(ValueError, match="evidence"):
        weekly.validate_editorial(bad, source)


def test_editorial_model_prefers_explicit_weekly_then_social(monkeypatch):
    monkeypatch.setattr(weekly, "_LLM_OVERRIDES", {})
    monkeypatch.delenv("WEEKLY_COPY_WRITER_MODEL", raising=False)
    assert weekly.editorial_role() == "social_copy_writer"
    monkeypatch.setenv("WEEKLY_COPY_WRITER_MODEL", "weekly-specific")
    assert weekly.editorial_role() == "weekly_copy_writer"
    monkeypatch.delenv("WEEKLY_COPY_WRITER_MODEL")
    monkeypatch.setattr(weekly, "_LLM_OVERRIDES", {"weekly_copy_writer_model": "db-specific"})
    assert weekly.editorial_role() == "weekly_copy_writer"


def test_semantic_repair_requires_new_review_and_is_bounded(tmp_path):
    corrected = candidate()
    corrected["post"] = corrected["post"].replace("所有客戶", "每個客戶")
    rejected = {"approved": False, "issues": ["cards[0].viewpoint.heading: conditional turned factual"]}
    with patch.object(weekly, "_model_name", return_value="test"), patch.object(weekly, "invoke_json", side_effect=[candidate(), rejected, corrected, approved_review()]) as call:
        assert weekly.generate_editorial(material(), tmp_path)["post"] == corrected["post"]
        assert call.call_count == 4


def test_structural_repair_uses_up_only_repair_slot(tmp_path):
    oversized = candidate()
    oversized["post"] *= 2
    with patch.object(weekly, "_model_name", return_value="test"), patch.object(weekly, "invoke_json", side_effect=[oversized, candidate(), {"approved": False, "issues": ["conditional turned factual"]}]) as call:
        with pytest.raises(ValueError, match="conditional turned factual"):
            weekly.generate_editorial(material(), tmp_path)
        assert call.call_count == 3


@pytest.mark.parametrize("images", [[], ["invalid"] * 3])
def test_render_failure_never_returns_publishable_images(images):
    from types import SimpleNamespace
    with patch.dict("sys.modules", {"src.pipeline.steps.social_cards_render": SimpleNamespace(_render_png=lambda *args: images)}):
        with pytest.raises(ValueError):
            weekly.render_editorial(candidate(), material())


@pytest.mark.parametrize("change", [
    lambda review: review.pop("checks"),
    lambda review: review["checks"].pop(),
    lambda review: review["checks"][0].update(supported=False),
    lambda review: review["checks"][0].update(path="unknown"),
    lambda review: review["checks"][0].update(reason="supported"),
    lambda review: review["checks"][0].update(evidence=[]),
    lambda review: review["checks"][0]["evidence"][0].update(quote="來源沒有的價格推論以及鎖定合約的說法。"),
])
def test_blanket_approval_cannot_override_field_checks(change):
    verdict = approved_review()
    assert weekly.review_passed(verdict, material())
    change(verdict)
    assert not weekly.review_passed(verdict, material())


def test_concise_post_floor_does_not_require_padding():
    draft = candidate()
    draft['post'] = '具體事實' * 45
    assert len(weekly.validate_editorial(draft, material())['post']) == 180
    draft['post'] = draft['post'][:-1]
    with pytest.raises(ValueError, match='post'):
        weekly.validate_editorial(draft, material())
