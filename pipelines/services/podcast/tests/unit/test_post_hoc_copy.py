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


def test_speaker_is_a_nickname_a_short_show_name_or_the_cjk_run():
    assert phc.speaker_for("Gooaye 股癌") == "孟恭"
    assert phc.speaker_for("游庭皓的財經皓角") == "皓哥"
    assert phc.speaker_for("兆華與股惑仔") == "兆華"
    assert phc.speaker_for("財經一路發") == "一路發"
    assert phc.speaker_for("Some 韭菜畢業班 Show") == "韭菜畢業班"
    assert phc.speaker_for("") == "他"


def test_build_messages_carries_the_stance_thesis_and_only_that_stocks_sections():
    msgs = phc.build_messages({
        "source": "兆華與股惑仔", "episode_title": "EP1173", "ticker": "3324", "name": "雙鴻",
        "mention_date": "2026-08-31", "sentiment_label": "STRONG_BULLISH",
        "thesis": "雙鴻跟上奇鋐建準。", "reasons": [{"title": "比價", "description": "族群擴散"}],
        "risks": [], "summary": _SUMMARY,
    })
    system, user = msgs[0]["content"], msgs[1]["content"]
    assert "時間停在節目播出那天" in system and "不要評斷" in system and "不准寫「主持人」" in system
    assert "講話的人（全篇這樣叫他）：兆華" in user and "那天他對它的立場：看多" in user
    assert "雙鴻跟上奇鋐建準。" in user and "- 比價 族群擴散" in user and "（無）" in user  # risks empty
    assert "作帳行情" in user and "光通訊" not in user
    assert "只能靠上面的結論" not in user


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
                          "sentiment_label": "BULLISH", "thesis": "跟上奇鋐"})
    assert r.status_code == 200 and r.json() == {"episode_id": "ep1", "ticker": "3324", "post": "那天他講雙鴻"}
    assert seen["source"] == "兆華與股惑仔" and seen["summary"] == _SUMMARY and seen["thesis"] == "跟上奇鋐"


def test_endpoint_404s_unknown_episode_and_502s_an_empty_story(client, monkeypatch):
    monkeypatch.setattr(podcast_router, "_ticker_insight", lambda *_: None)
    body = {"ticker": "3324"}
    assert client.post("/api/podcast/episodes/nope/post-hoc-copy", headers={"X-API-Key": "k"}, json=body).status_code == 404
    monkeypatch.setattr(phc, "write_post_hoc_copy", lambda m: {"post": ""})
    assert client.post("/api/podcast/episodes/ep1/post-hoc-copy", headers={"X-API-Key": "k"}, json=body).status_code == 502


def test_endpoint_requires_the_api_key(client):
    assert client.post("/api/podcast/episodes/ep1/post-hoc-copy", json={"ticker": "3324"}).status_code in (401, 403)
