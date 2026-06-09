"""Google Search Console (SEO) monitoring.

Pulls Search Analytics — impressions, clicks, CTR, average position, broken down by
query and by page — for the configured GSC property, and caches the latest pull in
SQLite so the admin dashboard can read it without hitting Google on every request.

Auth reuses the Google service account the backend already runs with (firebase-admin /
google-cloud-storage). That same service account must be added as a *user* of the
Search Console property (Settings → Users and permissions) and ``GSC_SITE_URL`` set to
the property id (``sc-domain:tinboker.com`` for a domain property).

This is read-only and credential-gated: with no ``gsc_site_url`` / no usable Google
credentials, ``is_configured`` is False and callers report "not configured" instead of
raising.
"""

import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional
from urllib.parse import quote

import httpx

from src.config import settings
from src.database.db import get_connection

logger = logging.getLogger(__name__)

GSC_API_BASE = "https://searchconsole.googleapis.com/webmasters/v3"
GSC_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"


class SearchConsoleService:
    """Read-only client for the Search Console Search Analytics API."""

    def __init__(self, site_url: Optional[str] = None):
        self.site_url = site_url if site_url is not None else settings.gsc_site_url

    @property
    def is_configured(self) -> bool:
        return bool(self.site_url)

    def _access_token(self) -> str:
        """Obtain an OAuth2 access token (blocking; call via asyncio.to_thread)."""
        from google.auth.transport.requests import Request

        cred_path = settings.google_application_credentials
        if cred_path:
            from google.oauth2 import service_account

            creds = service_account.Credentials.from_service_account_file(
                cred_path, scopes=[GSC_SCOPE]
            )
        else:
            import google.auth

            creds, _ = google.auth.default(scopes=[GSC_SCOPE])
        creds.refresh(Request())
        return creds.token

    async def query(
        self,
        start_date: str,
        end_date: str,
        dimensions: list[str],
        row_limit: int = 25,
    ) -> list[dict]:
        """Run one Search Analytics query. Returns the ``rows`` list (possibly empty)."""
        if not self.is_configured:
            raise RuntimeError("Search Console not configured (set GSC_SITE_URL)")

        import asyncio

        token = await asyncio.to_thread(self._access_token)
        url = f"{GSC_API_BASE}/sites/{quote(self.site_url, safe='')}/searchAnalytics/query"
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "dimensions": dimensions,
            "rowLimit": row_limit,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url, json=body, headers={"Authorization": f"Bearer {token}"}
            )
        if resp.status_code >= 400:
            logger.warning("GSC query failed (%s): %s", resp.status_code, resp.text[:300])
            resp.raise_for_status()
        return resp.json().get("rows", [])

    async def overview(self, days: int = 28) -> dict:
        """Top queries + top pages + totals for the last ``days`` days."""
        end = date.today()
        start = end - timedelta(days=days)
        start_s, end_s = start.isoformat(), end.isoformat()

        totals_rows = await self.query(start_s, end_s, dimensions=["date"], row_limit=1000)
        clicks = sum(r.get("clicks", 0) for r in totals_rows)
        impressions = sum(r.get("impressions", 0) for r in totals_rows)
        ctr = (clicks / impressions) if impressions else 0.0

        queries = await self.query(start_s, end_s, dimensions=["query"], row_limit=25)
        pages = await self.query(start_s, end_s, dimensions=["page"], row_limit=25)

        return {
            "site_url": self.site_url,
            "range": {"start": start_s, "end": end_s, "days": days},
            "totals": {
                "clicks": clicks,
                "impressions": impressions,
                "ctr": round(ctr, 4),
            },
            "top_queries": [_row(r) for r in queries],
            "top_pages": [_row(r) for r in pages],
            "fetched_at": datetime.utcnow().isoformat() + "Z",
        }

    async def refresh_cache(self, days: int = 28) -> dict:
        """Pull a fresh overview and persist it to SQLite. Returns the overview."""
        data = await self.overview(days=days)
        _ensure_table()
        conn = get_connection()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO seo_metrics (id, days, payload, fetched_at) "
                "VALUES (1, ?, ?, ?)",
                (days, json.dumps(data), data["fetched_at"]),
            )
            conn.commit()
        finally:
            conn.close()
        return data

    @staticmethod
    def get_cached() -> Optional[dict]:
        _ensure_table()
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT payload FROM seo_metrics WHERE id = 1"
            ).fetchone()
            return json.loads(row["payload"]) if row else None
        finally:
            conn.close()


def _row(r: dict) -> dict:
    keys = r.get("keys", [])
    return {
        "key": keys[0] if keys else None,
        "clicks": r.get("clicks", 0),
        "impressions": r.get("impressions", 0),
        "ctr": round(r.get("ctr", 0.0), 4),
        "position": round(r.get("position", 0.0), 1),
    }


def _ensure_table() -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seo_metrics (
                id         INTEGER PRIMARY KEY,
                days       INTEGER,
                payload    TEXT,
                fetched_at TIMESTAMP
            )
            """
        )
        conn.commit()
    finally:
        conn.close()
