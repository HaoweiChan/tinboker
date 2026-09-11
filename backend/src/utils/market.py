"""Market inference from ticker shape — mirrors the frontend inferStockMarket()."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def infer_market(ticker: str) -> str:
    """Best-effort market label from a bare ticker code.

    6-digit numeric codes are Korean (005930 Samsung, 000660 SK Hynix); 3-5 digit
    numeric codes are Taiwan (2330, 0050/00878B/00632R ETFs); anything else is US.
    HK 4-digit codes (0700) collide with TW ETFs by shape, so they fall to TW —
    positively distinguishing them needs a real market field, not a heuristic.

    A single trailing class letter (TW ETFs like 00878B / 00632R) is stripped
    before the digit check so those don't fall through to US.
    """
    code = (ticker or "").split(".")[0].upper()
    # Strip a single trailing class letter from an otherwise-numeric TW code.
    core = code[:-1] if (len(code) > 1 and code[-1].isalpha() and code[:-1].isdigit()) else code
    if not core.isdigit():
        return "US"
    return "KR" if len(core) == 6 else "TW"


MARKET_TZ = {
    "TW": ZoneInfo("Asia/Taipei"),
    "KR": ZoneInfo("Asia/Seoul"),
    "US": ZoneInfo("America/New_York"),
}


def market_date(at_utc: datetime, market: str) -> str:
    """Calendar date (YYYY-MM-DD) of a naive-UTC instant on the given market's exchange.

    A TW show released 23:30 UTC is already the next day in Taipei; a US name
    discussed at 01:00 UTC is still the previous evening in New York. Daily close
    tables are keyed by the exchange's local date, so baselines must be too.
    """
    tz = MARKET_TZ.get(market, MARKET_TZ["US"])
    return at_utc.replace(tzinfo=timezone.utc).astimezone(tz).strftime("%Y-%m-%d")
