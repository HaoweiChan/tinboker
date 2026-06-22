"""Meta Facebook Page Graph API client.

Thin async wrapper for publishing to a Facebook Page:

  - Album post:  upload each photo unpublished (POST /{page}/photos?published=false)
                 then a feed post referencing them (POST /{page}/feed, attached_media)
  - Photo post:  POST /{page}/photos  (single image + caption)
  - Text post:   POST /{page}/feed
  - Comment:     POST /{post-id}/comments  (optionally with an image attachment_url)

Docs: https://developers.facebook.com/docs/pages-api/posts

Credentials (a long-lived Page access token + the numeric Page id) come from
settings / GSM. When unconfigured the client reports ``is_configured == False`` and
callers fall back to dry-run instead of raising.
"""

import json
import logging
from typing import Optional

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

# Facebook is far more generous than Threads (63206 chars), but keep posts tight.
FACEBOOK_MAX_CHARS = 5000
# A feed post can reference at most this many attached photos.
FACEBOOK_MAX_ALBUM = 10


class FacebookError(RuntimeError):
    """Raised when the Facebook Graph API returns an error or is misconfigured."""


class FacebookService:
    """Async client for publishing posts + comments to a Facebook Page."""

    def __init__(
        self,
        page_id: Optional[str] = None,
        access_token: Optional[str] = None,
        api_base: Optional[str] = None,
    ):
        self._page_id = page_id if page_id is not None else settings.facebook_page_id
        self._token = access_token if access_token is not None else settings.facebook_page_access_token
        self._base = (api_base or settings.facebook_api_base).rstrip("/")

    @property
    def is_configured(self) -> bool:
        return bool(self._token and self._page_id)

    def _require_configured(self) -> None:
        if not self.is_configured:
            raise FacebookError("Facebook API not configured (missing page access token or page id)")

    async def publish_text(self, message: str) -> str:
        """Publish a text-only feed post. Returns the post id (``{page}_{post}``)."""
        self._require_configured()
        if not message or not message.strip():
            raise FacebookError("Refusing to publish an empty post")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self._base}/{self._page_id}/feed",
                data={"message": message, "access_token": self._token},
            )
            data = self._parse(resp, "create feed post")
            post_id = data.get("id")
            if not post_id:
                raise FacebookError(f"Facebook feed post returned no id: {data}")
            return post_id

    async def publish_photo(self, message: str, image_url: str) -> str:
        """Publish a single-photo post with a caption. Returns the feed post id."""
        self._require_configured()
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self._base}/{self._page_id}/photos",
                data={"url": image_url, "caption": message, "access_token": self._token},
            )
            data = self._parse(resp, "create photo post")
            # /photos returns {id: <photo>, post_id: <page>_<post>}; comment on post_id.
            post_id = data.get("post_id") or data.get("id")
            if not post_id:
                raise FacebookError(f"Facebook photo post returned no id: {data}")
            return post_id

    async def publish_album(self, message: str, image_urls: list[str]) -> str:
        """Publish a multi-photo feed post (album). Returns the feed post id."""
        self._require_configured()
        urls = image_urls[:FACEBOOK_MAX_ALBUM]
        if len(urls) < 2:
            raise FacebookError(f"Album needs 2+ images, got {len(urls)}")
        async with httpx.AsyncClient(timeout=120.0) as client:
            media_fbids: list[str] = []
            for url in urls:
                resp = await client.post(
                    f"{self._base}/{self._page_id}/photos",
                    data={"url": url, "published": "false", "access_token": self._token},
                )
                data = self._parse(resp, "upload album photo")
                fbid = data.get("id")
                if not fbid:
                    raise FacebookError(f"Facebook album photo returned no id: {data}")
                media_fbids.append(fbid)

            params = {"message": message, "access_token": self._token}
            for i, fbid in enumerate(media_fbids):
                params[f"attached_media[{i}]"] = json.dumps({"media_fbid": fbid})
            resp = await client.post(f"{self._base}/{self._page_id}/feed", data=params)
            data = self._parse(resp, "create album post")
            post_id = data.get("id")
            if not post_id:
                raise FacebookError(f"Facebook album post returned no id: {data}")
            return post_id

    async def publish_video(self, message: str, video_url: str) -> str:
        """Publish a single video post to the Page (description = caption).

        Facebook fetches the video from ``video_url`` (a public/signed URL) and processes
        it asynchronously; the returned video id identifies the post. A feed post cannot
        mix a video with photos, so the caller must send video-only here.
        """
        self._require_configured()
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{self._base}/{self._page_id}/videos",
                data={"file_url": video_url, "description": message, "access_token": self._token},
            )
            data = self._parse(resp, "create video post")
            video_id = data.get("id")
            if not video_id:
                raise FacebookError(f"Facebook video post returned no id: {data}")
            return video_id

    async def comment(self, post_id: str, message: str, image_url: Optional[str] = None) -> str:
        """Comment on a post (optionally with an image). Returns the comment id."""
        self._require_configured()
        if not message or not message.strip():
            raise FacebookError("Refusing to publish an empty comment")
        params = {"message": message, "access_token": self._token}
        if image_url:
            params["attachment_url"] = image_url
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{self._base}/{post_id}/comments", data=params)
            data = self._parse(resp, "create comment")
            comment_id = data.get("id")
            if not comment_id:
                raise FacebookError(f"Facebook comment returned no id: {data}")
            return comment_id

    @staticmethod
    def _parse(resp: httpx.Response, step: str) -> dict:
        try:
            payload = resp.json()
        except Exception:
            payload = {"raw": resp.text}
        if resp.status_code >= 400 or "error" in payload:
            err = payload.get("error", payload)
            logger.warning("Facebook %s failed (%s): %s", step, resp.status_code, err)
            raise FacebookError(f"Facebook {step} failed: {err}")
        return payload
