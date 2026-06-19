"""Admin/service endpoints for publishing episode summaries to Threads.

The publish endpoint accepts the TINBOKER_SOCIAL_TOKEN service token as well as an
admin JWT, so the agents' podcast pipeline can call it right after an ingest run to
fan the new episode out to Threads. It is idempotent and dry-run by default.
"""

import logging
from typing import List

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.auth.admin_auth import AdminAccess, get_admin_access, get_social_access
from src.config import settings
from src.services import facebook_publisher, threads_publisher
from src.services.podcast import PodcastService

_PUBLISHERS = {"threads": threads_publisher, "facebook": facebook_publisher}

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/threads", tags=["admin", "social"])

podcast_service = PodcastService()


class SocialComment(BaseModel):
    heading: str = Field("", description="The theme card this comment maps to")
    text: str = Field("", description="The comment body (human-tone, plain text)")


class SocialThreadPatch(BaseModel):
    post: str = Field("", description="Grand-summary post")
    comments: List[SocialComment] = Field(default_factory=list, description="One per theme card")


def _theme_cards(episode) -> list:
    return [c for c in (episode.social_cards or []) if isinstance(c, dict) and c.get("kind") == "theme"]


def _parse_platforms(platforms: str) -> list[str]:
    """Validate + normalise a comma list of platform names."""
    selected = [p.strip().lower() for p in platforms.split(",") if p.strip()]
    bad = [p for p in selected if p not in _PUBLISHERS]
    if bad:
        raise HTTPException(status_code=422, detail=f"Unknown platform(s): {', '.join(bad)}")
    if not selected:
        raise HTTPException(status_code=422, detail="No platforms selected")
    return selected


def _posted_status(episode_id: str) -> dict:
    """Whether this episode has already been posted, per platform (idempotency ledgers)."""
    return {name: pub.already_posted(episode_id) for name, pub in _PUBLISHERS.items()}


def _social_list_item(episode, posted_sets: dict[str, set]) -> dict:
    thread = episode.social_thread if isinstance(episode.social_thread, dict) else {}
    themes = _theme_cards(episode)
    return {
        "episode_id": episode.id,
        "podcast_name": episode.podcast_name,
        "episode_title": episode.episode_title,
        "released_at_ms": episode.released_at_ms or episode.created_time,
        "theme_card_count": len(themes),
        "has_copy": bool((thread.get("post") or "").strip()),
        "comment_count": len([c for c in (thread.get("comments") or []) if (c or {}).get("text")]),
        "has_images": any(c.get("image_url") for c in themes),
        "posted": {name: episode.id in ids for name, ids in posted_sets.items()},
    }


@router.post("/publish")
async def publish_social(
    dry_run: bool = Query(default=True, description="Compose only; do not post (default)"),
    limit: int = Query(default=10, ge=1, le=50, description="How many recent episodes to scan"),
    max_age_days: int = Query(
        default=None,
        ge=0,
        description="Only post episodes published within N days (default: configured threads_max_age_days)",
    ),
    platforms: str = Query(
        default="threads,facebook",
        description="Comma list of platforms to publish to (threads, facebook).",
    ),
    _: AdminAccess = Depends(get_social_access),
):
    """Scan recent episodes and post any not-yet-posted ones to the given platforms.

    Defaults to dry-run (returns the composed drafts). Pass ``dry_run=false`` to
    actually publish. Each platform is independently idempotent and is forced to
    dry-run when its credentials are unconfigured. Returns one result per platform.
    """
    selected = _parse_platforms(platforms)

    results = {}
    for name in selected:
        try:
            results[name] = await _PUBLISHERS[name].publish_recent(
                limit=limit, dry_run=dry_run, max_age_days=max_age_days
            )
        except Exception as e:
            logger.exception("%s publish run failed", name)
            results[name] = {"platform": name, "error": str(e)}
    return {"platforms": results}


@router.get("/posts")
async def list_social_posts(
    limit: int = Query(default=50, ge=1, le=200),
    platform: str = Query(default="threads", description="threads or facebook"),
    _: AdminAccess = Depends(get_admin_access),
):
    """List episodes already posted to a platform (its idempotency ledger)."""
    pub = _PUBLISHERS.get(platform.strip().lower())
    if not pub:
        raise HTTPException(status_code=422, detail=f"Unknown platform: {platform}")
    return {"platform": platform, "posts": pub.list_posted(limit=limit)}


# ── Social copy management (the human-tone post + per-theme comments) ──────────

@router.get("/episodes")
async def list_social_episodes(
    limit: int = Query(default=30, ge=1, le=100),
    _: AdminAccess = Depends(get_admin_access),
):
    """Recent episodes with their social-copy readiness, for the admin editor."""
    episodes = await podcast_service.get_recent_episodes(limit=limit, enrich_content=False)
    # One ledger read per platform (not per episode): the set of already-posted ids.
    posted_sets = {
        name: {p["episode_id"] for p in pub.list_posted(limit=200)}
        for name, pub in _PUBLISHERS.items()
    }
    return {"episodes": [_social_list_item(e, posted_sets) for e in episodes]}


