"""Post-hoc Threads copy: the story of one episode's take on one stock, clock stopped on
air date. The LLM is stubbed; what these lock is the material → prompt wiring and the
endpoint's doc → material mapping."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.podcast import post_hoc_copy as phc
from src.routers import podcast as podcast_router
from src.service import firestore_service as fs_mod

_SUMMARY = (
    "# 九月行情\n\n開場。\n\n"
    "## 作帳行情 (#time:2324093)\n\n散熱族群齊漲，[奇鋐](#ticker:3017)創高，[雙鴻](#ticker:3324)也放量上攻。\n\n"
    "## 光通訊\n\n[聯亞](#ticker:3081)最強。\n\n"
    "## 結論\n\n雙鴻這種落後補漲要看領頭羊。"
)


def test_sections_about_matches_anchor_or_name_and_strips_markup():
    secs = phc.sections_about(_SUMMARY, "3324", "雙鴻")
    assert [s["heading"] for s in secs] == ["作帳行情", "結論"]     # anchor hit, then name hit
    assert "[奇鋐](#ticker:3017)" not in secs[0]["body"] and "奇鋐創高" in secs[0]["body"]
    assert phc.sections_about(_SUMMARY, "2330", "台積電") == []


def test_speaker_fallback_is_a_nickname_or_the_cjk_run_and_a_passed_name_wins():
    assert phc.speaker_for("Gooaye 股癌") == "孟恭"
    assert phc.speaker_for("游庭皓的財經皓角") == "皓哥"
    assert phc.speaker_for("Some 韭菜畢業班 Show") == "韭菜畢業班"
    assert phc.speaker_for("") == "他"
    user = phc.build_messages({"ticker": "3324", "source": "兆華與股惑仔", "speaker": "兆華", "summary": ""})[1]["content"]
    assert "講話的人（全篇這樣叫他）：兆華" in user


def test_build_messages_carries_the_stance_thesis_and_only_that_stocks_sections():
    msgs = phc.build_messages({
        "source": "兆華與股惑仔", "episode_title": "EP1173", "ticker": "3324", "name": "雙鴻",
        "mention_date": "2026-08-31", "sentiment_label": "STRONG_BULLISH", "speaker": "兆華",
        "thesis": "雙鴻跟上奇鋐建準。", "reasons": [{"title": "比價", "description": "族群擴散"}],
        "risks": [], "summary": _SUMMARY,
    })
    system, user = msgs[0]["content"], msgs[1]["content"]
    assert "時間停在節目播出那天" in system and "不要評斷" in system and "不准寫「主持人」" in system
    assert "講話的人（全篇這樣叫他）：兆華" in user and "那天他對它的立場：看多" in user
    assert "雙鴻跟上奇鋐建準。" in user and "- 比價 族群擴散" in user and "（無）" in user  # risks empty
    assert "作帳行情" in user and "完整摘要" in user
    assert "光通訊" not in user.split("完整摘要")[0]
    assert "只能靠上面的結論" not in user


def test_mode_picks_the_closing_paragraph():
    base = {"ticker": "3324", "name": "雙鴻", "source": "兆華與股惑仔", "speaker": "兆華", "summary": _SUMMARY}
    past = phc.build_messages(base)[1]["content"]
    today = phc.build_messages({**base, "mode": "today"})[1]["content"]
    assert past.rstrip().endswith("不要評斷對錯。") and "用過去式" in past and "今天播出" not in past
    assert "這集是今天播出的" in today and "兆華這集講到雙鴻" in today and "不要留半句給系統補" in today
    assert "用過去式，不要寫之後的事" not in today


def test_build_messages_says_so_when_the_summary_never_names_the_stock():
    user = phc.build_messages({"ticker": "2330", "name": "台積電", "summary": _SUMMARY})[1]["content"]
    assert "沒有單獨講到這檔" in user and "沒有明確方向" in user


def test_postprocess_takes_the_post_and_tolerates_junk():
    assert phc.postprocess({"post": "  那天他講的是  "}) == {"post": "那天他講的是"}
    assert phc.postprocess("nonsense") == {"post": ""}


# ── endpoint ─────────────────────────────────────────────────────────────────

_DOC = {"episode_id": "ep1", "podcast_name": "兆華與股惑仔", "episode_title": "EP1173", "summary_content": _SUMMARY}


class _FakeFirestore:
    def get_document(self, collection, doc_id):
        return _DOC if doc_id == "ep1" else None


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("PODCAST_API_KEY", raising=False)
    monkeypatch.setattr(fs_mod, "FirestoreService", lambda: _FakeFirestore())
    app = FastAPI()
    app.include_router(podcast_router.router)
    return TestClient(app)


def test_endpoint_builds_material_from_the_doc_and_returns_the_story(client, monkeypatch):
    seen = {}

    def fake_write(material):
        seen.update(material)
        return {"post": "那天他講雙鴻"}
    monkeypatch.setattr(phc, "write_post_hoc_copy", fake_write)
    monkeypatch.setattr(podcast_router, "_ticker_insight", lambda *_: None)

    r = client.post("/api/podcast/episodes/ep1/post-hoc-copy", headers={"X-API-Key": "k"},
                    json={"ticker": "3324", "name": "雙鴻", "mention_date": "2026-08-31",
                          "sentiment_label": "BULLISH", "thesis": "跟上奇鋐", "speaker": "兆華"})
    assert r.status_code == 200 and r.json() == {"episode_id": "ep1", "ticker": "3324", "post": "那天他講雙鴻"}
    assert seen["source"] == "兆華與股惑仔" and seen["summary"] == _SUMMARY and seen["thesis"] == "跟上奇鋐"
    assert seen["speaker"] == "兆華"


def test_endpoint_404s_unknown_episode_and_502s_an_empty_story(client, monkeypatch):
    monkeypatch.setattr(podcast_router, "_ticker_insight", lambda *_: None)
    body = {"ticker": "3324"}
    assert client.post("/api/podcast/episodes/nope/post-hoc-copy", headers={"X-API-Key": "k"}, json=body).status_code == 404
    monkeypatch.setattr(phc, "write_post_hoc_copy", lambda m: {"post": ""})
    assert client.post("/api/podcast/episodes/ep1/post-hoc-copy", headers={"X-API-Key": "k"}, json=body).status_code == 502


def test_endpoint_requires_the_api_key(client):
    assert client.post("/api/podcast/episodes/ep1/post-hoc-copy", json={"ticker": "3324"}).status_code in (401, 403)


# triage: invariant-gap — generated text needs explicit source-grounded stance evidence.
def test_post_hoc_rejects_legacy_result_without_stance(monkeypatch):
    monkeypatch.setattr(phc, "invoke_json", lambda *_: {"post": "Arm 短期承壓"})
    assert phc.write_post_hoc_copy({"ticker": "ARM", "name": "Arm", "sentiment_label": "BULLISH",
                                   "summary": "## Arm\nArm 盤後下跌，短期承壓。"}) == {"post": ""}

_MATERIAL = {"ticker": "ARM", "name": "Arm", "sentiment_label": "BULLISH",
             "summary": "## Arm\nArm 未來需求將帶動股價上漲。"}
_VERIFIED = {"post": "兆華當時看好 Arm 未來需求", "source_stance": "bullish", "post_stance": "bullish",
             "supporting_quote": "Arm 未來需求將帶動股價上漲。", "has_conflicting_evidence": False}


@pytest.mark.parametrize("patch", [
    {"source_stance": "bearish"}, {"source_stance": "unclear"}, {"post_stance": "bearish"},
    {"has_conflicting_evidence": True}, {"supporting_quote": "這句話並未出現在原始摘要裡。"},
    {"supporting_quote": "Arm"}, {"supporting_quote": None},
])
def test_post_hoc_rejects_unfaithful_or_unsupported_story(monkeypatch, patch):
    monkeypatch.setattr(phc, "invoke_json", lambda *_: {**_VERIFIED, **patch})
    assert phc.write_post_hoc_copy(_MATERIAL) == {"post": ""}


def test_post_hoc_accepts_verified_stance_in_one_call_without_price_leak(monkeypatch):
    calls = []
    def invoke(role, messages):
        calls.append(messages)
        return _VERIFIED
    monkeypatch.setattr(phc, "invoke_json", invoke)
    assert phc.write_post_hoc_copy({**_MATERIAL, "pct": 39.4}) == {"post": _VERIFIED["post"]}
    assert len(calls) == 1 and "39.4" not in str(calls)


@pytest.mark.parametrize("patch", [
    {"summary": ""}, {"summary": "## Other\n其他股票看多"}, {"sentiment_label": "NOT_BULLISH"},
    {"summary": "## Arm\nArm" + "x" * phc.MAX_EVIDENCE_CHARS},
])
def test_post_hoc_missing_or_oversized_evidence_skips_model(monkeypatch, patch):
    def unexpected(*_):
        pytest.fail("Incomplete evidence must not incur a model call")
    monkeypatch.setattr(phc, "invoke_json", unexpected)
    assert phc.write_post_hoc_copy({**_MATERIAL, **patch}) == {"post": ""}


def test_all_matching_sections_and_late_reversal_reach_model(monkeypatch):
    summary = "\n\n".join(f"## Part {i}\nArm " + "前文" * 650 for i in range(4))
    summary += "\n\n## 最終判斷\nArm 最後仍看空。"
    seen = []
    def invoke(role, messages):
        seen.append(messages)
        return {**_VERIFIED, "source_stance": "bearish"}
    monkeypatch.setattr(phc, "invoke_json", invoke)
    assert phc.write_post_hoc_copy({**_MATERIAL, "summary": summary}) == {"post": ""}
    assert "Arm 最後仍看空。" in seen[0][1]["content"]
    assert len(phc.sections_about(summary, "ARM", "Arm")) == 5


def test_today_keeps_legacy_post_only_response(monkeypatch):
    monkeypatch.setattr(phc, "invoke_json", lambda *_: {"post": "今天觀察 Arm"})
    assert phc.write_post_hoc_copy({"ticker": "ARM", "mode": "today"}) == {"post": "今天觀察 Arm"}



def test_full_summary_includes_late_pronoun_reversal(monkeypatch):
    reversal = "不過這家公司估值過高，未來股價反而會跌。"
    material = {**_MATERIAL, "summary": _MATERIAL["summary"] + "\n\n## 最後結論\n" + reversal}
    calls = []
    def invoke(role, messages):
        calls.append(messages)
        return {**_VERIFIED, "source_stance": "unclear", "has_conflicting_evidence": True}
    monkeypatch.setattr(phc, "invoke_json", invoke)
    assert phc.write_post_hoc_copy(material) == {"post": ""}
    assert reversal in calls[0][1]["content"]


def test_full_summary_over_cap_skips_model_even_with_short_target_section(monkeypatch):
    def unexpected(*_):
        pytest.fail("Do not silently omit other sections when context exceeds the cap")
    monkeypatch.setattr(phc, "invoke_json", unexpected)
    material = {**_MATERIAL, "summary": _MATERIAL["summary"] + "\n\n## 其他\n" + "x" * phc.MAX_EVIDENCE_CHARS}
    assert phc.write_post_hoc_copy(material) == {"post": ""}


def test_today_keeps_bounded_sections_without_full_summary():
    summary = "\n\n".join(f"## Part {i}\nArm " + "x" * 1300 for i in range(4))
    user = phc.build_messages({**_MATERIAL, "summary": summary, "mode": "today"})[1]["content"]
    assert "Part 2" in user and "Part 3" not in user and "x" * 1201 not in user


def test_prompt_requires_independent_source_and_prose_assessment():
    system = phc.build_messages(_MATERIAL)[0]["content"]
    assert "報導過去漲跌不等於看多或看空" in system
    assert "post_stance 表示成文實際傳達的最終方向" in system
    assert "不能摘要看多卻以短期承壓作結" in system
