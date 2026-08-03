"""``GET /api/podcast/shows`` + ``/shows/{podcast_name}`` (P2 read-flip): both
read ``FirebaseService.get_all_podcast_shows``/``get_podcast_show``, which now
read ``firestore_mirror.podcasts`` instead of Firestore (see
``src/service/upload_to_firebase.py``). These tests only lock the router's use
of that (already-mocked-whole) service — the mirror SQL itself is covered by
``test_postgres_mirror_reader.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.routers import podcast as podcast_router
from src.service import upload_to_firebase as fb_mod


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("PODCAST_API_KEY", raising=False)
    app = FastAPI()
    app.include_router(podcast_router.router)
    return TestClient(app)


def _stub_firebase(monkeypatch, instance):
    monkeypatch.setattr(fb_mod, "FirebaseService", lambda: instance)


def test_list_shows_returns_mirror_backed_metadata(client, monkeypatch):
    fb = MagicMock()
    fb.get_all_podcast_shows.return_value = [
        {"podcast_name": "Gooaye 股癌", "publisher": "Gooaye", "id": "Gooaye_股癌"},
        {"podcast_name": "財經一路發", "publisher": "X", "id": "財經一路發"},
    ]
    _stub_firebase(monkeypatch, fb)

    resp = client.get("/api/podcast/shows", headers={"X-API-Key": "k"})

    assert resp.status_code == 200
    names = [s["podcast_name"] for s in resp.json()]
    assert names == ["Gooaye 股癌", "財經一路發"]


def test_get_show_returns_single_show(client, monkeypatch):
    fb = MagicMock()
    fb.get_podcast_show.return_value = {"podcast_name": "Gooaye 股癌", "language": "zh-TW"}
    _stub_firebase(monkeypatch, fb)

    resp = client.get("/api/podcast/shows/Gooaye%20股癌", headers={"X-API-Key": "k"})

    assert resp.status_code == 200
    assert resp.json()["language"] == "zh-TW"
    fb.get_podcast_show.assert_called_once_with("Gooaye 股癌")


def test_get_show_404_when_missing(client, monkeypatch):
    fb = MagicMock()
    fb.get_podcast_show.return_value = None
    _stub_firebase(monkeypatch, fb)

    resp = client.get("/api/podcast/shows/Nope", headers={"X-API-Key": "k"})

    assert resp.status_code == 404
