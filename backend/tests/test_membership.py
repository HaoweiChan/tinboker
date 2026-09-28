"""Unit tests for the membership entitlement layer (PR 1): `is_active_member`'s
naive/aware-safe comparison, and the `require_member` dependency's 402 split.

No DB or network — `require_member` is called directly with a stubbed
`UserResponse`, the same idiom other router tests use for a `Depends()` value.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from src.models.user import UserResponse, is_active_member
from src.utils.dependencies import require_member


def _user(member_until=None) -> UserResponse:
    now = datetime.now(timezone.utc)
    return UserResponse(
        id="u1",
        google_id="g1",
        email="a@b.com",
        name="Test User",
        email_verified=True,
        created_at=now,
        updated_at=now,
        member_until=member_until,
    )


def test_is_active_member_true_for_future():
    future = datetime.now(timezone.utc) + timedelta(days=1)
    assert is_active_member(future) is True


def test_is_active_member_false_for_past():
    past = datetime.now(timezone.utc) - timedelta(days=1)
    assert is_active_member(past) is False


def test_is_active_member_false_for_none():
    assert is_active_member(None) is False


def test_is_active_member_naive_datetime_treated_as_utc():
    # SQLite hands back naive datetimes even though we always write aware ones —
    # this must not raise a naive/aware TypeError, and must treat them as UTC.
    naive_future = datetime.utcnow() + timedelta(days=1)
    naive_past = datetime.utcnow() - timedelta(days=1)
    assert is_active_member(naive_future) is True
    assert is_active_member(naive_past) is False


def test_user_response_is_member_computed_field():
    future = datetime.now(timezone.utc) + timedelta(days=1)
    assert _user(member_until=future).is_member is True
    assert _user(member_until=None).is_member is False


def test_require_member_raises_402_for_non_member():
    with pytest.raises(HTTPException) as exc_info:
        require_member(user=_user(member_until=None))
    assert exc_info.value.status_code == 402


def test_require_member_returns_user_for_member():
    future = datetime.now(timezone.utc) + timedelta(days=1)
    member = _user(member_until=future)
    assert require_member(user=member) is member


def test_is_member_is_serialized_and_not_client_settable():
    # The frontend reads `is_member` off the payload, and it must only ever be derived.
    assert _user().model_dump()["is_member"] is False
    spoofed = UserResponse(**{**_user().model_dump(), "is_member": True, "member_until": None})
    assert spoofed.is_member is False
