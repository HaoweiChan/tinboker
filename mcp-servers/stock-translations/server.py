"""TinBoker stock-translations MCP server.

A thin, read-only MCP wrapper over the platform's public translation API
(`/api/stocks/translations/*`). It lets an agent — e.g. the tinboker-agents
summary writer, or Claude Code — look up a stock's English name, Traditional
Chinese (zh-TW) name, and brand color by ticker or by name.

Design notes
------------
* **Read-only.** Every tool is a GET against the HTTP API. The server holds no
  database credentials; the platform stays the single source of truth.
* **zh-TW is not enforced.** Many US stocks have no Chinese name (e.g. Palantir,
  Arm). Each result carries `has_zh_name` (true only for a real CJK name, never
  an English value parked in the zh column) and a pre-resolved `display_name`
  that already picks zh-TW vs. English — so callers don't re-implement that rule.

Config (env)
------------
* ``TINBOKER_API_BASE_URL`` — API root. Default ``https://api.tinboker.com``.
  Use ``https://dev-api.tinboker.com`` for dev.
* ``TINBOKER_API_TIMEOUT`` — per-request timeout in seconds. Default ``10``.

Run
---
    uvx --from . tinboker-stock-translations-mcp     # stdio transport
"""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP

API_BASE_URL = os.environ.get("TINBOKER_API_BASE_URL", "https://api.tinboker.com").rstrip("/")
API_TIMEOUT = float(os.environ.get("TINBOKER_API_TIMEOUT", "10"))

# Non-expiring TINBOKER_WRITE_TOKEN service token (the backend reads the same var).
# When set, the privileged backfill tools
# (list_pending_translations, propose_translations) are registered. Leave unset
# for the read-only deployment used by the summary-writing agent / frontend.
WRITE_TOKEN = os.environ.get("TINBOKER_WRITE_TOKEN")

mcp = FastMCP("stock-translations")


async def _get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    """GET a translation endpoint and return parsed JSON, or an {'error': ...} dict."""
    url = f"{API_BASE_URL}{path}"
    clean = {k: v for k, v in params.items() if v is not None}
    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            resp = await client.get(url, params=clean)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code} from {url}"}
    except httpx.HTTPError as e:
        return {"error": f"request failed: {e}"}


