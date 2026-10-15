"""Local-language headlines for the market-move reason, where Yahoo's search is thin.

Yahoo's English news search is fine for US names and nearly empty for a Taiwan morning:
on 2026-10-15, with the TAIEX down 3% at 10:20, it returned no headline from the last 20
hours for the market or its leaders, so every lane skipped for want of a reason. The two
Taiwan feeds the news pipeline already reads from the VPS (pipelines/services/news/
feeds.json) carry the wire's own morning copy, and they are two publishers — which is
what lets a reason reach the 主因… tier at all.

Best-effort like the rest: a feed that fails is logged and skipped.
"""
from __future__ import annotations

import asyncio
import html
import json
import logging
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import httpx

from src.cache.redis_client import cache_get, cache_set

logger = logging.getLogger(__name__)

TTL = 120
SUMMARY_CHARS = 160          # the lede: where a wire puts the "why" its headline leaves out
_TAGS = re.compile(r"<[^>]+>")
FEEDS: dict[str, list[tuple[str, str]]] = {
    "TW": [
        ("鉅亨網", "https://news.cnyes.com/rss/v1/news/category/tw_stock"),
        ("鉅亨網", "https://news.cnyes.com/rss/v1/news/category/headline"),
        ("經濟日報", "https://money.udn.com/rssfeed/news/1001/5590?ch=money"),
        # Yahoo奇摩股市 syndicates the wires (中央社, 鉅亨, 經濟日報, …); each item's
        # <source> names the original, which is the publisher that counts.
        ("Yahoo奇摩股市", "https://tw.stock.yahoo.com/rss?category=tw-market"),
    ],
}


def parse_rss(xml: str, publisher: str) -> list[dict]:
    """RSS 2.0 items → the same headline shape ``yahoo_chart.news`` returns, plus the
    item's lede as ``summary`` (headlines say how far; the lede usually says why). An
    item's own ``<source>`` overrides the feed's publisher — an aggregator's copy of
    a 中央社 story is 中央社's."""
    out = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return out
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        try:
            published = int(parsedate_to_datetime(item.findtext("pubDate") or "").timestamp())
        except (TypeError, ValueError):
            continue
        summary = html.unescape(_TAGS.sub("", item.findtext("description") or "")).strip()
        source = (item.findtext("source") or "").strip()
        if title and link:
            out.append({"title": title, "publisher": source or publisher, "url": link, "published": published,
                        "summary": " ".join(summary.split())[:SUMMARY_CHARS]})
    return out


async def _feed(publisher: str, url: str) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True,
                                     headers={"User-Agent": "Mozilla/5.0 TinBoker"}) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        return parse_rss(resp.text, publisher)
    except httpx.HTTPError as e:
        logger.warning("market news feed %s failed: %s", url, e)
        return []


async def headlines(market_id: str) -> list[dict]:
    feeds = FEEDS.get(market_id)
    if not feeds:
        return []
    key = f"market_news:{market_id}"
    cached = await cache_get(key)
    if cached:
        return json.loads(cached)
    items = [h for batch in await asyncio.gather(*(_feed(p, u) for p, u in feeds)) for h in batch]
    if items:
        await cache_set(key, json.dumps(items, ensure_ascii=False), TTL)
    return items
