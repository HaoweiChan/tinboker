"""Dev preview sessions do not alter persisted entitlements."""
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from jose import jwt

from src.config import settings
from src.models.user import UserResponse
from src.routers import auth
from src.utils import dependencies
from src.utils.auth import create_jwt_token, verify_jwt_token


@pytest.fixture
def preview(monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "admin_emails", ["admin@example.com"])
    monkeypatch.setattr(settings, "jwt_secret_key", "preview-test-secret")
    monkeypatch.setattr(settings, "jwt_expiration_hours", 24)
    monkeypatch.setattr(settings, "jwt_refresh_expiration_days", 60)
    now = datetime.now(timezone.utc)
    user = UserResponse(id="u1", google_id="g1", email="admin@example.com", name="Admin",
                        email_verified=True, created_at=now, updated_at=now,
                        member_until=now + timedelta(days=30))
    monkeypatch.setattr(auth, "get_user_by_email", lambda email: user)
    monkeypatch.setattr(dependencies, "get_user_by_email", lambda email: user)
    write = Mock(side_effect=AssertionError("Preview must not write users"))
    monkeypatch.setattr(auth, "get_or_create_user", write)
    app = FastAPI()
    app.include_router(auth.router)
    token = create_jwt_token(user.id, user.email, {"dev_bypass": True, "role": "admin"})
    return TestClient(app), user, token, write


def toggle(client, token, mode):
    return client.post("/api/auth/membership-preview", json={"mode": mode},
                       headers={"Authorization": f"Bearer {token}"})


def test_preview_me_member_gate_refresh_with_normal_lifetimes(preview):
    client, user, token, write = preview
    actual = user.member_until
    for mode in ("free", "paid"):
        response = toggle(client, token, mode)
        assert response.status_code == 200
        data = response.json()
        token = data["token"]
        assert data["user"]["membership_preview_available"] is True
        assert data["user"]["membership_preview"] == mode
        assert data["user"]["is_member"] is (mode != "free")
        assert user.member_until == actual and user.membership_preview is None
        payload = verify_jwt_token(token)
        assert "membership_preview_expires" not in payload
        assert 86395 <= payload["exp"] - datetime.now(timezone.utc).timestamp() <= 86400
        assert payload["dev_bypass"] is True and payload["role"] == "admin"
        current = dependencies.get_current_user(f"Bearer {token}")
        if mode == "free":
            assert current.member_until is None
            with pytest.raises(HTTPException) as exc:
                dependencies.require_member(current)
            assert exc.value.status_code == 402
        else:
            assert dependencies.require_member(current).is_member
        assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).json() == data["user"]
        refreshed = client.post("/api/auth/refresh", json={"refresh_token": data["refresh_token"]})
        assert refreshed.status_code == 200
        assert refreshed.json()["user"]["is_member"] == data["user"]["is_member"]
        assert refreshed.json()["user"]["membership_preview"] == mode
        for name in ("token", "refresh_token"):
            refreshed_payload = verify_jwt_token(refreshed.json()[name])
            assert "membership_preview_expires" not in refreshed_payload
            duration = 86400 if name == "token" else 60 * 86400
            assert duration - 5 <= refreshed_payload["exp"] - datetime.now(timezone.utc).timestamp() <= duration
    write.assert_not_called()


@pytest.mark.parametrize("environment", ["staging", "production", "test"])
@pytest.mark.parametrize("mode", ["free", "paid"])
def test_preview_never_crosses_environment(preview, monkeypatch, environment, mode):
    client, _, token, _ = preview
    data = toggle(client, token, mode).json()
    monkeypatch.setattr(settings, "environment", environment)
    for name in ("token", "refresh_token"):
        assert verify_jwt_token(data[name]) is None
    assert client.post("/api/auth/refresh", json={"refresh_token": data["refresh_token"]}).status_code == 401
    assert toggle(client, token, mode).status_code == 404


def test_anonymous_nonadmin_and_revoked_admin(preview, monkeypatch):
    client, user, token, _ = preview
    assert client.post("/api/auth/membership-preview", json={"mode": "paid"}).status_code == 401
    data = toggle(client, token, "paid").json()
    monkeypatch.setattr(settings, "admin_emails", [])
    assert user.membership_preview_available is False
    assert toggle(client, token, "paid").status_code == 403
    assert verify_jwt_token(data["token"]) is None
    assert client.post("/api/auth/refresh", json={"refresh_token": data["refresh_token"]}).status_code == 401


def test_paid_preview_of_free_user_and_validation(preview):
    client, user, token, _ = preview
    user.member_until = None
    assert toggle(client, token, "paid").json()["user"]["is_member"] is True
    assert user.member_until is None
    assert toggle(client, token, "original").status_code == 422
    assert toggle(client, token, "invalid").status_code == 422
    assert client.post("/api/auth/membership-preview", json={"mode": "paid", "member_until": "2099"},
                       headers={"Authorization": f"Bearer {token}"}).status_code == 422


def test_expired_preview_token_rejected(preview):
    client, _, token, _ = preview
    data = toggle(client, token, "paid").json()
    for name in ("token", "refresh_token"):
        payload = verify_jwt_token(data[name])
        payload["exp"] = int(datetime.now(timezone.utc).timestamp()) - 1
        expired = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
        assert verify_jwt_token(expired) is None
        if name == "refresh_token":
            assert client.post("/api/auth/refresh", json={"refresh_token": expired}).status_code == 401


def test_legacy_preview_refresh_drops_special_deadline(preview):
    client, _, token, _ = preview
    data = toggle(client, token, "paid").json()
    payload = verify_jwt_token(data["refresh_token"])
    payload["membership_preview_expires"] = int(datetime.now(timezone.utc).timestamp()) + 60
    payload["exp"] = payload["membership_preview_expires"]
    legacy = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    refreshed = client.post("/api/auth/refresh", json={"refresh_token": legacy})
    assert refreshed.status_code == 200
    data = refreshed.json()
    access = verify_jwt_token(data["token"])
    assert access["exp"] > payload["exp"]
    assert "membership_preview_expires" not in access
    assert datetime.fromisoformat(data["user"]["member_until"].replace("Z", "+00:00")).timestamp() == access["exp"]
