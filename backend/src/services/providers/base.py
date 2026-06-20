"""Provider abstraction for US-stock slow data (profile + daily OHLC).

Background: the US free-tier upstream (Massive/Polygon, ~5 req/min per key) was being
hit per-request for company profiles and logos — see the prod 429 storm on
``/v3/reference/tickers``. The fix is to warm that slow-moving data into Postgres from a
*batch* source on a schedule, and serve from the DB. This module defines the seam so the
warmer can pull from yfinance (no per-key rate cap, and it carries P/E that Polygon Starter
denies us) while Massive stays the source for company logos and the real-time/WebSocket path.

These providers are intentionally synchronous: they run inside the throttled background
warmer (in a thread), never on a request hot path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Protocol


@dataclass
class Profile:
    """Slow-moving company facts. All fields optional — providers fill what they have."""

    ticker: str
    name: Optional[str] = None
    market_cap: Optional[float] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    pe: Optional[float] = None
    dividend_yield: Optional[float] = None
    currency: Optional[str] = None
    description: Optional[str] = None
    logo_url: Optional[str] = None
    icon_url: Optional[str] = None
    logo_image: Optional[str] = None  # base64-encoded SVG (logos are auth-gated upstream)
    icon_image: Optional[str] = None  # base64-encoded PNG
    source: Optional[str] = None  # which provider produced this (observability)


@dataclass
class Bar:
    """One daily OHLCV bar."""

    date: str  # YYYY-MM-DD
    open: float
    high: float
    low: float
    close: float
    volume: float


# A US ticker is a short uppercase-ASCII symbol, optionally with a class suffix (BRK.B).
# This deliberately rejects the junk that was leaking into the US upstream and causing
# guaranteed-fail 429s: TW numeric/ETF codes ("2330", "00993A"), Chinese display names
# ("聯發科"), and English company *names* ("SALESFORCE", "FOXCONN") that aren't symbols.
_US_TICKER_RE = re.compile(r"^[A-Z]{1,5}([.\-][A-Z]{1,2})?$")


def is_us_ticker(ticker: str) -> bool:
    """True if ``ticker`` looks like a real US equity symbol (not a TW code or a name)."""
    if not ticker:
        return False
    return bool(_US_TICKER_RE.match(ticker.strip().upper()))


class PriceProvider(Protocol):
    """Source of slow US-stock data. Implementations must not raise — return None/[]."""

    name: str

    def supports(self, ticker: str) -> bool:
        """Whether this provider can serve the given ticker (market routing guard)."""
        ...

    def get_profile(self, ticker: str) -> Optional[Profile]:
        """Company profile, or None if unavailable/unsupported."""
        ...

    def get_daily_ohlc(self, ticker: str, start: str, end: str) -> List[Bar]:
        """Daily OHLCV bars in ``[start, end]`` (YYYY-MM-DD), ascending; [] on failure."""
        ...
