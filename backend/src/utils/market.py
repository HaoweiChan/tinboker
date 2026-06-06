"""Market inference from ticker shape — mirrors the frontend inferStockMarket()."""


def infer_market(ticker: str) -> str:
    """Best-effort market label from a bare ticker code.

    6-digit numeric codes are Korean (005930 Samsung, 000660 SK Hynix); 4-digit
    numeric codes are Taiwan (2330, 0050 ETFs); anything else is US. HK 4-digit
    codes (0700) collide with TW ETFs by shape, so they fall to TW — positively
    distinguishing them needs a real market field, not a heuristic.
    """
    code = (ticker or "").split(".")[0]
    if not code.isdigit():
        return "US"
    return "KR" if len(code) == 6 else "TW"
