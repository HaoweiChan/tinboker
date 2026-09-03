"""Read how many people opened our 方格子 (vocus) articles.

The counterpart to :mod:`vocus_publisher` (which *writes* articles): this *reads* the
per-article counters vocus keeps. Same undocumented API, same 7-day credential, same
rule — never report success on a shape we did not confirm.

Two things shape the design:

1. **There is no stats endpoint and no single-article read.** The article list is the
   only place an article's counters appear, so totals are accumulated by paging the
   published bucket. That is bounded by :data:`MAX_ARTICLES`; a publication larger than
   that reports ``truncated: True`` rather than a quietly low number.

2. **The field that holds the read count is not documented and could not be captured
   here.** So it is resolved against a ranked candidate list and the result carries
   ``field_map`` (which key the number came from) or, when nothing matched,
   ``sample_keys`` (what the article objects actually carry). A zero that comes from
   looking in the wrong place is reported as ``available: False``, never as a zero —
   "nobody read it" and "we asked wrong" must never look the same on the dashboard.

Read-only and credential-gated: an unusable token or any API error yields
``available: False`` with a reason instead of raising, so the admin page degrades to
"not connected" rather than 500-ing.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from src.services import vocus_publisher
from src.services.insight_fields import pick_int, sample_keys, sum_int
from src.services.vocus_publisher import STATUS_PUBLIC, VocusClient, VocusError, article_url

logger = logging.getLogger(__name__)

# Ranked candidates. vocus's own article cards show 閱讀 / 愛心 / 收藏; these are the
# field spellings its API is most likely to use for them. Order matters only in that
# the first key present wins — confirm against `sample_keys` and pin the real one.
READ_KEYS = ("readCount", "totalReadCount", "readNum", "readTimes", "viewCount", "views",
             "pv", "stats.readCount", "stats.views")
LIKE_KEYS = ("likeCount", "totalLikeCount", "likes", "loveCount", "stats.likeCount")
BOOKMARK_KEYS = ("bookmarkCount", "collectCount", "saveCount", "stats.bookmarkCount")
TITLE_KEYS = ("title", "articleTitle", "name")

PAGE_SIZE = 50
# A publication this size is already far past what the panel can usefully show, and it
# caps the number of list calls one dashboard load can make against an undocumented API.
MAX_ARTICLES = 200

REQUEST_TIMEOUT = 30.0


def _article_id(article: dict) -> Optional[str]:
    raw = article.get("_id") or article.get("id") or article.get("articleId")
    return str(raw) if raw else None


def _title(article: dict) -> str:
    for key in TITLE_KEYS:
        value = article.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


class VocusInsightsService:
    """Read-only client for vocus article counters."""

    def __init__(self, client: Optional[VocusClient] = None):
        # Constructed lazily by default so an unconfigured environment never reads the
        # credential just to render a "not connected" panel.
        self._client = client

    def _vocus(self) -> VocusClient:
        if self._client is None:
            self._client = VocusClient()
        return self._client

    async def _published_articles(self, http: httpx.AsyncClient) -> tuple[list[dict], bool]:
        """Every published article, up to the cap → ``(articles, truncated)``."""
        client = self._vocus()
        articles: list[dict] = []
        seen: set[str] = set()
        page = 1
        while len(articles) < MAX_ARTICLES:
            batch = await client.list_articles(http, STATUS_PUBLIC, limit=PAGE_SIZE, page=page)
            if not batch:
                return articles, False
            # Ids, not just length: `page` is one more unverified parameter, and an API
            # that quietly ignores it would multiply the read total rather than fail.
            fresh = [a for a in batch if (_article_id(a) or "") not in seen]
            seen.update(_article_id(a) or "" for a in fresh)
            articles.extend(fresh)
            # A short page is the last page; vocus has no cursor to follow. No fresh
            # articles means paging isn't advancing, which is also the end of the road.
            if len(batch) < PAGE_SIZE or not fresh:
                return articles, False
            page += 1
        return articles[:MAX_ARTICLES], True

    async def account_summary(self, limit_articles: int = MAX_ARTICLES) -> dict:
        """Lifetime read total across published articles.

        **Lifetime, not windowed.** vocus exposes a running counter per article and no
        history, so there is no honest way to answer "reads in the last 28 days" from
        one call. Growth comes from the daily snapshot
        (``POST /api/admin/analytics/snapshot``) charting this total day over day —
        the same reason the Threads follower count is snapshotted rather than queried
        for a range.
        """
        token = vocus_publisher.token_status()
        if not token["configured"]:
            return {"configured": False, "available": False,
                    "detail": "Set VOCUS_ID_TOKEN and VOCUS_USER_ID to enable vocus insights."}
        if token["expired"]:
            # Same rule as the publisher: an expired 7-day token is loud, never a
            # silently empty panel that looks like "no reads yet".
            return {"configured": True, "available": False, "token": token,
                    "detail": "vocus token expired — replace VOCUS_ID_TOKEN to resume reading stats."}

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as http:
                articles, truncated = await self._published_articles(http)
        except VocusError as e:
            return {"configured": True, "available": False, "token": token, "detail": str(e)}
        except httpx.HTTPError as e:
            return {"configured": True, "available": False, "token": token,
                    "detail": f"Request failed: {e}"}

        articles = articles[:max(1, limit_articles)]
        reads, read_key, matched = sum_int(articles, READ_KEYS)
        likes, like_key, _ = sum_int(articles, LIKE_KEYS)
        bookmarks, bookmark_key, _ = sum_int(articles, BOOKMARK_KEYS)

        if articles and not matched:
            # The articles are there and none of them carried a read count: the mapping
            # is wrong, not the audience. Hand over the field names so it is one edit.
            return {
                "configured": True, "available": False, "token": token,
                "articles": len(articles), "lifetime": True,
                "detail": ("Articles found but no read-count field matched — pin the right key in "
                           "vocus_insights_service.READ_KEYS."),
                "sample_keys": sample_keys(articles),
            }

        return {
            "configured": True,
            "available": bool(articles),
            "token": token,
            "lifetime": True,
            "articles": len(articles),
            "truncated": truncated,
            "reads": reads,
            "likes": likes,
            "bookmarks": bookmarks,
            "field_map": {k: v for k, v in
                          (("reads", read_key), ("likes", like_key), ("bookmarks", bookmark_key))
                          if v},
            **({"detail": "No published articles yet."} if not articles else {}),
        }

    async def recent_post_insights(self, limit: int = 10) -> list[dict]:
        """Newest published articles with their counters (best-effort, never raises)."""
        token = vocus_publisher.token_status()
        if not token["configured"] or token["expired"]:
            return []
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as http:
                articles = await self._vocus().list_articles(
                    http, STATUS_PUBLIC, limit=max(1, min(limit, PAGE_SIZE))
                )
        except (VocusError, httpx.HTTPError) as e:
            logger.warning("vocus recent insights failed: %s", e)
            return []

        rows: list[dict] = []
        for article in articles[:limit]:
            article_id = _article_id(article)
            reads, _ = pick_int(article, READ_KEYS)
            likes, _ = pick_int(article, LIKE_KEYS)
            rows.append({
                "article_id": article_id,
                "title": _title(article),
                "url": article_url(article_id) if article_id else None,
                "reads": reads,
                "likes": likes,
            })
        return rows
