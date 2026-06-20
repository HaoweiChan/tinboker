"""yfinance-backed provider — the batch source for US slow data.

yfinance is an *unofficial* scraper of Yahoo's endpoints: no API key, no per-key rate cap,
but no SLA and it can break when Yahoo changes internals. It is therefore used ONLY here, in
the scheduled background warmer over a bounded ticker set — never on a request hot path, and
never as a hard dependency (callers treat its output as best-effort and fall back to the DB /
Massive). In return it gives bulk daily OHLC and the P/E that Polygon Starter denies us, for
free. It does not provide company logos — those still come from MassiveProvider.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from src.services.providers.base import Bar, Profile, is_us_ticker

logger = logging.getLogger(__name__)


class YFinanceProvider:
    name = "yfinance"

    def supports(self, ticker: str) -> bool:
        return is_us_ticker(ticker)

    def get_profile(self, ticker: str) -> Optional[Profile]:
        if not self.supports(ticker):
            return None
        try:
            import yfinance as yf

            info = yf.Ticker(ticker).get_info() or {}
        except Exception as e:  # network / scraper breakage — best-effort only
            logger.warning(f"yfinance profile fetch failed for {ticker}: {e}")
            return None
        if not info or not (info.get("longName") or info.get("shortName")):
            return None
        div = info.get("dividendYield")
        return Profile(
            ticker=ticker,
            name=info.get("longName") or info.get("shortName"),
            market_cap=info.get("marketCap"),
            sector=info.get("sector"),
            industry=info.get("industry"),
            pe=info.get("trailingPE") or info.get("forwardPE"),
            dividend_yield=(div / 100.0 if isinstance(div, (int, float)) and div > 1 else div),
            currency=info.get("currency"),
            description=info.get("longBusinessSummary"),
            source=self.name,
        )

    def get_daily_ohlc(self, ticker: str, start: str, end: str) -> List[Bar]:
        if not self.supports(ticker):
            return []
        try:
            import yfinance as yf

            # end is exclusive in yfinance.history; the caller passes an inclusive end, so the
            # warmer should pad +1 day. We keep this provider faithful to yfinance semantics.
            df = yf.Ticker(ticker).history(start=start, end=end, interval="1d", auto_adjust=False)
        except Exception as e:
            logger.warning(f"yfinance OHLC fetch failed for {ticker}: {e}")
            return []
        bars: List[Bar] = []
        for idx, row in df.iterrows():
            try:
                close = float(row["Close"])
            except (KeyError, TypeError, ValueError):
                continue
            bars.append(
                Bar(
                    date=idx.strftime("%Y-%m-%d"),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=close,
                    volume=float(row.get("Volume", 0) or 0),
                )
            )
        return bars
