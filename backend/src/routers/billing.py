"""Membership plans, hosted NewebPay checkout and verified server callbacks."""
import asyncio
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from typing import Optional
from src.models.user import UserResponse
from src.utils.dependencies import get_current_user
from src.utils.auth import verify_jwt_token
from src.services import billing
from pydantic import BaseModel, Field

from src.cache.cdn_cache import cdn_cached
from src.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])

class PlansResponse(BaseModel):
    list_price: int
    checkout_open: bool
    gateway_env: str


@router.get("/plans", response_model=PlansResponse)
@cdn_cached(s_maxage=60, max_age=0, stale=30)
async def get_plans():
    """Public, non-personalised plan info for the `/membership` page. Discounts are
    per-user (promo codes), so they are quoted by `/promo/{code}`, not here."""
    return PlansResponse(
        list_price=settings.membership_list_price,
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


class CheckoutRequest(BaseModel):
    promo_code: Optional[str] = Field(None, min_length=1, max_length=32)


@router.post("/checkout")
def start_checkout(response: Response, req: Optional[CheckoutRequest] = None,
                   user: UserResponse = Depends(billing_writer)):
    response.headers["Cache-Control"] = "private, no-store"
    return billing.checkout(user.id, user.email, req.promo_code if req else None)


@router.get("/promo/{code}")
def quote_promo(code: str, response: Response, user: UserResponse = Depends(billing_user)):
    """What this signed-in user would pay with `code` — 404 unknown, 409 spent."""
    response.headers["Cache-Control"] = "private, no-store"
    if len(code) > 32:
        raise HTTPException(404, "Promo code not found")
    return billing.promo_preview(user.id, code)


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
        # A gateway-side rejection (e.g. PER10030) posts plain Status/Message, no Period.
        logger.warning("billing: notification without Period status=%s message=%s", form.get("Status"), form.get("Message"))
        raise HTTPException(400, "Missing encrypted payment notification")
    return await asyncio.to_thread(billing.process_notification, encrypted)


@router.post("/notify")
async def notify(request: Request):
    return await _notification(request)


@router.post("/return")
async def payment_return(request: Request):
    # ReturnURL is a gateway form POST. Verify it identically to NotifyURL; only
    # validated server state grants access, never a browser query-string status.
    site, _ = billing.billing_urls()
    try:
        await _notification(request)
        outcome = "return"
    except HTTPException as e:
        # The payer is a browser here: send them back to the site, not a JSON 400.
        # NotifyURL still carries the authoritative outcome.
        if e.status_code >= 500:
            raise
        outcome = "failed"
    return RedirectResponse(f"{site}/membership?payment={outcome}", status_code=303,
                            headers={"Cache-Control": "private, no-store"})
