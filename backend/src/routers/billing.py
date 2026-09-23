"""Membership plans, hosted NewebPay checkout and verified server callbacks."""
import asyncio

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from typing import Optional
from src.models.user import UserResponse
from src.utils.dependencies import get_current_user
from src.utils.auth import verify_jwt_token
from src.services import billing
from pydantic import BaseModel
from sqlalchemy import func

from src.cache.cdn_cache import cdn_cached
from src.config import settings
from src.database.models import Subscription
from src.database.postgres import session_scope

router = APIRouter(prefix="/api/billing", tags=["billing"])

class PlansResponse(BaseModel):
    list_price: int
    founding_price: int
    founding_limit: int
    founding_remaining: int
    founding_open: bool
    checkout_open: bool
    gateway_env: str


def _founding_taken() -> int:
    """Pending reserves a seat; paid/cancelled/ended mandates already spent one.
    Only a verified terminal first-auth failure releases its reservation."""
    with session_scope() as db:
        return int(
            db.query(func.count(Subscription.id))
            .filter(
                Subscription.is_founding.is_(True),
                Subscription.status.in_(["pending", "active", "cancelling", "cancelled", "ended"]),
                Subscription.gateway_env == settings.newebpay_env,
            )
            .scalar()
            or 0
        )


@router.get("/plans", response_model=PlansResponse)
@cdn_cached(s_maxage=60, max_age=0, stale=30)
async def get_plans():
    """Public, non-personalised plan info for the `/membership` page.

    CDN cache: 60s edge (short — founding-seat count changes as people subscribe).
    `founding_remaining` is advisory only (a 60s-cached, non-transactional count) —
    Checkout re-checks and reserves founding seats inside its transaction rather
    than trusting this cached advisory count.
    """
    taken = await asyncio.to_thread(_founding_taken)
    remaining = max(0, settings.membership_founding_limit - taken)
    return PlansResponse(
        list_price=settings.membership_list_price,
        founding_price=settings.membership_founding_price,
        founding_limit=settings.membership_founding_limit,
        founding_remaining=remaining,
        founding_open=remaining > 0,
        checkout_open=settings.newebpay_configured and settings.newebpay_checkout_enabled,
        gateway_env=settings.newebpay_env,
    )


def billing_user(user: UserResponse = Depends(get_current_user)) -> UserResponse:
    if not settings.is_production and user.email.lower() not in {e.lower() for e in settings.admin_emails}:
        raise HTTPException(403, "Sandbox billing requires an administrator")
    return user


def billing_writer(
    user: UserResponse = Depends(billing_user), authorization: Optional[str] = Header(None),
) -> UserResponse:
    payload = verify_jwt_token(authorization.split()[1], expected_type="access") if authorization else None
    if not payload:
        raise HTTPException(401, "Invalid or expired token")
    if payload.get("membership_preview_session"):
        raise HTTPException(403, "Sign out of membership preview and sign in again before changing billing")
    return user


@router.post("/checkout")
def start_checkout(response: Response, user: UserResponse = Depends(billing_writer)):
    response.headers["Cache-Control"] = "private, no-store"
    return billing.checkout(user.id, user.email)


@router.get("/subscription")
def get_subscription(response: Response, user: UserResponse = Depends(billing_user)):
    response.headers["Cache-Control"] = "private, no-store"
    return billing.subscription_status(user.id)


@router.post("/cancel")
def cancel(response: Response, user: UserResponse = Depends(billing_writer)):
    response.headers["Cache-Control"] = "private, no-store"
    return billing.cancel_subscription(user.id)


async def _notification(request: Request) -> dict:
    if len(await request.body()) > 65536:
        raise HTTPException(413, "Payment notification too large")
    form = await request.form()
    encrypted = form.get("Period")
    if not isinstance(encrypted, str) or not encrypted:
        raise HTTPException(400, "Missing encrypted payment notification")
    return await asyncio.to_thread(billing.process_notification, encrypted)


@router.post("/notify")
async def notify(request: Request):
    return await _notification(request)


@router.post("/return")
async def payment_return(request: Request):
    # ReturnURL is a gateway form POST. Verify it identically to NotifyURL; only
    # validated server state grants access, never a browser query-string status.
    await _notification(request)
    site, _ = billing.billing_urls()
    return RedirectResponse(f"{site}/membership?payment=return", status_code=303,
                            headers={"Cache-Control": "private, no-store"})
