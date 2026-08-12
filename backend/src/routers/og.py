"""Public cover images for syndicated copies.

Deliberately unauthenticated: the whole point is that vocus, Substack, and any social
card crawler can fetch the URL we hand them. It exposes nothing an episode page does not
already show — the podcast name and the episode title.
"""
import base64
import logging

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from src.cache.redis_client import cache_get, cache_set
from src.services.og_image import episode_cover_svg
from src.services.podcast import PodcastService
from src.services.syndication_markdown import podcast_short_name

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/og", tags=["og"])
podcast_service = PodcastService()

# A day: the title never changes after ingest, and the syndication platforms refetch on
# their own schedule regardless.
_CACHE_CONTROL = "public, max-age=86400"

# Show artwork changes about never, and it is inlined into every cover we draw, so the
# fetch is cached rather than repeated per request.
# ponytail: content_sources.cover_image_url stores Spotify's CDN *link*, not the bytes —
# nothing in the repo mirrors cover art, though episode summary images do live in our own
# GCS bucket. Mirroring covers at ingest would remove this third-party fetch; deferred
# deliberately, since a weekly per-show request with a working degrade path is cheap.
# The degrade path stays either way: reading our own bucket is still a network call.
_ART_CACHE_TTL = 7 * 24 * 3600
_ART_MAX_BYTES = 512 * 1024


async def _cover_data_uri(podcast_name: str) -> str:
    """Show artwork as a data: URI, or "" if it cannot be had.

    Never raises: a cover without artwork is a perfectly good cover, and an image fetch
    is not a reason to fail the request.
    """
    if not podcast_name:
        return ""
    key = f"og:art:{podcast_name}"
    cached = await cache_get(key)
    if cached is not None:
        return cached
    try:
        covers = await podcast_service._podcast_cover_map()
        url = (covers or {}).get(podcast_name, "")
        if not url:
            return ""
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.get(url)
        content_type = resp.headers.get("content-type", "")
        if resp.status_code != 200 or not content_type.startswith("image/"):
            return ""
        if len(resp.content) > _ART_MAX_BYTES:
            logger.info("og: artwork for %s too large (%d bytes)", podcast_name, len(resp.content))
            return ""
        uri = f"data:{content_type};base64,{base64.b64encode(resp.content).decode()}"
    except Exception as e:  # noqa: BLE001 — the cover degrades, it does not fail
        logger.info("og: artwork fetch failed for %s (%s)", podcast_name, e)
        return ""
    await cache_set(key, uri, ttl=_ART_CACHE_TTL)
    return uri


@router.get("/episode/{episode_id}.svg")
async def episode_cover(episode_id: str) -> Response:
    """The cover drawn for one episode's off-site copies."""
    episode = await podcast_service.get_episode_admin(episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")

    podcast_name = (getattr(episode, "podcast_name", None) or "").strip()
    title = (getattr(episode, "episode_title", None) or "").strip() or episode_id
    svg = episode_cover_svg(title, kicker=podcast_short_name(podcast_name),
                            cover_data_uri=await _cover_data_uri(podcast_name))
    return Response(content=svg, media_type="image/svg+xml",
                    headers={"Cache-Control": _CACHE_CONTROL})
