"""
Admin endpoint for manually granting/revoking paid membership.

PR 1 of the membership entitlement system — no billing exists yet (NewebPay lands
later), so this is the only way to make a user a member for now. Gated by the same
ADMIN_EMAILS allowlist as the other admin routers.
"""
import asyncio
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.auth.admin_auth import get_admin_access, AdminAccess
from src.cache.cdn_cache import cdn_cached, CacheProfile
from src.database.user_db import set_member_until, list_granted_members
from src.models.user import UserResponse

router = APIRouter(prefix="/api/admin/members", tags=["admin"])


class MemberGrantRequest(BaseModel):
    """Body for the manual grant/revoke endpoint. `member_until: null` revokes."""
    member_until: Optional[datetime] = None


class MemberSummary(BaseModel):
    email: str
    member_until: Optional[datetime]
    is_member: bool


def _summary(user: UserResponse) -> MemberSummary:
    return MemberSummary(email=user.email, member_until=user.member_until, is_member=user.is_member)


@router.put("/{email}", response_model=MemberSummary)
async def grant_membership(
    email: str,
    req: MemberGrantRequest,
    admin: AdminAccess = Depends(get_admin_access),
):
    """Set (or clear, with `member_until: null`) a user's membership expiry."""
    updated = await asyncio.to_thread(set_member_until, email, req.member_until)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return _summary(updated)


@router.get("", response_model=List[MemberSummary])
@cdn_cached(profile=CacheProfile.PRIVATE)
async def list_members(
    admin: AdminAccess = Depends(get_admin_access),
):
    """Every user with a membership grant (active or expired), newest expiry first.

    Explicitly marked CacheProfile.PRIVATE — Cloudflare caches every `GET /api/*` by
    URL with no Vary on Authorization, so an uncached-by-default admin endpoint would
    still risk one admin's response being served to another.
    """
    return [_summary(u) for u in await asyncio.to_thread(list_granted_members)]
