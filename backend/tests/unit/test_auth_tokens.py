"""Unit tests for JWT access/refresh token creation and verification."""
from datetime import datetime, timedelta, timezone

from jose import jwt

from src.config import settings
from src.utils.auth import create_jwt_token, create_refresh_token, verify_jwt_token


def _with_secret(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret_key", "test-secret-key")
    monkeypatch.setattr(settings, "jwt_algorithm", "HS256")


def test_access_token_carries_access_type(monkeypatch):
    _with_secret(monkeypatch)
    token = create_jwt_token("user-1", "a@b.com")

    payload = verify_jwt_token(token)
    assert payload is not None
    assert payload["type"] == "access"
    assert payload["email"] == "a@b.com"

    # Type enforcement: an access token must not pass as a refresh token.
    assert verify_jwt_token(token, expected_type="access") is not None
    assert verify_jwt_token(token, expected_type="refresh") is None


def test_refresh_token_round_trip(monkeypatch):
    _with_secret(monkeypatch)
    token = create_refresh_token("user-1", "a@b.com")

    assert verify_jwt_token(token, expected_type="refresh") is not None
    # A refresh token must not be usable as an access token.
    assert verify_jwt_token(token, expected_type="access") is None


def test_refresh_token_outlives_access_token(monkeypatch):
    _with_secret(monkeypatch)
    monkeypatch.setattr(settings, "jwt_expiration_hours", 24)
    monkeypatch.setattr(settings, "jwt_refresh_expiration_days", 60)

    access_exp = verify_jwt_token(create_jwt_token("u", "a@b.com"))["exp"]
    refresh_exp = verify_jwt_token(
        create_refresh_token("u", "a@b.com"), expected_type="refresh"
    )["exp"]
    assert refresh_exp > access_exp


def test_legacy_token_without_type_treated_as_access(monkeypatch):
    _with_secret(monkeypatch)
    # Tokens minted before the `type` claim existed must still authenticate.
    legacy = jwt.encode(
        {
            "sub": "user-1",
            "email": "a@b.com",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        "test-secret-key",
        algorithm="HS256",
    )
    assert verify_jwt_token(legacy, expected_type="access") is not None


def test_invalid_token_returns_none(monkeypatch):
    _with_secret(monkeypatch)
    assert verify_jwt_token("not-a-jwt") is None
    # Wrong signing key → invalid.
    bad = jwt.encode({"sub": "u", "email": "a@b.com"}, "other-secret", algorithm="HS256")
    assert verify_jwt_token(bad) is None
