"""Meta Threads Graph API client.

Thin async wrapper over the two-step Threads publishing flow:

  1. Create a media container   POST {base}/{user_id}/threads
  2. Publish the container       POST {base}/{user_id}/threads_publish

Docs: https://developers.facebook.com/docs/threads/posts

Credentials (a long-lived access token + the numeric Threads user id) come from
settings / GSM. When unconfigured the client reports ``is_configured == False`` and
callers fall back to dry-run instead of raising.
"""

import asyncio
import logging
from typing import Optional

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

# Threads enforces a 500-character limit per post.
THREADS_MAX_CHARS = 500


class ThreadsError(RuntimeError):
    """Raised when the Threads API returns an error or is misconfigured."""


class ThreadsService:
    """Async client for publishing single posts to a Threads account."""

    def __init__(
        self,
        access_token: Optional[str] = None,
        user_id: Optional[str] = None,
        api_base: Optional[str] = None,
    ):
        self._token = access_token if access_token is not None else settings.threads_access_token
        self._user_id = user_id if user_id is not None else settings.threads_user_id
        self._base = (api_base or settings.threads_api_base).rstrip("/")

    @property
    def is_configured(self) -> bool:
        return bool(self._token and self._user_id)

    async def publish(
        self,
        text: str,
        image_url: Optional[str] = None,
        *,
        image_publish_delay: float = 5.0,
    ) -> str:
        """Publish one post. Returns the published media id.

        ``image_url`` must be a public HTTPS URL when given. For image posts the
        container needs a moment to be processed before publishing, hence the
        short delay between the two calls.
        """
        if not self.is_configured:
            raise ThreadsError("Threads API not configured (missing access token or user id)")
        if not text or not text.strip():
            raise ThreadsError("Refusing to publish an empty post")

        async with httpx.AsyncClient(timeout=30.0) as client:
            container_id = await self._create_container(client, text, image_url)
            if image_url:
                # Give Meta time to fetch/process the image before publishing.
                await asyncio.sleep(image_publish_delay)
            return await self._publish_container(client, container_id)

    async def publish_carousel(
        self,
        image_urls: list[str],
        text: str,
        *,
        item_delay: float = 2.0,
        parent_delay: float = 5.0,
    ) -> str:
        """Publish a carousel post (2–20 images) with a caption. Returns root media id.

        Each child image container is created first (Meta needs a moment to fetch each
        image), then the CAROUSEL parent referencing them, then publish.
        """
        if not self.is_configured:
            raise ThreadsError("Threads API not configured (missing access token or user id)")
        if not (2 <= len(image_urls) <= 20):
            raise ThreadsError(f"Carousel needs 2–20 items, got {len(image_urls)}")

        async with httpx.AsyncClient(timeout=60.0) as client:
            child_ids: list[str] = []
            for url in image_urls:
                child_ids.append(await self._create_carousel_item(client, url))
                await asyncio.sleep(item_delay)
            await asyncio.sleep(parent_delay)
            parent_id = await self._create_carousel_parent(client, child_ids, text)
            return await self._publish_container(client, parent_id)

    async def publish_reply(self, text: str, reply_to_id: str, *, delay: float = 2.0) -> str:
        """Publish a text reply to ``reply_to_id``. Returns the reply's media id."""
        if not self.is_configured:
            raise ThreadsError("Threads API not configured (missing access token or user id)")
        if not text or not text.strip():
            raise ThreadsError("Refusing to publish an empty reply")
        async with httpx.AsyncClient(timeout=30.0) as client:
            params = {
                "media_type": "TEXT", "text": text,
                "reply_to_id": reply_to_id, "access_token": self._token,
            }
            resp = await client.post(f"{self._base}/{self._user_id}/threads", data=params)
            data = self._parse(resp, "create reply")
            container_id = data.get("id")
            if not container_id:
                raise ThreadsError(f"Threads create-reply returned no id: {data}")
            await asyncio.sleep(delay)
            return await self._publish_container(client, container_id)

    async def publish_single_media(self, text: str, item: dict, *, video_timeout: float = 180.0) -> str:
        """Publish one post carrying a single media item ``{type, url}`` (image or video).

        Videos are processed asynchronously by Meta, so the container is polled until
        FINISHED before publishing (a fixed sleep would race long uploads). Returns the
        published media id.
        """
        if not self.is_configured:
            raise ThreadsError("Threads API not configured (missing access token or user id)")
        async with httpx.AsyncClient(timeout=120.0) as client:
            if item.get("type") == "video":
                params = {"media_type": "VIDEO", "video_url": item["url"], "text": text, "access_token": self._token}
                resp = await client.post(f"{self._base}/{self._user_id}/threads", data=params)
                container_id = self._parse(resp, "create video container").get("id")
                if not container_id:
                    raise ThreadsError("Threads create video container returned no id")
                await self._wait_until_ready(client, container_id, timeout=video_timeout)
                return await self._publish_container(client, container_id)
            # image path mirrors publish() but without re-opening a client
            container_id = await self._create_container(client, text, item["url"])
            await asyncio.sleep(5.0)
            return await self._publish_container(client, container_id)

    async def publish_media_carousel(
        self, items: list[dict], text: str, *, video_timeout: float = 180.0, parent_delay: float = 3.0,
    ) -> str:
        """Publish a carousel of mixed media (2–20 ``{type, url}`` items). Returns root id.

        Threads carousels may mix images and videos. Each child container is created,
        then ALL are polled to FINISHED (videos take longest) before the parent is
        created and published.
        """
        if not self.is_configured:
            raise ThreadsError("Threads API not configured (missing access token or user id)")
        if not (2 <= len(items) <= 20):
            raise ThreadsError(f"Carousel needs 2–20 items, got {len(items)}")
        async with httpx.AsyncClient(timeout=120.0) as client:
            child_ids: list[str] = []
            for it in items:
                if it.get("type") == "video":
                    child_ids.append(await self._create_carousel_item(client, it["url"], media_type="VIDEO"))
                else:
                    child_ids.append(await self._create_carousel_item(client, it["url"]))
            for cid in child_ids:
                await self._wait_until_ready(client, cid, timeout=video_timeout)
            await asyncio.sleep(parent_delay)
            parent_id = await self._create_carousel_parent(client, child_ids, text)
            return await self._publish_container(client, parent_id)

    async def _wait_until_ready(
        self, client: httpx.AsyncClient, container_id: str, *, timeout: float = 180.0, interval: float = 3.0,
    ) -> None:
        """Poll a media container until status == FINISHED (or raise on ERROR/timeout)."""
        elapsed = 0.0
        while elapsed < timeout:
            resp = await client.get(
                f"{self._base}/{container_id}",
                params={"fields": "status,error_message", "access_token": self._token},
            )
            data = self._parse(resp, "check container status")
            status = data.get("status")
            if status == "FINISHED":
                return
            if status in ("ERROR", "EXPIRED"):
                raise ThreadsError(f"Threads container {container_id} {status}: {data.get('error_message')}")
            await asyncio.sleep(interval)
            elapsed += interval
        raise ThreadsError(f"Threads container {container_id} not ready after {timeout}s")

    async def _create_carousel_item(
        self, client: httpx.AsyncClient, media_url: str, *, media_type: str = "IMAGE"
    ) -> str:
        params = {
            "media_type": media_type, "is_carousel_item": "true",
            ("video_url" if media_type == "VIDEO" else "image_url"): media_url,
            "access_token": self._token,
        }
        resp = await client.post(f"{self._base}/{self._user_id}/threads", data=params)
        data = self._parse(resp, "create carousel item")
        container_id = data.get("id")
        if not container_id:
            raise ThreadsError(f"Threads carousel-item returned no id: {data}")
        return container_id

    async def _create_carousel_parent(
        self, client: httpx.AsyncClient, children: list[str], text: str
    ) -> str:
        params = {
            "media_type": "CAROUSEL", "children": ",".join(children),
            "text": text, "access_token": self._token,
        }
        resp = await client.post(f"{self._base}/{self._user_id}/threads", data=params)
        data = self._parse(resp, "create carousel")
        container_id = data.get("id")
        if not container_id:
            raise ThreadsError(f"Threads carousel-parent returned no id: {data}")
        return container_id

    async def _create_container(
        self, client: httpx.AsyncClient, text: str, image_url: Optional[str]
    ) -> str:
        params = {
            "media_type": "IMAGE" if image_url else "TEXT",
            "text": text,
            "access_token": self._token,
        }
        if image_url:
            params["image_url"] = image_url
        resp = await client.post(f"{self._base}/{self._user_id}/threads", data=params)
        data = self._parse(resp, "create container")
        container_id = data.get("id")
        if not container_id:
            raise ThreadsError(f"Threads create-container returned no id: {data}")
        return container_id

    async def _publish_container(self, client: httpx.AsyncClient, container_id: str) -> str:
        params = {"creation_id": container_id, "access_token": self._token}
        resp = await client.post(f"{self._base}/{self._user_id}/threads_publish", data=params)
        data = self._parse(resp, "publish")
        media_id = data.get("id")
        if not media_id:
            raise ThreadsError(f"Threads publish returned no id: {data}")
        return media_id

    @staticmethod
    def _parse(resp: httpx.Response, step: str) -> dict:
        try:
            payload = resp.json()
        except Exception:
            payload = {"raw": resp.text}
        if resp.status_code >= 400 or "error" in payload:
            err = payload.get("error", payload)
            logger.warning("Threads %s failed (%s): %s", step, resp.status_code, err)
            raise ThreadsError(f"Threads {step} failed: {err}")
        return payload
