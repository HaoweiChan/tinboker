"""
Admin Analytics API - Fetches live traffic analytics from Cloudflare.
"""
import logging

from fastapi import APIRouter, Depends, Query

from src.auth.admin_auth import AdminAccess, get_admin_access
from src.services.cloudflare_analytics_service import CloudflareAnalyticsService

router = APIRouter(prefix="/api/admin/analytics", tags=["admin-analytics"])
logger = logging.getLogger(__name__)


@router.get("/overview")
async def get_analytics_overview(
    days: int = Query(default=7, ge=1, le=90),
    admin: AdminAccess = Depends(get_admin_access),
):
    """
    Cloudflare zone analytics overview — requests / page views / visits over ``days``.

    Returns live numbers when ``CLOUDFLARE_API_TOKEN`` (with Analytics:Read) and
    ``CLOUDFLARE_ZONE_TAG`` are set; otherwise ``available: false`` with a reason, so
    the admin UI falls back to the Cloudflare dashboard link. Always 200 (never raises
    on an upstream/permission error). Requires admin authentication.
    """
    cf = CloudflareAnalyticsService()
    data = await cf.overview(days=days)
    return {
        **data,
        "dashboards": {
            # Account-level Web Analytics (the :account token is resolved by the
            # Cloudflare dashboard to the signed-in account).
            "cloudflare": "https://dash.cloudflare.com/?to=/:account/web-analytics",
            "googleAnalytics": "https://analytics.google.com",
        },
    }
