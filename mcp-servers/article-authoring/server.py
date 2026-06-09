"""TinBoker article-authoring MCP server.

A local stdio MCP wrapper over TinBoker's HTTP article APIs. It gives an LLM
the tools to assemble Markdown articles with TinBoker marker links, then create
and revise drafts through the same backend used by the admin editor.

Config (env)
------------
* ``TINBOKER_API_BASE_URL`` — API root. Default ``https://api.tinboker.com``.
  Use ``https://dev-api.tinboker.com`` for dev.
* ``TINBOKER_WEB_BASE_URL`` — frontend root for article URLs. Default
  ``https://tinboker.com``.
* ``TINBOKER_ARTICLE_TOKEN`` — optional service token. Required for draft,
  update, publish, and admin article reads.
* ``TINBOKER_API_TIMEOUT`` — per-request timeout in seconds. Default ``10``.

Run
---
    uvx --from . tinboker-article-authoring-mcp
"""

from __future__ import annotations

import os
import re
from typing import Any, Optional

import httpx
from mcp.server.fastmcp import FastMCP

API_BASE_URL = os.environ.get("TINBOKER_API_BASE_URL", "https://api.tinboker.com").rstrip("/")
WEB_BASE_URL = os.environ.get("TINBOKER_WEB_BASE_URL", "https://tinboker.com").rstrip("/")
API_TIMEOUT = float(os.environ.get("TINBOKER_API_TIMEOUT", "10"))
ARTICLE_TOKEN = os.environ.get("TINBOKER_ARTICLE_TOKEN")

mcp = FastMCP("article-authoring")


def _slugify_tag(name: str) -> str:
    slug = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", name.strip().lower()).strip("-")
    return slug or "topic"


def _article_link(slug: str, *, admin: bool = False) -> str:
    path = "/admin/articles" if admin else f"/article/{slug}"
    return f"{WEB_BASE_URL}{path}"


async def _request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: Any = None,
    token_required: bool = False,
) -> dict[str, Any]:
    """Call the TinBoker API and return parsed JSON, or an actionable error dict."""
    if token_required and not ARTICLE_TOKEN:
        return {
            "error": "TINBOKER_ARTICLE_TOKEN is not set. Set it in the MCP environment to use article write tools.",
        }

    url = f"{API_BASE_URL}{path}"
    clean_params = {k: v for k, v in (params or {}).items() if v is not None}
    headers = {"Authorization": f"Bearer {ARTICLE_TOKEN}"} if token_required and ARTICLE_TOKEN else None
    try:
        async with httpx.AsyncClient(timeout=API_TIMEOUT) as client:
            resp = await client.request(method, url, params=clean_params, json=json, headers=headers)
            resp.raise_for_status()
            if resp.status_code == 204:
                return {"ok": True}
            return resp.json()
    except httpx.HTTPStatusError as e:
        hint = ""
        if e.response.status_code in (401, 403):
            hint = " Check that TINBOKER_ARTICLE_TOKEN matches the backend's TINBOKER_ARTICLE_TOKEN."
        try:
            detail = e.response.json()
        except ValueError:
            detail = e.response.text[:500]
        return {"error": f"HTTP {e.response.status_code} from {url}.{hint}", "detail": detail}
    except httpx.HTTPError as e:
        return {"error": f"request failed: {e}"}


async def _get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return await _request("GET", path, params=params)


async def _admin(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: Any = None,
) -> dict[str, Any]:
    return await _request(method, path, params=params, json=json, token_required=True)


@mcp.tool()
async def search_tickers(query: str, market: Optional[str] = None, limit: int = 8) -> dict[str, Any]:
    """Search TinBoker stock translations by ticker or company name.

    Use this before citing a company in an article. Results include canonical
    ticker, market, zh-TW/English names, display_name, and brand color.
    """
    return await _get(
        "/api/stocks/translations/search",
        {"q": query, "market": market, "limit": max(1, min(limit, 20))},
    )


@mcp.tool()
async def cite_ticker(query: str, market: Optional[str] = None) -> dict[str, Any]:
    """Resolve a company query and return a ready-to-paste ticker citation.

    The returned `markdown` uses TinBoker's marker grammar:
    `[display](#ticker:SYMBOL)`.
    """
    data = await search_tickers(query=query, market=market, limit=1)
    if "error" in data:
        return data
    items = data.get("items", [])
    if not items:
        return {"found": False, "query": query, "markdown": None}
    item = items[0]
    ticker = str(item["ticker"]).upper()
    display = item.get("display_name") or item.get("name_zh_tw") or item.get("name_en") or ticker
    return {"found": True, "ticker": ticker, "display": display, "markdown": f"[{display}](#ticker:{ticker})", "item": item}


@mcp.tool()
async def suggest_tags(text: str, limit: int = 8) -> dict[str, Any]:
    """Suggest existing TinBoker topic tags that match article draft text."""
    query = text.strip()[:120]
    if not query:
        return {"items": []}
    data = await _get("/api/search", {"q": query, "limit": max(1, min(limit, 20))})
    if "error" in data:
        return data
    return {"items": data.get("tags", [])}


