"""Google AdSense monetization metrics (AdSense Management API v2).

Reads the admin-facing money numbers for the site: estimated earnings, page RPM,
ad-request coverage (fill rate) and Active-View viewability, plus a per-day series
and the top earning pages.

Auth does *not* reuse the backend service account: AdSense has no service-account
support — reports can only be read by a Google account that owns the AdSense account.
So this needs one stored *user* OAuth credential:

  1. locally:  ``gcloud auth application-default login \\
                  --scopes=https://www.googleapis.com/auth/adsense.readonly,\\
https://www.googleapis.com/auth/cloud-platform``
     which writes an authorized-user JSON to the ADC path;
  2. on the VPS: paste that same JSON into GSM secret ``ADSENSE_OAUTH_JSON``.

The refresh token in it does not expire on its own (gcloud's OAuth client is a
published app), so this is a one-time setup rather than a rotating token.

Read-only and credential-gated: with no usable credential (or any API error) the
service returns ``configured``/``available`` flags instead of raising, so the admin
UI degrades to the AdSense dashboard link — same contract as
``CloudflareAnalyticsService.overview``.
"""

import asyncio
import json
import logging
import os
from datetime import date, timedelta
from typing import Optional

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

ADSENSE_API = "https://adsense.googleapis.com/v2"
ADSENSE_SCOPE = "https://www.googleapis.com/auth/adsense.readonly"
DASHBOARD_URL = "https://www.google.com/adsense/new/u/0/home"

# The five numbers worth an admin card. Earnings/RPM are the outcome; coverage and
# viewability are the two *actionable* ones — coverage drops mean ad requests aren't
# being filled, low viewability means Auto ads landed below the fold.
_METRICS = [
    "ESTIMATED_EARNINGS",
    "PAGE_VIEWS",
    "PAGE_VIEWS_RPM",
    "IMPRESSIONS",
    "CLICKS",
    "IMPRESSIONS_CTR",
    "AD_REQUESTS_COVERAGE",
    "ACTIVE_VIEW_VIEWABILITY",
]

# Response cell values are strings; tally metrics are ints, the rest floats.
_INT_METRICS = {"PAGE_VIEWS", "IMPRESSIONS", "CLICKS", "AD_REQUESTS", "MATCHED_AD_REQUESTS"}


def _num(header: dict, raw: str):
    name = header.get("name", "")
    try:
        return int(raw) if name in _INT_METRICS else float(raw)
    except (TypeError, ValueError):
        return 0


def _rows(payload: dict) -> list[dict]:
    """Zip a reports:generate payload into ``[{HEADER_NAME: value}, ...]``."""
    headers = payload.get("headers") or []
    out = []
    for row in payload.get("rows") or []:
        cells = row.get("cells") or []
        item = {}
        for h, c in zip(headers, cells):
            v = c.get("value")
            item[h["name"]] = v if h.get("type") == "DIMENSION" else _num(h, v)
        out.append(item)
    return out


def _totals(payload: dict) -> dict:
    """Metric totals for the whole window (absent when the report has no data)."""
    headers = payload.get("headers") or []
    cells = (payload.get("totals") or {}).get("cells") or []
    return {
        h["name"]: _num(h, c.get("value"))
        for h, c in zip(headers, cells)
        if h.get("type") != "DIMENSION"
    }


