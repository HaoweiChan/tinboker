"""The ingest hook requires content-write access and purges stale episode responses."""

import threading
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.auth import admin_auth
from src.routers import admin_mentions


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(admin_auth.settings, "tinboker_write_token", "test-write-token")
    monkeypatch.setattr(admin_auth.settings, "admin_emails", ["admin@example.com"])
    monkeypatch.setattr("src.utils.auth.verify_jwt_token", lambda token: {
        "admin-jwt": {"email": "admin@example.com"},
        "viewer-jwt": {"email": "viewer@example.com"},
    }.get(token))
    app = FastAPI()
    app.include_router(admin_mentions.router)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sync_mock(monkeypatch):
    sync = Mock(return_value={"ticker_mentions": 2, "sector_mentions": 1})
    monkeypatch.setattr(admin_mentions.mention_sync, "sync_episode_mentions", sync)
    monkeypatch.setattr(admin_mentions, "purge_cdn_cache", AsyncMock(return_value=True))
    return sync


@pytest.mark.parametrize("token", [None, "bad-token", "viewer-jwt"])
def test_sync_rejects_unauthorized(client, sync_mock, token):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = client.post("/api/admin/episodes/ep1/sync-mentions", headers=headers)
    assert response.status_code in (401, 403)
    sync_mock.assert_not_called()


@pytest.mark.parametrize("token", ["test-write-token", "admin-jwt"])
def test_sync_accepts_content_writer_and_purges_all_environments(client, sync_mock, token):
    response = client.post(
        "/api/admin/episodes/ep1/sync-mentions", headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json() == {"episode_id": "ep1", "ticker_mentions": 2, "sector_mentions": 1}
    sync_mock.assert_called_once_with("ep1")
    admin_mentions.purge_cdn_cache.assert_awaited_once_with(urls=[
        f"https://{host}/api/episodes/ep1/{suffix}"
        for host in ("api.tinboker.com", "staging-api.tinboker.com", "dev-api.tinboker.com")
        for suffix in ("mentions", "cross-show")
    ])


def test_sync_missing_episode_is_404(client, sync_mock):
    sync_mock.side_effect = ValueError("Episode missing not found")
    response = client.post(
        "/api/admin/episodes/missing/sync-mentions",
        headers={"Authorization": "Bearer test-write-token"},
    )
    assert response.status_code == 404
    admin_mentions.purge_cdn_cache.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_runs_off_event_loop_and_survives_purge_failure(sync_mock):
    event_loop_thread = threading.get_ident()

    def sync(episode_id):
        assert threading.get_ident() != event_loop_thread
        return {"ticker_mentions": 2}

    sync_mock.side_effect = sync
    admin_mentions.purge_cdn_cache.side_effect = RuntimeError("CDN unavailable")
    assert await admin_mentions.sync_episode_mentions("ep1", admin=None) == {
        "episode_id": "ep1", "ticker_mentions": 2,
    }