@router.get("/episodes/{episode_id}")
async def get_social_episode(
    episode_id: str,
    _: AdminAccess = Depends(get_admin_access),
):
    """The editable social bundle for one episode: the stored post + comments
    (seeded from the theme cards when empty), the marp deck markdown for an
    in-browser card preview, and the composed thread that would actually post."""
    episode = await podcast_service.get_episode_admin(episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")

    thread = episode.social_thread if isinstance(episode.social_thread, dict) else {}
    themes = _theme_cards(episode)
    stored_comments = [c for c in (thread.get("comments") or []) if isinstance(c, dict)]
    # Seed one comment slot per theme card when nothing is stored yet, so the
    # editor always shows the full set aligned to the slides.
    if stored_comments:
        comments = [{"heading": c.get("heading", ""), "text": c.get("text", "")} for c in stored_comments]
    else:
        comments = [{"heading": (c.get("title") or "").strip(), "text": ""} for c in themes]

    return {
        "episode_id": episode.id,
        "podcast_name": episode.podcast_name,
        "episode_title": episode.episode_title,
        "post": thread.get("post") or "",
        "comments": comments,
        "theme_cards": [
            {"heading": (c.get("title") or "").strip(), "bullets": c.get("bullets") or [], "image_url": c.get("image_url")}
            for c in themes
        ],
        "marp_markdown": episode.marp_markdown_content or "",
        "marp_size": _marp_size(episode.marp_markdown_content or ""),
        "composed": threads_publisher.compose_thread(episode),
        "has_copy": bool((thread.get("post") or "").strip()),
        "posted": _posted_status(episode.id),
    }


@router.patch("/episodes/{episode_id}")
async def save_social_episode(
    episode_id: str,
    body: SocialThreadPatch,
    _: AdminAccess = Depends(get_admin_access),
):
    """Save the human-tone post + comments for an episode."""
    thread = {"post": body.post.strip(), "comments": [c.model_dump() for c in body.comments]}
    episode = await podcast_service.set_social_thread(episode_id, thread)
    return {"episode_id": episode.id, "social_thread": episode.social_thread}


@router.post("/episodes/{episode_id}/social-copy")
async def generate_social_episode(
    episode_id: str,
    _: AdminAccess = Depends(get_admin_access),
):
    """Generate the social copy for an episode on demand, then persist it.

    The platform API has no LLM, so this proxies to the podcast pipeline service
    (which runs the ``social_copy_writer`` Gemini node) and persists the returned
    copy through the normal ``social_thread`` write path (Firestore + cache bust).
    Overwrites any existing copy; the admin then edits + saves via the PATCH above.
    """
    base = (settings.netcup_api_url or "").rstrip("/")
    if not base:
        raise HTTPException(status_code=503, detail="Pipeline service URL is not configured")
    headers = {"X-API-Key": settings.podcast_api_key} if settings.podcast_api_key else {}

    # Bound connection setup tightly (fail fast if the pipeline URL is wrong/down)
    # but allow a long read — the Gemini generation itself can take tens of seconds.
    timeout = httpx.Timeout(120.0, connect=5.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{base}/api/podcast/episodes/{episode_id}/social-copy",
                headers=headers,
            )
    except httpx.HTTPError as e:
        logger.warning("social-copy pipeline call failed for %s: %r", episode_id, e)
        raise HTTPException(status_code=502, detail=f"Pipeline service unreachable: {e!r}")

    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")
    if resp.status_code >= 400:
        logger.warning("pipeline social-copy %s -> %s: %s", episode_id, resp.status_code, resp.text[:300])
        raise HTTPException(
            status_code=502,
            detail=f"Social copy generation failed (pipeline {resp.status_code}).",
        )

    data = resp.json()
    thread = {
        "post": (data.get("post") or "").strip(),
        "comments": [
            {"heading": c.get("heading", ""), "text": c.get("text", "")}
            for c in (data.get("comments") or [])
        ],
    }
    episode = await podcast_service.set_social_thread(episode_id, thread)
    return {
        "episode_id": episode.id,
        "post": thread["post"],
        "comments": thread["comments"],
        "social_thread": episode.social_thread,
    }


@router.post("/episodes/{episode_id}/publish")
async def publish_social_episode(
    episode_id: str,
    dry_run: bool = Query(default=True, description="Compose only; do not post (default)"),
    platforms: str = Query(
        default="threads,facebook",
        description="Comma list of platforms to publish to (threads, facebook).",
    ),
    _: AdminAccess = Depends(get_social_access),
):
    """Publish ONE episode (the admin's edited copy) to the selected platforms.

    Defaults to dry-run (returns the composed draft per platform). Pass
    ``dry_run=false`` to actually post. Each platform is independently idempotent
    (skips if already posted) and forced to dry-run when its credentials are unset.
    """
    selected = _parse_platforms(platforms)
    episode = await podcast_service.get_episode_admin(episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")

    results = {}
    for name in selected:
        try:
            results[name] = await _PUBLISHERS[name].publish_episode(episode, dry_run=dry_run)
        except Exception as e:
            logger.exception("%s publish failed for %s", name, episode_id)
            results[name] = {"platform": name, "error": str(e)}
    return {"episode_id": episode_id, "platforms": results}


def _marp_size(marp_markdown: str) -> str:
    """Pull the ``size:`` directive (e.g. ``1:1``) so the editor can size the preview."""
    for line in marp_markdown.splitlines():
        s = line.strip()
        if s.startswith("size:"):
            return s.split(":", 1)[1].strip()
    return "1:1"
