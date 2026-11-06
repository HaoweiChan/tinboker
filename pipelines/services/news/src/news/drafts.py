"""Stage one news draft after ingestion, using persisted source records and CLI gates."""
from __future__ import annotations

import base64
import logging
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from shared.platform_client import USER_AGENT, admin_base_url, news_drafts_request
from shared.wiki_builder import news_slug
from shared.wiki_builder.repository import WikiRepository

from .pipeline.article import FeedEntry

MAX_IMAGE_BYTES = 4 * 1024 * 1024


def stock_chart(ticker: str, cache_path: Path) -> bytes | None:
    """Best-effort real-price card from the existing platform renderer, never a placeholder."""
    base = admin_base_url()
    if not base:
        return None
    request = urllib.request.Request(
        f"{base}/api/og/stock/{ticker}.png?days=90", headers={"User-Agent": USER_AGENT},
    )
    try:
        if cache_path.is_file():
            with cache_path.open("rb") as cached:
                image = cached.read(MAX_IMAGE_BYTES + 1)
            if image.startswith(b"\x89PNG\r\n\x1a\n") and len(image) <= MAX_IMAGE_BYTES:
                return image
        with urllib.request.urlopen(request, timeout=30) as response:
            image = response.read(MAX_IMAGE_BYTES + 1)
        if image.startswith(b"\x89PNG\r\n\x1a\n") and len(image) <= MAX_IMAGE_BYTES:
            cache_path.write_bytes(image)
            return image
    except (OSError, ValueError) as exc:
        logging.getLogger(__name__).warning("News stock chart unavailable (%s)", type(exc).__name__)
    return None


def stage_news_draft(repo: WikiRepository, entries: list[FeedEntry]) -> dict | None:
    """Fail closed before paid calls when disabled, history unavailable, or capped."""
    if os.environ.get("NEWS_THREADS_DRAFTS_ENABLED", "").lower() != "true":
        return None
    state = news_drafts_request()
    if state is None or state.get("remaining_today", 0) <= 0:
        return None

    from podcast.content_builder.news_drafts import identity, run

    articles = []
    # ponytail: candidates are persisted pages still in this run's bounded RSS window;
    # older pages absent from the feeds are not scanned or backfilled.
    for entry in entries:
        page = repo.get_page("news_article", news_slug(entry.url))
        if page is None:
            continue
        fm = page.frontmatter
        articles.append({
            "id": page.slug, "title": page.title, "url": fm["url"],
            "source": fm.get("source", ""), "language": fm.get("language", ""),
            "published_at": fm.get("published_at", ""),
            "publication_verified": fm.get("publication_verified", False),
            "tickers": fm.get("tickers", []),
            "paragraphs": [{"id": str(p["index"]), "text": p["text"]}
                           for p in fm.get("paragraphs", [])],
        })
    articles = list({article["id"]: article for article in articles}.values())
    if not articles:
        return None
    posted = set(state["already_posted_ids"])
    urls = set(state["already_posted_urls"])
    hashes = set(state["already_posted_hashes"])
    for article in articles:
        try:
            url, digest = identity(article)
        except (ValueError, KeyError, TypeError):
            continue  # The unchanged CLI prefilter reports malformed records.
        if url in urls or digest in hashes:
            posted.add(article["id"])
    # The systemd oneshot serializes runs; durable cache avoids repeated Jev spending.
    out = Path(os.environ.get("NEWS_THREADS_DRAFTS_CACHE_DIR", ".cache/news-threads-drafts"))
    report = run({"articles": articles, "already_posted_ids": sorted(posted)}, out,
                 as_of=datetime.now(timezone.utc), select_with_jev=True)
    draft = report.get("draft")
    if not draft:
        return None
    selected = next(a for a in articles if a["id"] == draft["article_id"])
    url, digest = identity(selected)
    # No image, no draft: capture() raises when the passage is missing or covered.
    from .screenshot import capture

    image = capture(selected["url"], draft["highlights"])
    ticker = draft.get("chart_ticker")
    chart = stock_chart(ticker, out / f"stock-chart-{digest}-{ticker}.png") if ticker else None
    result = news_drafts_request({
        "article_id": selected["id"], "canonical_url": url, "content_hash": digest,
        "source": selected["source"], "published_at": selected["published_at"],
        "image_png_base64": base64.b64encode(image).decode(),
        "stock_chart_png_base64": base64.b64encode(chart).decode() if chart else None,
        "chart_ticker": ticker if chart else None,
        "text": draft["post"], "comment": draft["first_comment"],
    })
    print(f"news draft: {(result or {}).get('status', 'handoff_failed')}")
    return result
