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
