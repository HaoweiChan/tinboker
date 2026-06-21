"""Read engagement insights from a Meta Facebook Page (Graph API).

The read counterpart to :mod:`facebook_publisher` (which *writes* posts). Pulls the
Page's audience size (fans / followers) and a few still-supported Page-insights
metrics. Reuses the same Page access token + Page id configured for publishing
(``FACEBOOK_PAGE_ACCESS_TOKEN`` / ``FACEBOOK_PAGE_ID``).

Facebook deprecated most classic Page-insights metrics; this queries only the set
that is still valid on Graph API v21 (verified against the live page): page views,
post engagements, total actions. fan_count / followers_count come from the Page node
(always available). Read-only and credential-gated — on any error it returns
``available: False`` with a reason instead of raising, so the admin UI degrades to a
"not connected" state.

Docs: https://developers.facebook.com/docs/platforminsights/page
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

# Page-insights metrics still valid on Graph API v21 for this page (period=day,
# summed over the window). The classic page_impressions* / page_fans family was
# removed by Meta and 400s with "must be a valid insights metric".
PAGE_DAILY_METRICS = ["page_views_total", "page_post_engagements", "page_total_actions"]


class FacebookInsightsService:
    """Read-only client for Facebook Page audience + engagement insights."""

    def __init__(
        self,
        page_id: Optional[str] = None,
        access_token: Optional[str] = None,
        api_base: Optional[str] = None,
    ):
        self._page_id = page_id if page_id is not None else settings.facebook_page_id
        self._token = access_token if access_token is not None else settings.facebook_page_access_token
        self._base = (api_base or settings.facebook_api_base).rstrip("/")

    @property
    def is_configured(self) -> bool:
        return bool(self._token and self._page_id)

    async def _get(self, client: httpx.AsyncClient, path: str, params: dict) -> dict:
        params = {**params, "access_token": self._token}
        resp = await client.get(f"{self._base}/{path}", params=params)
        payload = resp.json()
        if resp.status_code >= 400 or "error" in payload:
            err = payload.get("error", payload)
            raise RuntimeError(str(err.get("message", err) if isinstance(err, dict) else err)[:300])
        return payload

    @staticmethod
    def _sum_metric(item: dict) -> int:
        total = 0
        for v in item.get("values", []) or []:
            try:
                total += int((v or {}).get("value", 0) or 0)
            except (TypeError, ValueError):
                continue
        return total

    async def account_summary(self, days: int = 28) -> dict:
        """Page audience + engagement totals over ``days``.

        Returns ``{configured, available, name, fans, followers, metrics, range}``.
        Never raises — degradation is reported via ``available: False`` + ``detail``.
        """
        if not self.is_configured:
            return {
                "configured": False,
                "available": False,
                "detail": "Set FACEBOOK_PAGE_ID and FACEBOOK_PAGE_ACCESS_TOKEN to enable Facebook insights.",
            }

        now = datetime.now(timezone.utc)
        since = int((now - timedelta(days=max(1, days))).timestamp())
        until = int(now.timestamp())
        name: Optional[str] = None
        fans: Optional[int] = None
        followers: Optional[int] = None
        metrics: dict[str, int] = {}
        detail: Optional[str] = None

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Audience size from the Page node (always available, not an insight).
                try:
                    node = await self._get(
                        client, self._page_id, {"fields": "name,fan_count,followers_count"}
                    )
                    name = node.get("name")
                    fans = node.get("fan_count")
                    followers = node.get("followers_count")
                except Exception as e:
                    detail = f"Page fields failed: {e}"
                    logger.warning("Facebook page node failed: %s", e)

                # Daily engagement metrics summed over the window.
                try:
                    payload = await self._get(
                        client,
                        f"{self._page_id}/insights",
                        {"metric": ",".join(PAGE_DAILY_METRICS), "period": "day",
                         "since": since, "until": until},
                    )
                    for item in (payload.get("data") or []):
                        if item.get("name"):
                            metrics[item["name"]] = self._sum_metric(item)
                except Exception as e:
                    detail = detail or f"Insights failed: {e}"
                    logger.warning("Facebook page insights failed: %s", e)
        except Exception as e:
            return {"configured": True, "available": False, "detail": f"Request failed: {e}"}

        available = followers is not None or fans is not None or bool(metrics)
        return {
            "configured": True,
            "available": available,
            "range": {"days": days},
            "name": name,
            "fans": fans,
            "followers": followers,
            "metrics": metrics,
            **({"detail": detail} if detail and not available else {}),
        }
