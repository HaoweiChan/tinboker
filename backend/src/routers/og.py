"""Public cover images for syndicated copies.

Deliberately unauthenticated: the whole point is that vocus, Substack, and any social
card crawler can fetch the URL we hand them. It exposes nothing an episode page does not
already show — the podcast name and the episode title.
"""
import asyncio
import base64
import logging
import mimetypes

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from src.cache.redis_client import cache_get, cache_set
from src.services.gcs_content import GCSContentService, media_path
from src.services.og_image import episode_cover_png, episode_cover_svg
from src.services.podcast import PodcastService
from src.services.syndication_markdown import podcast_short_name, syndication_title

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/og", tags=["og"])
podcast_service = PodcastService()

# A day: the title never changes after ingest, and the syndication platforms refetch on
# their own schedule regardless.
_CACHE_CONTROL = "public, max-age=86400"

# Show artwork changes about never, and it is inlined into every cover we draw, so the
# result is cached rather than rebuilt per request.
_ART_CACHE_TTL = 7 * 24 * 3600
_ART_MAX_BYTES = 512 * 1024


async def _cover_bytes(url: str) -> tuple[bytes, str]:
    """Artwork as ``(bytes, content_type)`` — off our own disk when it is mirrored.

    ``content_sources.cover_image_url`` points at the media host once
    ``mirror_podcast_covers`` has run, and that maps to a file on the disk this process
    already has mounted, so the common path is a local read with no network at all. The
    HTTP branch stays for rows the mirror has not reached yet (it runs in the
    background after boot) and for anything pointing somewhere else entirely.
    """
    parsed = GCSContentService.parse_gs_url(url)
    if parsed:
        path = media_path(*parsed)
        data = await asyncio.to_thread(path.read_bytes)
        return data, mimetypes.guess_type(path.name)[0] or ""
    async with httpx.AsyncClient(timeout=10) as http:
        resp = await http.get(url)
    if resp.status_code != 200:
        return b"", ""
    return resp.content, resp.headers.get("content-type", "").split(";", 1)[0].strip()


async def _cover_data_uri(podcast_name: str) -> str:
    """Show artwork as a data: URI, or "" if it cannot be had.

    Never raises: a cover without artwork is a perfectly good cover, and neither a
    missing file nor a failed fetch is a reason to fail the request — this endpoint is
    what the syndication crawlers hit, so it degrades rather than 500s.
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
        data, content_type = await _cover_bytes(url)
        if not data or not content_type.startswith("image/"):
            return ""
        if len(data) > _ART_MAX_BYTES:
            logger.info("og: artwork for %s too large (%d bytes)", podcast_name, len(data))
            return ""
        uri = f"data:{content_type};base64,{base64.b64encode(data).decode()}"
    except Exception as e:  # noqa: BLE001 — the cover degrades, it does not fail
        logger.info("og: artwork fetch failed for %s (%s)", podcast_name, e)
        return ""
    await cache_set(key, uri, ttl=_ART_CACHE_TTL)
    return uri


async def _episode_svg(episode_id: str) -> str:
    episode = await podcast_service.get_episode_admin(episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")
    podcast_name = (getattr(episode, "podcast_name", None) or "").strip()
    raw_title = (getattr(episode, "episode_title", None) or "").strip() or episode_id

    # The cover has to say what the post is called, so it is built from the same
    # syndication_title() the publishers use — reading episode_title directly meant the
    # cover said "EP684 | 🔦" while the post was "股癌 EP684 | 🔦 摘要". The show's name
    # is then dropped from the line because the kicker above it already carries it.
    short = podcast_short_name(podcast_name)
    full = syndication_title(podcast_name, raw_title)
    title = full[len(short):].strip() if short and full.startswith(short) else full

    return episode_cover_svg(title, kicker=short,
                             cover_data_uri=await _cover_data_uri(podcast_name))


@router.get("/episode/{episode_id}.svg")
async def episode_cover(episode_id: str) -> Response:
    """The cover as SVG. Kept because already-published articles reference this URL."""
    return Response(content=await _episode_svg(episode_id), media_type="image/svg+xml",
                    headers={"Cache-Control": _CACHE_CONTROL})


@router.get("/episode/{episode_id}.png")
async def episode_cover_raster(episode_id: str) -> Response:
    """The cover as PNG — what social crawlers need, since og:image ignores SVG.

    A failure here is loud on purpose. Serving the SVG instead would produce a 200 with
    a card that silently never renders, and silent success is the failure mode that has
    cost the most time on this integration.
    """
    svg = await _episode_svg(episode_id)
    try:
        png = await asyncio.to_thread(episode_cover_png, svg)
    except Exception as e:  # noqa: BLE001 — surfaced, never swapped for the SVG
        logger.exception("og: PNG rasterisation failed for %s", episode_id)
        raise HTTPException(status_code=500, detail=f"cover rasterisation failed: {e}") from e
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": _CACHE_CONTROL})
