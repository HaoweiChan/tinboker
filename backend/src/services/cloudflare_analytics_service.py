"""Cloudflare zone analytics via the GraphQL Analytics API.

Reads aggregate traffic for the configured zone (``CLOUDFLARE_ZONE_TAG``) using the
``httpRequests1dGroups`` dataset — daily-rolled requests / page views / unique
visitors. Auth reuses ``CLOUDFLARE_API_TOKEN``; that token must carry the
**Account/Zone Analytics: Read** permission (the cache-purge-only token used by the
deploy pipeline will return an auth error — callers fall back to the dashboard link).

This is read-only and credential-gated: with no token/zone configured (or any API
error) ``overview`` returns ``configured``/``available`` flags so the admin UI can
degrade gracefully instead of raising.
"""

import logging
from datetime import date, timedelta
from typing import Optional

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

CF_GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql"

# Daily-rolled HTTP analytics for a zone. pageViews/uniques are populated for zones
# proxied through Cloudflare (tinboker.com is). Sampled adaptive datasets exist too,
# but the 1d groups are the simplest stable aggregate for an admin overview.
_QUERY = """
query Overview($zoneTag: String!, $since: String!, $until: String!) {
  viewer {
    zones(filter: { zoneTag: $zoneTag }) {
      httpRequests1dGroups(
        limit: 100
        filter: { date_geq: $since, date_leq: $until }
        orderBy: [date_ASC]
      ) {
        dimensions { date }
        sum { requests pageViews }
        uniq { uniques }
      }
    }
  }
}
"""


class CloudflareAnalyticsService:
    """Read-only client for the Cloudflare GraphQL zone-analytics dataset."""

    def __init__(self, api_token: Optional[str] = None, zone_tag: Optional[str] = None):
        self._token = api_token if api_token is not None else settings.cloudflare_api_token
        self._zone = zone_tag if zone_tag is not None else settings.cloudflare_zone_tag

    @property
    def is_configured(self) -> bool:
        return bool(self._token and self._zone)

    async def overview(self, days: int = 7) -> dict:
        """Totals + per-day series for the last ``days`` days.

        Returns ``{configured, available, totals, series, range, ...}``. Never raises:
        on any API/permission/parse error it returns ``available: False`` with a
        ``detail`` message so the UI can fall back to the Cloudflare dashboard link.
        """
        if not self.is_configured:
            return {
                "configured": False,
                "available": False,
                "detail": "Set CLOUDFLARE_API_TOKEN and CLOUDFLARE_ZONE_TAG to enable inline analytics.",
            }

        end = date.today()
        start = end - timedelta(days=max(1, days))
        variables = {
            "zoneTag": self._zone,
            "since": start.isoformat(),
            "until": end.isoformat(),
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    CF_GRAPHQL_URL,
                    json={"query": _QUERY, "variables": variables},
                    headers={"Authorization": f"Bearer {self._token}"},
                )
            payload = resp.json()
        except Exception as e:  # network / JSON decode
            logger.warning("Cloudflare analytics request failed: %s", e)
            return {"configured": True, "available": False, "detail": f"Request failed: {e}"}

        errors = payload.get("errors")
        if errors:
            # Most common: the token lacks Analytics:Read, or the zone tag is wrong.
            msg = "; ".join(str(e.get("message", e)) for e in errors)[:300]
            logger.warning("Cloudflare analytics GraphQL errors: %s", msg)
            return {"configured": True, "available": False, "detail": msg}

        try:
            zones = (payload.get("data") or {}).get("viewer", {}).get("zones") or []
            groups = zones[0].get("httpRequests1dGroups", []) if zones else []
        except (AttributeError, IndexError, TypeError) as e:
            logger.warning("Cloudflare analytics unexpected shape: %s", e)
            return {"configured": True, "available": False, "detail": "Unexpected API response shape."}

        series = []
        requests = page_views = uniques = 0
        for g in groups:
            s = g.get("sum") or {}
            u = g.get("uniq") or {}
            d = (g.get("dimensions") or {}).get("date")
            req = int(s.get("requests", 0) or 0)
            pv = int(s.get("pageViews", 0) or 0)
            uv = int(u.get("uniques", 0) or 0)
            requests += req
            page_views += pv
            uniques += uv
            series.append({"date": d, "requests": req, "pageViews": pv, "uniques": uv})

        return {
            "configured": True,
            "available": True,
            "range": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
            "totals": {
                "requests": requests,
                "pageViews": page_views,
                # Sum of daily uniques over-counts visitors who return on multiple days;
                # it's an upper bound, labelled "visits" in the UI to avoid implying it's
                # the exact unique-visitor count Cloudflare shows for the whole window.
                "uniques": uniques,
            },
            "series": series,
        }
