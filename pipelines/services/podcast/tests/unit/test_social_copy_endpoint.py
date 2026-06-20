"""On-demand social-copy endpoint: POST /api/podcast/episodes/{id}/social-copy.

The platform admin Social page proxies here to (re)generate social copy for an
existing episode. These tests lock the Firestore-doc → pipeline-state mapping, the
empty-generation guard, and the API-key gate. The LLM + Firestore are stubbed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.podcast.content_builder.nodes import social_copy_writer as scw
from src.routers import podcast as podcast_router
from src.service import firestore_service as fs_mod

_DOC = {
    "episode_id": "ep1",
    "podcast_name": "Gooaye 股癌",
    "episode_title": "EP671",
    "summary_content": "# 標題\n\n孟恭談市場。",
    "social_cards": [
        {"kind": "cover", "title": "封面"},
        {"kind": "theme", "title": "市場百花齊放", "bullets": ["被動元件"]},
    ],
    "key_insights": ["資金回流台積電"],
}


class _FakeFirestore:
    def __init__(self, doc):
        self._doc = doc

    def get_document(self, collection, doc_id):
        assert collection == "episodes"
        return self._doc


@pytest.fixture
def client(monkeypatch):
    """A TestClient over an app mounting only the podcast router.

    Clears PODCAST_API_KEY so verify_api_key runs in dev mode (any non-empty key
    accepted, missing key rejected) — keeps the auth assertions deterministic.
    """
    monkeypatch.delenv("PODCAST_API_KEY", raising=False)
    app = FastAPI()
    app.include_router(podcast_router.router)
    return TestClient(app)


def _stub_firestore(monkeypatch, doc):
    monkeypatch.setattr(fs_mod, "FirestoreService", lambda: _FakeFirestore(doc))


def _stub_gcs(monkeypatch, text=None, error=None):
    import src.service.gcs_storage_service as gcs_mod

    class _FakeGCS:
        def download_text_by_gcs_url(self, url, encoding="utf-8"):
            if error is not None:
                raise error
            return text

    monkeypatch.setattr(gcs_mod, "GCSStorageService", _FakeGCS)


def test_load_summary_prefers_inline(monkeypatch):
    # Inline summary present → used as-is; GCS must not be touched.
    import src.service.gcs_storage_service as gcs_mod

    class _BoomGCS:
        def download_text_by_gcs_url(self, *a, **k):
            raise AssertionError("GCS should not be read when inline summary exists")

    monkeypatch.setattr(gcs_mod, "GCSStorageService", _BoomGCS)
    assert podcast_router._load_summary(_DOC, "ep1") == "# 標題\n\n孟恭談市場。"


def test_load_summary_reads_gcs_when_inline_empty(monkeypatch):
    # Published episodes keep the sectioned summary in GCS, inline field empty.
    doc = {**_DOC, "summary_content": "", "summary_url": "gs://b/ep1/summary.md"}
    _stub_gcs(monkeypatch, text="# 標題\n\n## 段落A\n\n內容A\n\n## 段落B\n\n內容B\n")
    out = podcast_router._load_summary(doc, "ep1")
    assert "## 段落A" in out and "內容B" in out


def test_load_summary_degrades_to_empty_on_gcs_error(monkeypatch):
    doc = {**_DOC, "summary_content": "", "summary_url": "gs://b/ep1/summary.md"}
    _stub_gcs(monkeypatch, error=RuntimeError("gcs down"))
    assert podcast_router._load_summary(doc, "ep1") == ""


def test_load_summary_empty_when_no_inline_and_no_url():
    assert podcast_router._load_summary({**_DOC, "summary_content": "", "summary_url": None}, "ep1") == ""


def test_generate_helper_maps_doc_fields_to_state(monkeypatch):
    _stub_firestore(monkeypatch, _DOC)
    captured = {}

    def fake_write(state):
        captured["state"] = state
        return {"social_thread": {"post": "P", "comments": [{"heading": "h", "text": "t"}]}}

    monkeypatch.setattr(scw, "write_social_copy", fake_write)

    thread = podcast_router._generate_social_copy("ep1")

    state = captured["state"]
    assert state["source"] == "Gooaye 股癌"          # podcast_name -> source
    assert state["episode_title"] == "EP671"
    assert state["markdown_report"] == _DOC["summary_content"]  # summary steer
    assert state["social_cards"] == _DOC["social_cards"]
    assert thread["post"] == "P"


def test_endpoint_returns_filtered_copy(client, monkeypatch):
    _stub_firestore(monkeypatch, _DOC)
    monkeypatch.setattr(scw, "write_social_copy", lambda state: {
        "social_thread": {
            "post": "  整集重點 👇  ",
            "comments": [
                {"heading": "市場百花齊放", "text": "題材輪動很快"},
                {"heading": "空的", "text": ""},  # dropped
            ],
        }
    })

    resp = client.post("/api/podcast/episodes/ep1/social-copy", headers={"X-API-Key": "k"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["episode_id"] == "ep1"
    assert body["post"] == "整集重點 👇"  # stripped
    assert [c["text"] for c in body["comments"]] == ["題材輪動很快"]


def test_endpoint_404_when_episode_missing(client, monkeypatch):
    _stub_firestore(monkeypatch, None)
    monkeypatch.setattr(scw, "write_social_copy", lambda state: {"social_thread": {}})

    resp = client.post("/api/podcast/episodes/nope/social-copy", headers={"X-API-Key": "k"})
    assert resp.status_code == 404


def test_endpoint_502_when_generation_empty(client, monkeypatch):
    _stub_firestore(monkeypatch, _DOC)
    monkeypatch.setattr(scw, "write_social_copy", lambda state: {
        "social_thread": {"post": "  ", "comments": [{"heading": "x", "text": ""}]}
    })

    resp = client.post("/api/podcast/episodes/ep1/social-copy", headers={"X-API-Key": "k"})
    assert resp.status_code == 502


def test_endpoint_401_without_api_key(client):
    resp = client.post("/api/podcast/episodes/ep1/social-copy")
    assert resp.status_code == 401
