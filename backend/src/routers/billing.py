"""Public membership billing info (PR 3a — billing foundation).

Only one endpoint lives here for now: the plans the `/membership` page reads to
render price + founding-seat availability. No endpoint in this file talks to
NewebPay or writes `member_until` — PR 3b adds checkout/notify/cancel once
NewebPay approves the Periodic API (see `docs/agents/auth-admin.md` § Membership).
"""
import asyncio

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func

from src.cache.cdn_cache import cdn_cached
from src.config import settings
from src.database.models import Subscription
from src.database.postgres import session_scope

router = APIRouter(prefix="/api/billing", tags=["billing"])

# PR 3b flips this once the checkout endpoint exists. Kept as an explicit constant
# (ANDed into `checkout_open` below) rather than inferring "checkout exists" from
# `newebpay_configured` alone, so approved-but-not-yet-wired credentials still show
# 即將開放 instead of a button that 404s.
CHECKOUT_IMPLEMENTED = False


class PlansResponse(BaseModel):
    list_price: int
    founding_price: int
    founding_limit: int
    founding_remaining: int
    founding_open: bool
    checkout_open: bool


def _founding_taken() -> int:
    """Founding seats already spent: active or cancelled-but-paid mandates in the
    current gateway env still used a seat; pending (never charged) and ended do not."""
    with session_scope() as db:
        return int(
            db.query(func.count(Subscription.id))
            .filter(
                Subscription.is_founding.is_(True),
                Subscription.status.in_(["active", "cancelled"]),
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
    PR 3b must re-check founding seats inside the checkout transaction before
    actually granting the founding price, not trust what this endpoint last said.
    """
    taken = await asyncio.to_thread(_founding_taken)
    remaining = max(0, settings.membership_founding_limit - taken)
    return PlansResponse(
        list_price=settings.membership_list_price,
        founding_price=settings.membership_founding_price,
        founding_limit=settings.membership_founding_limit,
        founding_remaining=remaining,
        founding_open=remaining > 0,
        checkout_open=settings.newebpay_configured and CHECKOUT_IMPLEMENTED,
    )
