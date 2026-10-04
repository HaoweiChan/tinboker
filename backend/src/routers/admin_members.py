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
from pydantic import BaseModel, Field
from sqlalchemy import func

from src.auth.admin_auth import get_admin_access, AdminAccess
from src.cache.cdn_cache import cdn_cached, CacheProfile
from src.database.models import PromoCode, Subscription
from src.database.postgres import session_scope
from src.database.user_db import set_member_until, list_granted_members
from src.services.billing import PROMO_USED_STATUSES
from src.models.user import UserResponse

router = APIRouter(prefix="/api/admin/members", tags=["admin"])
promo_router = APIRouter(prefix="/api/admin/promo-codes", tags=["admin"])


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


class PromoCodeRequest(BaseModel):
    """`amount_off` is NT$/month; the list price or more makes the code a free grant."""
    amount_off: int = Field(gt=0)
    max_uses: int = Field(ge=0)
    active: bool = True


class PromoCodeSummary(PromoCodeRequest):
    code: str
    # The admin API only exists on dev/staging (sandbox gateway) while the codes are
    # shared with production through the one Postgres, so report both counts.
    used_production: int
    used_sandbox: int


def _promo_rows(code: Optional[str] = None) -> List[PromoCodeSummary]:
    with session_scope() as db:
        used = {(code, env): count for code, env, count in db.query(
            Subscription.promo_code, Subscription.gateway_env, func.count(Subscription.id)).filter(
            Subscription.status.in_(PROMO_USED_STATUSES)).group_by(Subscription.promo_code, Subscription.gateway_env)}
        query = db.query(PromoCode).order_by(PromoCode.created_at.desc())
        return [PromoCodeSummary(code=p.code, amount_off=p.amount_off, max_uses=p.max_uses, active=p.active,
                                 used_production=used.get((p.code, "production"), 0),
                                 used_sandbox=used.get((p.code, "sandbox"), 0))
                for p in (query.filter_by(code=code) if code else query)]


def _upsert_promo(code: str, req: PromoCodeRequest) -> PromoCodeSummary:
    with session_scope() as db:
        promo = db.get(PromoCode, code) or PromoCode(code=code)
        promo.amount_off, promo.max_uses, promo.active = req.amount_off, req.max_uses, req.active
        db.add(promo)
    return _promo_rows(code)[0]


@promo_router.put("/{code}", response_model=PromoCodeSummary)
async def upsert_promo_code(code: str, req: PromoCodeRequest, admin: AdminAccess = Depends(get_admin_access)):
    """Create or edit a shared code. `active: false` or a lower `max_uses` stops new
    redemptions; existing subscriptions keep their price."""
    code = code.strip().upper()
    if not code.isalnum() or len(code) > 32:
        raise HTTPException(status_code=422, detail="Code must be 1-32 letters or digits")
    return await asyncio.to_thread(_upsert_promo, code, req)


@promo_router.get("", response_model=List[PromoCodeSummary])
@cdn_cached(profile=CacheProfile.PRIVATE)
async def list_promo_codes(admin: AdminAccess = Depends(get_admin_access)):
    """Every code with its use counts on the production and sandbox gateways."""
    return await asyncio.to_thread(_promo_rows)
