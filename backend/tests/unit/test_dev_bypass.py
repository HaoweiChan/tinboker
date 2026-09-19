"""The dev bypass: who it signs in, what its tokens are worth, and where they are refused.

dev, staging and production verify JWTs with one shared secret. Before this, a token from
the dev bypass — which signs in as the first admin — was a valid PRODUCTION admin session.
"""
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt

from src.config import settings
from src.models.user import UserResponse
from src.routers import auth as auth_router
from src.utils.auth import create_jwt_token, verify_jwt_token


def _user(google_id: str, email: str, name: str = "x", **_) -> UserResponse:
    now = datetime.now(timezone.utc)
    return UserResponse(id=f"id-{google_id}", google_id=google_id, email=email, name=name,
                        email_verified=True, created_at=now, updated_at=now)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "dev_bypass_token", "s3cret")
    monkeypatch.setattr(settings, "admin_emails", ["boss@tinboker.com"])
    monkeypatch.setattr(settings, "jwt_secret_key", "test-signing-key")
    users: dict[str, UserResponse] = {}

    def get_or_create(**kw):
        users[kw["email"]] = _user(**kw)
        return users[kw["email"]]
    monkeypatch.setattr(auth_router, "get_or_create_user", get_or_create)
    monkeypatch.setattr(auth_router, "get_user_by_email", lambda email: users.get(email))
    app = FastAPI()
    app.include_router(auth_router.router)
    return TestClient(app)


def _claims(token: str) -> dict:
    return jwt.decode(token, "test-signing-key", algorithms=[settings.jwt_algorithm])


def _is_admin(client, token):
    return client.get("/api/auth/is-admin", headers={"Authorization": f"Bearer {token}"}).json()


def test_viewer_gets_past_the_gate_but_is_not_an_admin(client):
    body = client.post("/api/auth/dev-token", json={"token": "s3cret", "role": "viewer"}).json()
    assert body["user"]["email"] == "qa-viewer@tinboker.com"
    assert {k: _claims(body["token"])[k] for k in ("dev_bypass", "role", "type")} == \
        {"dev_bypass": True, "role": "viewer", "type": "access"}
    assert _is_admin(client, body["token"]) == {"is_admin": False, "env_access": True}


def test_admin_stays_the_default_role(client):
    body = client.post("/api/auth/dev-token", json={"token": "s3cret"}).json()
    assert body["user"]["email"] == "boss@tinboker.com" and _claims(body["token"])["role"] == "admin"
    assert _is_admin(client, body["token"]) == {"is_admin": True, "env_access": True}


def test_bad_secret_bad_role_and_production_are_refused(client, monkeypatch):
    assert client.post("/api/auth/dev-token", json={"token": "nope"}).status_code == 401
    assert client.post("/api/auth/dev-token", json={"token": "s3cret", "role": "root"}).status_code == 422
    monkeypatch.setattr(settings, "environment", "production")
    assert client.post("/api/auth/dev-token", json={"token": "s3cret"}).status_code == 404


def test_production_refuses_a_bypass_token_but_not_a_real_one(client, monkeypatch):
    bypass = client.post("/api/auth/dev-token", json={"token": "s3cret"}).json()
    real = create_jwt_token("u1", "boss@tinboker.com")
    assert verify_jwt_token(bypass["token"]) and verify_jwt_token(real)

    monkeypatch.setattr(settings, "environment", "production")
    assert verify_jwt_token(bypass["token"]) is None
    assert verify_jwt_token(bypass["refresh_token"], expected_type="refresh") is None
    assert verify_jwt_token(real)["email"] == "boss@tinboker.com"
    assert _is_admin(client, bypass["token"]) == {"is_admin": False, "env_access": False}


def test_a_refresh_cannot_launder_a_bypass_session(client):
    first = client.post("/api/auth/dev-token", json={"token": "s3cret", "role": "viewer"}).json()
    again = client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]}).json()
    for tok in (again["token"], again["refresh_token"]):
        assert _claims(tok)["dev_bypass"] is True and _claims(tok)["role"] == "viewer"


def test_extra_claims_cannot_override_the_reserved_ones(client):
    claims = _claims(create_jwt_token("u1", "a@b.c", extra={"sub": "evil", "type": "refresh", "email": "x@y.z",
                                                          "dev_bypass": True, "anything": 1}))
    assert (claims["sub"], claims["type"], claims["email"]) == ("u1", "access", "a@b.c")
    assert claims["dev_bypass"] is True and "anything" not in claims
