"""Read how many people opened our Substack posts.

The counterpart to :mod:`substack_publisher` (which *stages and publishes*): this
*reads* the per-post view counters Substack keeps for the publication. It reuses the
publisher's client, so the session cookie and the headers the edge requires are
maintained in exactly one place.

Two things shape the design:

1. **Which endpoint lists published posts is not documented.** Candidates are tried in
   order and the first that returns posts wins; the result reports the ``source`` that
   answered, so the working path can be pinned once it is known.

2. **Neither is the field holding the view count.** It is resolved against a ranked
   candidate list, and the result carries ``field_map`` (which key the number came
   from) or, when nothing matched, ``sample_keys`` (what the post objects actually
   carry). Posts found with no view field is reported as ``available: False`` — never
   as zero views, which would read as "nobody opened it".

Read-only and credential-gated: no cookie, or any API error, yields ``available:
False`` with a reason instead of raising.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from src.services.insight_fields import pick_int, sample_keys, sum_int
from src.services.substack_publisher import (REQUEST_TIMEOUT, SubstackClient, SubstackError,
                                             public_url)

logger = logging.getLogger(__name__)

# Ranked candidates for the list of published posts. The first is the publication
# dashboard's own list (most likely to carry stats); the second is the public archive,
# which at least yields the post set when the first path changes.
LIST_ENDPOINTS = (
    "/api/v1/post_management/published?offset={offset}&limit={limit}",
    "/api/v1/posts?offset={offset}&limit={limit}",
)

VIEW_KEYS = ("postviews", "views", "audience_views", "total_views", "view_count",
             "stats.views", "stats.postviews", "stats.audience_views")
# Reactions and comments ride along in the same objects when they are there at all.
REACTION_KEYS = ("reaction_count", "likes", "reactions", "stats.reaction_count")
COMMENT_KEYS = ("comment_count", "comments", "stats.comment_count")
TITLE_KEYS = ("title", "draft_title")

# Substack rejected limit=50 on the drafts endpoint ("param: limit, msg: Invalid
# value"), so stay under it here too rather than rediscover the same wall.
PAGE_SIZE = 49
MAX_POSTS = 200


def _posts_of(payload: Any) -> list[dict]:
    """The post list out of whichever envelope answered.

    The drafts endpoint keys its list ``posts``, not ``drafts`` — guessing that wrong
    returns 200 and an empty publication forever, so every shape is checked explicitly.
    """
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("posts") or payload.get("data") or payload.get("results") or []
    else:
        items = []
    return [p for p in items if isinstance(p, dict)]


def _title(post: dict) -> str:
    for key in TITLE_KEYS:
        value = post.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


class SubstackInsightsService:
    """Read-only client for Substack post view counters."""

    def __init__(self, client: Optional[SubstackClient] = None):
        self._client = client

    def _substack(self) -> SubstackClient:
        if self._client is None:
            self._client = SubstackClient()
        return self._client

    async def _list_page(self, http: httpx.AsyncClient, offset: int, limit: int,
                         endpoint: Optional[str]) -> tuple[list[dict], Optional[str]]:
        """One page of published posts → ``(posts, endpoint_that_answered)``.

        Once an endpoint has answered, later pages go straight to it; only the first
        call pays for the candidate walk.
        """
        client = self._substack()
        candidates = (endpoint,) if endpoint else LIST_ENDPOINTS
        last_error: Optional[Exception] = None
        for candidate in candidates:
            try:
                payload = await client.get_json(http, candidate.format(offset=offset, limit=limit))
            except SubstackError as e:
                # A wrong path 404s here; keep walking. A bad cookie fails every
                # candidate identically and is reported by the caller.
                last_error = e
                logger.info("substack insights: %s did not answer (%s)", candidate, e)
                continue
            posts = _posts_of(payload)
            if posts or endpoint:
                return posts, candidate
        if last_error and not endpoint:
            raise last_error
        return [], endpoint

    async def _published_posts(self, http: httpx.AsyncClient) -> tuple[list[dict], Optional[str], bool]:
        """Every published post, up to the cap → ``(posts, source, truncated)``."""
        posts: list[dict] = []
        seen: set[str] = set()
        source: Optional[str] = None
        while len(posts) < MAX_POSTS:
            page, source = await self._list_page(http, len(posts), PAGE_SIZE, source)
            if not page:
                return posts, source, False
            # An ignored `offset` would re-serve page one forever and inflate the view
            # total; dedupe by id so that shows up as "no more posts" instead.
            fresh = [item for item in page if str(item.get("id")) not in seen]
            seen.update(str(item.get("id")) for item in fresh)
            posts.extend(fresh)
            if len(page) < PAGE_SIZE or not fresh:
                return posts, source, False
        return posts[:MAX_POSTS], source, True

    async def account_summary(self) -> dict:
        """Lifetime view total across published posts.

        **Lifetime, not windowed** — Substack's post objects carry a running counter and
        no history, so growth comes from the daily snapshot charting this total day over
        day, the same way the follower counts are handled.
        """
        client = self._substack()
        if not client.is_configured():
            return {"configured": False, "available": False,
                    "detail": ("Set SUBSTACK_SID, SUBSTACK_SUBDOMAIN and SUBSTACK_USER_ID "
                               "to enable Substack insights.")}

        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as http:
                posts, source, truncated = await self._published_posts(http)
        except SubstackError as e:
            return {"configured": True, "available": False, "detail": str(e)}
        except httpx.HTTPError as e:
            return {"configured": True, "available": False, "detail": f"Request failed: {e}"}

        views, view_key, matched = sum_int(posts, VIEW_KEYS)
        reactions, reaction_key, _ = sum_int(posts, REACTION_KEYS)
        comments, comment_key, _ = sum_int(posts, COMMENT_KEYS)

        if posts and not matched:
            return {
                "configured": True, "available": False, "lifetime": True,
                "posts": len(posts), "source": source,
                "detail": ("Posts found but no view-count field matched — pin the right key in "
                           "substack_insights_service.VIEW_KEYS."),
                "sample_keys": sample_keys(posts),
            }

        return {
            "configured": True,
            "available": bool(posts),
            "lifetime": True,
            "posts": len(posts),
            "truncated": truncated,
            "source": source,
            "views": views,
            "reactions": reactions,
            "comments": comments,
            "field_map": {k: v for k, v in
                          (("views", view_key), ("reactions", reaction_key), ("comments", comment_key))
                          if v},
            **({"detail": "No published posts yet."} if not posts else {}),
        }

    async def recent_post_insights(self, limit: int = 10) -> list[dict]:
        """Newest published posts with their counters (best-effort, never raises)."""
        client = self._substack()
        if not client.is_configured():
            return []
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as http:
                posts, _ = await self._list_page(http, 0, max(1, min(limit, PAGE_SIZE)), None)
        except (SubstackError, httpx.HTTPError) as e:
            logger.warning("substack recent insights failed: %s", e)
            return []

        rows: list[dict] = []
        for post in posts[:limit]:
            views, _ = pick_int(post, VIEW_KEYS)
            reactions, _ = pick_int(post, REACTION_KEYS)
            url = post.get("canonical_url")
            rows.append({
                "post_id": str(post.get("id")) if post.get("id") else None,
                "title": _title(post),
                "url": url if isinstance(url, str) and url else public_url(client.subdomain, post),
                "views": views,
                "reactions": reactions,
            })
        return rows