@mcp.tool()
async def add_tag(name: str, slug: Optional[str] = None) -> dict[str, Any]:
    """Return a ready-to-paste TinBoker tag citation for an article."""
    tag_slug = slug.strip() if slug else _slugify_tag(name)
    label = name.strip() or tag_slug
    return {"slug": tag_slug, "markdown": f"[{label}](#tag:{tag_slug})"}


@mcp.tool()
async def image_markdown(source_url: str, alt: str, title: Optional[str] = None) -> dict[str, Any]:
    """Return a Markdown image snippet for an externally hosted image.

    TinBoker's dedicated image upload endpoint is intentionally not exposed yet;
    Phase 0 still needs the public GCS/CDN hostname. Use this for drafts that
    reference an existing public image URL.
    """
    clean_url = source_url.strip()
    clean_alt = alt.strip() or "article image"
    suffix = f' "{title.strip()}"' if title and title.strip() else ""
    return {"markdown": f"![{clean_alt}]({clean_url}{suffix})", "source_url": clean_url}


@mcp.tool()
async def insert_chart(ticker: str, timeframe: str = "1Y", indicators: Optional[list[str]] = None) -> dict[str, Any]:
    """Return a future chart directive snippet for article drafts.

    Chart rendering is planned for Phase 3, so this is best used as a placeholder
    while drafting.
    """
    symbol = ticker.strip().upper()
    indicator_text = f" indicators={','.join(indicators)}" if indicators else ""
    return {"markdown": f":::chart{{ticker={symbol} timeframe={timeframe}{indicator_text}}}\n:::", "phase": "planned"}


@mcp.tool()
async def insert_graph(graph_id: str) -> dict[str, Any]:
    """Return a future knowledge-graph directive snippet for article drafts."""
    gid = graph_id.strip()
    return {"markdown": f":::graph{{id={gid}}}\n:::", "phase": "planned"}


@mcp.tool()
async def create_draft(
    title: str,
    body_markdown: str,
    subtitle: Optional[str] = None,
    slug: Optional[str] = None,
    cover_image_url: Optional[str] = None,
    key_points: Optional[list[str]] = None,
    tags: Optional[list[str]] = None,
    tickers: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Create a TinBoker article draft. Requires TINBOKER_ARTICLE_TOKEN."""
    payload = {
        "title": title,
        "subtitle": subtitle,
        "slug": slug,
        "body_content": body_markdown,
        "cover_image_url": cover_image_url,
        "key_points": key_points,
        "tags": tags,
        "tickers": tickers,
        "status": "draft",
    }
    data = await _admin("POST", "/api/admin/articles", json={k: v for k, v in payload.items() if v is not None})
    if "error" in data:
        return data
    return {**data, "admin_url": _article_link(data["slug"], admin=True), "preview_url": _article_link(data["slug"])}


@mcp.tool()
async def update_draft(
    article_id: int,
    title: Optional[str] = None,
    body_markdown: Optional[str] = None,
    subtitle: Optional[str] = None,
    slug: Optional[str] = None,
    cover_image_url: Optional[str] = None,
    key_points: Optional[list[str]] = None,
    tags: Optional[list[str]] = None,
    tickers: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Update an existing article draft. Requires TINBOKER_ARTICLE_TOKEN."""
    payload = {
        "title": title,
        "subtitle": subtitle,
        "slug": slug,
        "body_content": body_markdown,
        "cover_image_url": cover_image_url,
        "key_points": key_points,
        "tags": tags,
        "tickers": tickers,
    }
    data = await _admin("PATCH", f"/api/admin/articles/{article_id}", json={k: v for k, v in payload.items() if v is not None})
    if "error" in data:
        return data
    return {**data, "admin_url": _article_link(data["slug"], admin=True), "preview_url": _article_link(data["slug"])}


@mcp.tool()
async def list_my_drafts(limit: int = 20, offset: int = 0) -> dict[str, Any]:
    """List article drafts and published articles visible to the article token."""
    data = await _admin(
        "GET",
        "/api/admin/articles",
        params={"limit": max(1, min(limit, 100)), "offset": max(0, offset)},
    )
    if "error" in data:
        return data
    return {"items": data}


@mcp.tool()
async def get_article(article_id: Optional[int] = None, slug: Optional[str] = None) -> dict[str, Any]:
    """Get an article by admin ID when token is set, or by public slug."""
    if article_id is not None:
        data = await _admin("GET", f"/api/admin/articles/{article_id}")
    elif slug:
        data = await _get(f"/api/articles/{slug.strip()}")
    else:
        return {"error": "pass either article_id or slug"}
    if "error" in data:
        return data
    return {**data, "admin_url": _article_link(data["slug"], admin=True), "public_url": _article_link(data["slug"])}


@mcp.tool()
async def publish(article_id: int) -> dict[str, Any]:
    """Publish an article draft. Requires TINBOKER_ARTICLE_TOKEN."""
    data = await _admin("POST", f"/api/admin/articles/{article_id}/publish", json={})
    if "error" in data:
        return data
    return {**data, "public_url": _article_link(data["slug"])}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
