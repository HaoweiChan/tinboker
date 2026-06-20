"""Massive/Polygon-backed provider.

Kept as a provider so the warmer can pull **logos** from here (yfinance has none, and
Massive's branding images are auth-gated so the frontend can't load them directly) while
sourcing the rest of the profile + OHLC from the rate-cap-free yfinance provider. Massive
also remains the real-time/WebSocket path elsewhere; this wrapper is slow-data only.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from src.services.massive_service import MassiveAPIService
from src.services.providers.base import Bar, Profile, is_us_ticker

logger = logging.getLogger(__name__)


class MassiveProvider:
    name = "massive"

    def __init__(self, service: Optional[MassiveAPIService] = None):
        self._service = service or MassiveAPIService()

    def supports(self, ticker: str) -> bool:
        return is_us_ticker(ticker)

    def get_profile(self, ticker: str) -> Optional[Profile]:
        """Profile incl. base64 logo/icon. Returns None if Massive has nothing (e.g. 429)."""
        if not self.supports(ticker):
            return None
        details = self._service.get_ticker_details(ticker)  # already error-safe → dict|None
        if not details:
            return None
        return Profile(
            ticker=ticker,
            name=details.get("name"),
            market_cap=details.get("market_cap"),
            industry=details.get("industry"),
            currency=details.get("currency"),
            description=details.get("description"),
            logo_url=details.get("logo_url"),
            icon_url=details.get("icon_url"),
            logo_image=details.get("logo_image"),
            icon_image=details.get("icon_image"),
            source=self.name,
        )

    def get_daily_ohlc(self, ticker: str, start: str, end: str) -> List[Bar]:
        if not self.supports(ticker):
            return []
        rows = self._service.list_daily_ticker_summary_range(ticker, start, end)
        return [
            Bar(
                date=r["date"],
                open=r.get("open"),
                high=r.get("high"),
                low=r.get("low"),
                close=r.get("close"),
                volume=r.get("volume", 0),
            )
            for r in rows
            if r.get("close") is not None
        ]
