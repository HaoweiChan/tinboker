"""Public prelaunch membership prices. This router never accepts payments."""
import asyncio
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import inspect, text

from src.cache.cdn_cache import cdn_cached
from src.config import settings
from src.database.postgres import session_scope

router = APIRouter(prefix="/api/billing", tags=["billing"])


class PlansResponse(BaseModel):
    list_price: int
    founding_price: int
    founding_limit: int
    founding_remaining: int
    founding_open: bool
    checkout_open: Literal[False] = False
    gateway_env: Literal["sandbox", "production"]


def _founding_taken(gateway_env: str) -> int:
    """Read the shared billing table without registering or migrating its models."""
    with session_scope() as db:
        # A fresh local database may predate the billing service entirely.
        if not inspect(db.connection()).has_table("subscriptions"):
            return 0
        return int(db.execute(text(
            "SELECT COUNT(*) FROM subscriptions "
            "WHERE is_founding = TRUE AND gateway_env = :gateway_env "
            "AND status IN ('pending', 'active', 'cancelling', 'cancelled', 'ended')"
        ), {"gateway_env": gateway_env}).scalar_one())


@router.get("/plans", response_model=PlansResponse)
@cdn_cached(s_maxage=60, max_age=0, stale=30)
async def get_plans() -> PlansResponse:
    """Advertise backend-configured prices; checkout stays closed before launch."""
    gateway_env = "production" if settings.is_production else "sandbox"
    taken = await asyncio.to_thread(_founding_taken, gateway_env)
    remaining = max(0, settings.membership_founding_limit - taken)
    return PlansResponse(
        list_price=settings.membership_list_price,
        founding_price=settings.membership_founding_price,
        founding_limit=settings.membership_founding_limit,
        founding_remaining=remaining,
        founding_open=remaining > 0,
        gateway_env=gateway_env,
    )
