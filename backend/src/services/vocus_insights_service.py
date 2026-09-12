"""Read how many people opened our 方格子 (vocus) articles.

The counterpart to :mod:`vocus_publisher` (which *writes* articles): this *reads* the
per-article counters vocus keeps. Same undocumented API, same rule — never report
success on a shape we did not confirm.

Three things shape the design:

1. **Published articles are public, so reads need no credential.** Verified
   2026-09-11: ``GET /api/articles?...&status=2&userId=...`` with a browser User-Agent
   and no Authorization header returns ``{"count": N, "articles": [...]}``. Only writes
   need the 7-day token, so an expired token must not blank the reading panel — that is
   exactly what left ``analytics_snapshots.vocus_reads`` NULL on every row.

2. **There is no stats endpoint and no single-article read.** The article list is the
   only place an article's counters appear, so totals are accumulated by paging the
   published bucket, stopping at the response's ``count``. That is bounded by
   :data:`MAX_ARTICLES`; a publication larger than that reports ``truncated: True``
   rather than a quietly low number.

3. **Two read-ish counters exist.** ``pageview`` is what vocus itself shows as 瀏覽 and
   is what ``reads`` carries; ``readCount`` is the deeper "actually read" metric and
   travels alongside as ``read_count``. Both are resolved against ranked candidate
   lists and the result carries ``field_map`` (which key each number came from) or,
   when nothing matched, ``sample_keys`` (what the article objects actually carry). A
   zero that comes from looking in the wrong place is reported as ``available: False``,
   never as a zero — "nobody read it" and "we asked wrong" must never look the same.

Read-only: any API error yields ``available: False`` with a reason instead of raising,
so the admin page degrades to "not connected" rather than 500-ing.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from src.config import settings
from src.services import vocus_publisher
from src.services.insight_fields import pick_int, sample_keys, sum_int
from src.services.vocus_publisher import STATUS_PUBLIC, VOCUS_API_BASE, article_url

logger = logging.getLogger(__name__)

# Ranked candidates; the first key present wins. `pageview` and `readCount` were both
# observed live 2026-09-11 — pageview is what vocus displays as 瀏覽, so it leads.
READ_KEYS = ("pageview", "readCount", "totalReadCount", "readNum", "readTimes", "viewCount",
             "views", "pv", "stats.readCount", "stats.views")
READ_COUNT_KEYS = ("readCount", "totalReadCount", "stats.readCount")
LIKE_KEYS = ("likeCount", "totalLikeCount", "likes", "loveCount", "stats.likeCount")
BOOKMARK_KEYS = ("collectCount", "bookmarkCount", "saveCount", "stats.bookmarkCount")
TITLE_KEYS = ("title", "articleTitle", "name")

PAGE_SIZE = 50
# A publication this size is already far past what the panel can usefully show, and it
# caps the number of list calls one dashboard load can make against an undocumented API.
MAX_ARTICLES = 200

REQUEST_TIMEOUT = 30.0
# The public list answers a browser; a bare httpx UA is what we did not verify.
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")


class VocusReadError(RuntimeError):
    """The public article list answered with an HTTP error."""


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
    """Read-only, unauthenticated client for vocus article counters."""

    def __init__(self, user_id: Optional[str] = None, base: str = VOCUS_API_BASE):
        self._user_id = user_id if user_id is not None else settings.vocus_user_id
        self._base = base.rstrip("/")

    async def _page(self, http: httpx.AsyncClient, limit: int, page: int = 1
                    ) -> tuple[list[dict], Optional[int]]:
        """One page of the public bucket → ``(articles, count)``; ``count`` is the
        server's total when the response carried one."""
        resp = await http.get(
            f"{self._base}/api/articles?num={limit}&order=desc&page={page}&sort=updatedAt"
            f"&status={STATUS_PUBLIC}&userId={self._user_id}",
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )
        if resp.status_code >= 400:
            detail = (resp.text or "")[:300].replace("\n", " ")
            logger.warning("vocus public list page=%s -> %s %s", page, resp.status_code, detail)
            raise VocusReadError(f"http_{resp.status_code}: {detail}" if detail else f"http_{resp.status_code}")
        try:
            data = resp.json()
        except ValueError:
            return [], None
        if isinstance(data, list):
            return [a for a in data if isinstance(a, dict)], None
        data = data if isinstance(data, dict) else {}
        items = data.get("articles") or data.get("data") or []
        count = data.get("count")
        return [a for a in items if isinstance(a, dict)], count if isinstance(count, int) else None

    async def _published_articles(self, http: httpx.AsyncClient) -> tuple[list[dict], bool]:
        """Every published article, up to the cap → ``(articles, truncated)``."""
        articles: list[dict] = []
        seen: set[str] = set()
        page = 1
        while len(articles) < MAX_ARTICLES:
            batch, count = await self._page(http, PAGE_SIZE, page)
            if not batch:
                return articles, False
            # Ids, not just length: `page` is one more unverified parameter, and an API
            # that quietly ignores it would multiply the read total rather than fail.
            fresh = [a for a in batch if (_article_id(a) or "") not in seen]
            seen.update(_article_id(a) or "" for a in fresh)
            articles.extend(fresh)
            # The server's `count` is the end when present; otherwise a short page is
            # the last page. No fresh articles means paging isn't advancing — also done.
            done = (count is not None and len(articles) >= count) or len(batch) < PAGE_SIZE
            if done or not fresh:
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

        ``token`` is carried for the publisher's sake (the UI warns before it lapses);
        it does not gate reads, which are unauthenticated.
        """
        token = vocus_publisher.token_status()
        if not self._user_id:
            return {"configured": False, "available": False, "token": token,
                    "detail": "Set VOCUS_USER_ID to enable vocus insights."}

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as http:
                articles, truncated = await self._published_articles(http)
        except VocusReadError as e:
            return {"configured": True, "available": False, "token": token, "detail": str(e)}
        except httpx.HTTPError as e:
            return {"configured": True, "available": False, "token": token,
                    "detail": f"Request failed: {e}"}

        articles = articles[:max(1, limit_articles)]
        reads, read_key, matched = sum_int(articles, READ_KEYS)
        read_count, read_count_key, _ = sum_int(articles, READ_COUNT_KEYS)
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
            "read_count": read_count,
            "likes": likes,
            "bookmarks": bookmarks,
            "field_map": {k: v for k, v in
                          (("reads", read_key), ("read_count", read_count_key),
                           ("likes", like_key), ("bookmarks", bookmark_key))
                          if v},
            **({"detail": "No published articles yet."} if not articles else {}),
        }

    async def recent_post_insights(self, limit: int = 10) -> list[dict]:
        """Newest published articles with their counters (best-effort, never raises)."""
        if not self._user_id:
            return []
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as http:
                articles, _ = await self._page(http, max(1, min(limit, PAGE_SIZE)))
        except (VocusReadError, httpx.HTTPError) as e:
            logger.warning("vocus recent insights failed: %s", e)
            return []

        rows: list[dict] = []
        for article in articles[:limit]:
            article_id = _article_id(article)
            reads, _ = pick_int(article, READ_KEYS)
            read_count, _ = pick_int(article, READ_COUNT_KEYS)
            likes, _ = pick_int(article, LIKE_KEYS)
            rows.append({
                "article_id": article_id,
                "title": _title(article),
                "url": article_url(article_id) if article_id else None,
                "reads": reads,
                "read_count": read_count,
                "likes": likes,
            })
        return rows