@mcp.tool()
async def search_stocks(
    query: str,
    market: Optional[str] = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Search stock translations by ticker, English name, zh-TW name, or curated alias.

    Use this when you have a company *name* (e.g. "Nvidia", "輝達", "台積電") or a
    partial ticker and need its canonical symbol, localized names, and brand color.

    Args:
        query: Free text — matches ticker, name_en, name_zh_tw, or a curated alias (case-insensitive).
        market: Optional market filter: "US", "TW", or "JP".
        limit: Max results (1–100, default 10).

    Returns a dict with `items`, each containing:
        ticker, market, name_en, name_zh_tw, brand_color, aliases, translation_status,
        has_zh_name (bool — a real Chinese name exists), and
        display_name (zh-TW if has_zh_name else English/ticker).
    """
    data = await _get(
        "/api/stocks/translations/search",
        {"q": query, "market": market, "limit": max(1, min(limit, 100))},
    )
    return data


@mcp.tool()
async def get_stock(ticker: str, market: Optional[str] = None) -> dict[str, Any]:
    """Resolve a single ticker to its localized names and brand color.

    Prefer this when you already know the exact symbol. If `market` is omitted and
    the symbol exists in more than one market, the best match is returned and the
    rest are listed under `alternatives`.

    A result with `has_zh_name=false` means the stock is English-preferred (no
    Chinese name); render `display_name` (its English/Latin name) as-is.
    """
    data = await _get(
        "/api/stocks/translations/batch",
        {"tickers": ticker, "market": market},
    )
    if "error" in data:
        return data
    items = data.get("items", [])
    if not items:
        return {"found": False, "ticker": ticker.upper(), "market": market}
    # Prefer an exact market match, then a row that has a real Chinese name.
    items.sort(key=lambda i: (market and i["market"] != market.upper(), not i["has_zh_name"]))
    best = items[0]
    return {"found": True, **best, "alternatives": items[1:]}


@mcp.tool()
async def get_stocks_batch(
    tickers: list[str],
    market: Optional[str] = None,
) -> dict[str, Any]:
    """Resolve many tickers at once — built for localizing a symbol-only list.

    Pass an episode's `related_tickers` (mixed TW/US is fine) to get a localized
    `display_name` and brand color for each. Symbols with no translation row are
    reported in `missing`.

    Args:
        tickers: List of symbols, e.g. ["NVDA", "2330", "AAPL"].
        market: Optional market filter applied to all.
    """
    if not tickers:
        return {"items": [], "missing": [], "total": 0}
    data = await _get(
        "/api/stocks/translations/batch",
        {"tickers": ",".join(tickers), "market": market},
    )
    if "error" in data:
        return data
    items = data.get("items", [])
    found = {i["ticker"] for i in items}
    missing = [t.strip().upper() for t in tickers if t.strip() and t.strip().upper() not in found]
    return {"items": items, "missing": missing, "total": len(items)}


async def _admin_request(
    method: str, path: str, *, params: dict[str, Any] | None = None, json: Any = None
) -> dict[str, Any]:
    """Authenticated request to an admin endpoint, or an {'error': ...} dict."""
    url = f"{API_BASE_URL}{path}"
    clean = {k: v for k, v in (params or {}).items() if v is not None}
    headers = {"Authorization": f"Bearer {WRITE_TOKEN}"}
    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            resp = await client.request(method, url, params=clean, json=json, headers=headers)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as e:
        hint = " (check TINBOKER_WRITE_TOKEN matches the value set on the backend)" if e.response.status_code in (401, 403) else ""
        return {"error": f"HTTP {e.response.status_code} from {url}{hint}"}
    except httpx.HTTPError as e:
        return {"error": f"request failed: {e}"}


# --- Privileged backfill tools (only when a write token is configured) -----------
if WRITE_TOKEN:

    @mcp.tool()
    async def list_pending_translations(limit: int = 50, market: Optional[str] = None) -> dict[str, Any]:
        """List PENDING translation stubs awaiting resolution (the backfill work queue).

        These are tickers discovered in episodes that have no names/color yet. Resolve
        each with search_stocks (dedupe) + your own research, then submit via
        propose_translations. Requires TINBOKER_WRITE_TOKEN.
        """
        return await _admin_request(
            "GET",
            "/api/admin/translations",
            params={"status": "pending", "limit": max(1, min(limit, 100)), "market": market},
        )

    @mcp.tool()
    async def propose_translations(items: list[dict[str, Any]]) -> dict[str, Any]:
        """Write resolved translations back to the table (status defaults to 'auto').

        Requires TINBOKER_WRITE_TOKEN. Rendered immediately on cards; a human later
        promotes 'auto' → 'approved' in the admin portal.

        Each item: {ticker, market?, name_en?, name_zh_tw?, brand_color?, name_preference?, translation_status?}
        - market is inferred from the ticker when omitted (numeric → TW, else US).
        - Set name_zh_tw to null for English-preferred stocks (do NOT copy the English
          name into the zh field).
        - name_preference: "auto" (default — show zh when it exists), "zh_tw", or "en"
          (force English even if a zh name exists). Omit unless you specifically want to
          override; omitting leaves an existing preference untouched.
        - brand_color is the company's corporate identity hex color, not a sentiment,
          sector, or random chip color. For TW references: MediaTek/聯發科 2454
          uses orange "#F58220"; TSMC/台積電 2330 uses red "#E60012";
          Delta Electronics/台達電 2308 uses light blue "#00AEEF".
        """
        valid_pref = {"auto", "zh_tw", "en"}
        payload: list[dict[str, Any]] = []
        for it in items:
            ticker = str(it.get("ticker", "")).strip().upper()
            if not ticker:
                continue
            bare = ticker.split(".")[0]
            market = str(it.get("market") or ("TW" if bare.isdigit() else "US")).upper()
            pref = it.get("name_preference")
            pref = pref.lower() if isinstance(pref, str) and pref.lower() in valid_pref else None
            payload.append(
                {
                    "ticker": bare,
                    "market": market,
                    "name_en": it.get("name_en"),
                    "name_zh_tw": it.get("name_zh_tw"),
                    "brand_color": it.get("brand_color"),
                    "name_preference": pref,
                    "translation_status": it.get("translation_status", "auto"),
                }
            )
        if not payload:
            return {"error": "no valid items (each needs at least a ticker)"}
        return await _admin_request("POST", "/api/admin/translations/bulk-json", json=payload)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