class AdSenseService:
    """Read-only client for the AdSense Management API v2."""

    def __init__(self, account_id: Optional[str] = None):
        # e.g. "pub-7624557827833745". Unset → discovered from /v2/accounts.
        self._account = account_id if account_id is not None else settings.adsense_account_id

    def _credentials(self):
        """Authorized-user credentials (blocking; call via asyncio.to_thread).

        Prefers the ``ADSENSE_OAUTH_JSON`` secret, falls back to local ADC so a dev
        box works straight after ``gcloud auth application-default login``.
        """
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials

        raw = settings.adsense_oauth_json
        if raw:
            creds = Credentials.from_authorized_user_info(json.loads(raw), scopes=[ADSENSE_SCOPE])
        else:
            import google.auth

            creds, _ = google.auth.default(scopes=[ADSENSE_SCOPE])
        creds.refresh(Request())
        return creds

    async def _auth_headers(self) -> dict:
        creds = await asyncio.to_thread(self._credentials)
        headers = {"Authorization": f"Bearer {creds.token}"}
        # User credentials carry no project of their own, and AdSense bills quota to a
        # project — without this header every call 403s with SERVICE_DISABLED.
        project = getattr(creds, "quota_project_id", None) or os.getenv("GCP_PROJECT_ID")
        if project:
            headers["x-goog-user-project"] = project
        return headers

    async def _get(self, client: httpx.AsyncClient, path: str, params=None) -> dict:
        resp = await client.get(f"{ADSENSE_API}/{path}", params=params)
        resp.raise_for_status()
        return resp.json()

    async def _report(self, client: httpx.AsyncClient, account: str, start: date, end: date,
                      dimensions: list[str], **extra) -> dict:
        params = [
            ("dateRange", "CUSTOM"),
            ("startDate.year", start.year), ("startDate.month", start.month), ("startDate.day", start.day),
            ("endDate.year", end.year), ("endDate.month", end.month), ("endDate.day", end.day),
            ("reportingTimeZone", "ACCOUNT_TIME_ZONE"),
            *[("dimensions", d) for d in dimensions],
            *[("metrics", m) for m in _METRICS],
            *extra.items(),
        ]
        return await self._get(client, f"{account}/reports:generate", params)

    async def overview(self, days: int = 28, top_pages: int = 5) -> dict:
        """Earnings + traffic-quality metrics over ``days``, plus top earning pages.

        Never raises: returns ``{configured, available, detail}`` on any credential or
        upstream error so the admin page can fall back to the dashboard link.
        """
        end = date.today() - timedelta(days=1)  # today is still accruing
        start = end - timedelta(days=max(1, days) - 1)
        try:
            headers = await self._auth_headers()
        except Exception as e:
            logger.warning("AdSense credentials unavailable: %s", e)
            return {
                "configured": False,
                "available": False,
                "detail": "No AdSense credential. Set the ADSENSE_OAUTH_JSON secret "
                          "(authorized-user JSON with the adsense.readonly scope).",
                "dashboard": DASHBOARD_URL,
            }

        try:
            async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
                account = self._account and f"accounts/{self._account}"
                if not account:
                    accounts = (await self._get(client, "accounts")).get("accounts") or []
                    if not accounts:
                        return {"configured": True, "available": False,
                                "detail": "This Google account has no AdSense account.",
                                "dashboard": DASHBOARD_URL}
                    account = accounts[0]["name"]

                sites, by_day, by_page = await asyncio.gather(
                    self._get(client, f"{account}/sites"),
                    self._report(client, account, start, end, ["DATE"]),
                    self._report(client, account, start, end, ["PAGE_URL"],
                                 orderBy="-ESTIMATED_EARNINGS", limit=max(1, top_pages)),
                )
        except httpx.HTTPStatusError as e:
            detail = e.response.text[:300]
            logger.warning("AdSense API %s: %s", e.response.status_code, detail)
            return {"configured": True, "available": False,
                    "detail": f"AdSense API {e.response.status_code}: {detail}",
                    "dashboard": DASHBOARD_URL}
        except Exception as e:
            logger.warning("AdSense request failed: %s", e)
            return {"configured": True, "available": False,
                    "detail": f"Request failed: {e}", "dashboard": DASHBOARD_URL}

        totals = _totals(by_day)
        site = (sites.get("sites") or [{}])[0]
        return {
            "configured": True,
            "available": True,
            "account": account.split("/")[-1],
            # GETTING_READY = still in review, no data will exist yet; READY = serving.
            "site": {
                "domain": site.get("domain"),
                "state": site.get("state"),
                "autoAdsEnabled": site.get("autoAdsEnabled"),
            },
            "range": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
            "currency": next(
                (h.get("currencyCode") for h in by_day.get("headers", []) if h.get("currencyCode")),
                "USD",
            ),
            "totals": {
                "earnings": totals.get("ESTIMATED_EARNINGS", 0.0),
                "pageViews": totals.get("PAGE_VIEWS", 0),
                "rpm": totals.get("PAGE_VIEWS_RPM", 0.0),
                "impressions": totals.get("IMPRESSIONS", 0),
                "clicks": totals.get("CLICKS", 0),
                "ctr": totals.get("IMPRESSIONS_CTR", 0.0),
                "coverage": totals.get("AD_REQUESTS_COVERAGE", 0.0),
                "viewability": totals.get("ACTIVE_VIEW_VIEWABILITY", 0.0),
            },
            "series": [
                {
                    "date": r.get("DATE"),
                    "earnings": r.get("ESTIMATED_EARNINGS", 0.0),
                    "pageViews": r.get("PAGE_VIEWS", 0),
                    "rpm": r.get("PAGE_VIEWS_RPM", 0.0),
                }
                for r in _rows(by_day)
            ],
            "top_pages": [
                {
                    "url": r.get("PAGE_URL"),
                    "earnings": r.get("ESTIMATED_EARNINGS", 0.0),
                    "pageViews": r.get("PAGE_VIEWS", 0),
                    "rpm": r.get("PAGE_VIEWS_RPM", 0.0),
                }
                for r in _rows(by_page)
            ],
            "dashboard": DASHBOARD_URL,
        }
