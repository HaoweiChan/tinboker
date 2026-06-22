"""Market inference from ticker shape — mirrors the frontend inferStockMarket()."""


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
