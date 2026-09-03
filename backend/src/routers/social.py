"""Admin/service endpoints for publishing episode summaries to Threads.

The publish endpoint accepts the TINBOKER_SOCIAL_TOKEN service token as well as an
admin JWT, so the agents' podcast pipeline can call it right after an ingest run to
fan the new episode out to Threads. It is idempotent and dry-run by default.
"""

import asyncio
import logging
import mimetypes
import uuid
from datetime import datetime
from typing import List, Optional, Any

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.auth.admin_auth import AdminAccess, get_admin_access, get_social_access
from src.config import settings
from src.database.models import PromoDraft, ScheduledSocialPost
from src.database.postgres import get_session
from src.services import (facebook_publisher, promo_publisher, substack_publisher,
                          threads_publisher, vocus_publisher)
from src.services.content_source_service import social_enabled_for
from src.services.gcs_content import GCSContentService, media_url
from src.services.syndication_markdown import (podcast_short_name, syndication_excerpt,
                                               syndication_title)
from src.tag_registry import canonical_label
from src.services.podcast import PodcastService
from src.services.facebook_insights_service import (FacebookInsightsService,
                                                     recent_post_insights as facebook_recent_post_insights)
from src.services.threads_insights_service import ThreadsInsightsService
from src.services import threads_comments_service

_MAX_MEDIA_BYTES = 200 * 1024 * 1024  # 200 MB per file
_gcs = GCSContentService()

_PUBLISHERS = {"threads": threads_publisher, "facebook": facebook_publisher}

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/threads", tags=["admin", "social"])
# Facebook insights live under their own prefix (parallel to the threads endpoints).
facebook_router = APIRouter(prefix="/api/admin/facebook", tags=["admin", "social"])

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


def _social_off_result(platform: str, episode_id: str) -> dict:
    """The skip a muted show gets, in the shape every publish handler already renders."""
    return {"platform": platform, "episode_id": episode_id,
            "posted": False, "reason": "social_disabled_for_show"}


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


@router.get("/insights")
async def threads_insights(
    days: int = Query(default=28, ge=1, le=90),
    posts: int = Query(default=5, ge=0, le=25, description="How many recent posts to include"),
    _: AdminAccess = Depends(get_admin_access),
):
    """Threads engagement insights: account totals + per-post breakdown.

    Always 200 — when Threads isn't configured (or the API errors) the payload reports
    ``available: false`` so the admin UI shows a "not connected" state.
    """
    svc = ThreadsInsightsService()
    summary = await svc.account_summary(days=days)
    recent = await svc.recent_post_insights(limit=posts) if posts else []
    return {**summary, "recent_posts": recent}


@facebook_router.get("/insights")
async def facebook_insights(
    days: int = Query(default=28, ge=1, le=90),
    posts: int = Query(default=10, ge=0, le=25, description="How many recent posts to include"),
    _: AdminAccess = Depends(get_admin_access),
):
    """Facebook Page insights: audience, engagement totals, and per-post reach.

    Always 200 — when the page isn't configured (or the Graph API errors) the payload
    reports ``available: false`` so the admin UI shows a "not connected" state.
    ``recent_posts`` is what answers "is anyone seeing these"; it needs the
    ``read_insights`` scope and is an empty list without it.
    """
    summary = await FacebookInsightsService().account_summary(days=days)
    recent = await facebook_recent_post_insights(limit=posts) if posts else []
    return {**summary, "recent_posts": recent}


# ── Comment triage (replies people leave on our posts) ────────────────────────

class CommentReply(BaseModel):
    text: str = Field("", description="Reply body; defaults to the stored draft when empty")


@router.get("/comments")
def list_threads_comments(
    status: str = Query(default="pending", description="pending | replied | skipped | ignored | hidden | all"),
    limit: int = Query(default=50, ge=1, le=200),
    _: AdminAccess = Depends(get_admin_access),
):
    """Triaged comments on our Threads posts, newest first."""
    return {"comments": threads_comments_service.list_comments(status=status, limit=limit)}


@router.post("/comments/sync")
async def sync_threads_comments(
    scan_posts: int = Query(default=None, ge=1, le=100),
    _: AdminAccess = Depends(get_social_access),
):
    """Pull new comments, triage them, and auto-reply to the safe ones."""
    return await threads_comments_service.sync_and_triage(scan_posts=scan_posts)


@router.post("/comments/{comment_id}/reply")
async def reply_to_threads_comment(
    comment_id: str,
    body: CommentReply,
    _: AdminAccess = Depends(get_admin_access),
):
    """Post a reply to one comment — the edited draft, or the stored one when blank."""
    text = (body.text or "").strip()
    if not text:
        stored = threads_comments_service.list_comments(status="all", limit=200)
        match = next((c for c in stored if c["id"] == comment_id), None)
        text = (match or {}).get("draft") or ""
    try:
        return await threads_comments_service.send_reply(comment_id, text)
    except ValueError as e:
        raise HTTPException(status_code=404 if "unknown" in str(e) else 422, detail=str(e))


@router.post("/comments/{comment_id}/skip")
def skip_threads_comment(comment_id: str, _: AdminAccess = Depends(get_admin_access)):
    try:
        return threads_comments_service.set_status(comment_id, "skipped")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


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
        # The long-form summary, for the "copy for 方格子/Substack" action. Prefer the
        # human-edited version, same precedence the episode page uses.
        "summary_markdown": episode.modified_summary_content or episode.summary_content or "",
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


@router.get("/vocus/token-status")
async def vocus_token_status(_: AdminAccess = Depends(get_social_access)):
    """How long the 方格子 credential has left.

    It lives 7 days with no refresh endpoint, so the admin page shows this as a banner:
    the operator learns the token is dying while there is still time to replace it,
    rather than by noticing that nothing has published for a week. Reports *about* the
    token — expiry and configured-ness — never its value.
    """
    return vocus_publisher.token_status()


@router.post("/episodes/{episode_id}/publish-vocus")
async def publish_episode_to_vocus(
    episode_id: str,
    request: Request,
    dry_run: bool = Query(default=True, description="Convert only; do not publish (default)"),
    _: AdminAccess = Depends(get_social_access),
):
    """Publish one episode's long-form summary to 方格子.

    Separate from ``/publish`` because this is a different kind of thing: that one posts
    short social copy plus card images to Threads/Facebook, this one syndicates the whole
    article. Defaults to dry-run, which converts the markdown and reports the block count
    without creating anything.
    """
    episode = await podcast_service.get_episode_admin(episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")

    summary = getattr(episode, "modified_summary_content", None) or getattr(episode, "summary_content", None) or ""
    podcast_name = (getattr(episode, "podcast_name", None) or "").strip()
    raw_title = (getattr(episode, "episode_title", None) or "").strip() or episode_id
    title = syndication_title(podcast_name, raw_title)
    if not social_enabled_for(podcast_name):
        return _social_off_result("vocus", episode_id)

    # zh-TW labels, not raw slugs: a vocus reader searches 台股, never "twstocks", and the
    # podcast's own name leads so the post lands on the tag page its audience reads.
    labels = [canonical_label(t) for t in (getattr(episode, "tags", None) or []) if isinstance(t, str)]
    short = podcast_short_name(podcast_name)
    # The podcast name is attribution, not a topic — it sits outside the 5-topic budget so
    # naming the show never costs a subject tag.
    tags = list(dict.fromkeys(([short] if short else []) + labels[:5]))

    # Our own generated cover, not the show's artwork and not the episode's
    # summary_image. Borrowing the podcast's logo would make a summary look like the
    # podcast's own post, and summary_image is a "Placeholder Chart" SVG on every episode
    # checked. See services/og_image.py.
    thumbnail_url = f"{_public_base_url(request)}/api/og/episode/{episode_id}.png"

    return await vocus_publisher.publish_summary(
        episode_id,
        title,
        summary,
        podcast_name=podcast_name,
        # summary_excerpt is None on every episode checked, so derive the lead from the
        # summary itself rather than shipping an empty field.
        abstract=((getattr(episode, "summary_excerpt", None) or "").strip()
                  or syndication_excerpt(summary)),
        tags=tags,
        thumbnail_url=thumbnail_url,
        dry_run=dry_run,
    )


@router.post("/episodes/{episode_id}/draft-substack")
async def draft_episode_to_substack(
    episode_id: str,
    request: Request,
    dry_run: bool = Query(default=True, description="Convert only; do not create the draft (default)"),
    _: AdminAccess = Depends(get_social_access),
):
    """Stage one episode's summary as a Substack DRAFT.

    Named ``draft-`` rather than ``publish-`` because it deliberately stops short of
    publishing: on Substack that emails every subscriber the instant it succeeds and
    cannot be undone, so the final click stays human. The response carries the draft's
    edit URL to make that click one step away.
    """
    episode = await podcast_service.get_episode_admin(episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")

    summary = getattr(episode, "modified_summary_content", None) or getattr(episode, "summary_content", None) or ""
    podcast_name = (getattr(episode, "podcast_name", None) or "").strip()
    raw_title = (getattr(episode, "episode_title", None) or "").strip() or episode_id
    title = syndication_title(podcast_name, raw_title)
    if not social_enabled_for(podcast_name):
        return _social_off_result("substack", episode_id)

    return await substack_publisher.create_summary_draft(
        episode_id,
        title,
        summary,
        podcast_name=podcast_name,
        cover_image_url=f"{_public_base_url(request)}/api/og/episode/{episode_id}.png",
        send_email=False,
        subtitle=((getattr(episode, "summary_excerpt", None) or "").strip()
                  or syndication_excerpt(summary, limit=140)),
        dry_run=dry_run,
    )


@router.post("/episodes/{episode_id}/syndicate")
async def syndicate_episode(
    episode_id: str,
    request: Request,
    platforms: str = Query(default="vocus,substack", description="Comma list: vocus, substack"),
    dry_run: bool = Query(default=True, description="Convert only; create nothing (default)"),
    publish: bool = Query(default=False, description="vocus only: go public instead of staying a draft"),
    publish_substack: bool = Query(
        default=False,
        description="Substack only: publish to the web (never emails) instead of staying a draft",
    ),
    _: AdminAccess = Depends(get_social_access),
):
    """Stage one episode on every syndication target at once.

    Drafts on both by default. Reviewing the same summary on two platforms means opening
    two editors, and doing that from one action is the whole point — firing them
    separately guarantees the two copies drift while you fiddle.

    ``publish`` covers vocus, ``publish_substack`` covers Substack. Separate switches on
    purpose: turning one on should never quietly turn the other on.

    Publishing to Substack here NEVER emails subscribers — the publisher hard-wires
    ``send_email: false`` and exposes no way to change it. A web-only post can be taken
    down; a newsletter cannot be recalled.

    Each platform reports independently. One failing does not roll back or block the
    other — two half-finished drafts you can see beat one silent skip.
    """
    selected = [p.strip().lower() for p in platforms.split(",") if p.strip()]
    unknown = [p for p in selected if p not in ("vocus", "substack")]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown platform(s): {', '.join(unknown)}")
    if not selected:
        raise HTTPException(status_code=422, detail="No platforms selected")

    episode = await podcast_service.get_episode_admin(episode_id)
    if not episode:
        raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")

    summary = getattr(episode, "modified_summary_content", None) or getattr(episode, "summary_content", None) or ""
    podcast_name = (getattr(episode, "podcast_name", None) or "").strip()
    raw_title = (getattr(episode, "episode_title", None) or "").strip() or episode_id
    title = syndication_title(podcast_name, raw_title)
    if not social_enabled_for(podcast_name):
        return {"episode_id": episode_id, "title": title,
                "platforms": {p: _social_off_result(p, episode_id) for p in selected}}
    excerpt = ((getattr(episode, "summary_excerpt", None) or "").strip()
               or syndication_excerpt(summary))

    async def _vocus() -> dict:
        labels = [canonical_label(t) for t in (getattr(episode, "tags", None) or []) if isinstance(t, str)]
        short = podcast_short_name(podcast_name)
        tags = list(dict.fromkeys(([short] if short else []) + labels[:5]))
        return await vocus_publisher.publish_summary(
            episode_id, title, summary, podcast_name=podcast_name, abstract=excerpt,
            tags=tags,
            thumbnail_url=f"{_public_base_url(request)}/api/og/episode/{episode_id}.png",
            as_draft=not publish, dry_run=dry_run,
        )

    async def _substack() -> dict:
        return await substack_publisher.create_summary_draft(
            episode_id, title, summary, podcast_name=podcast_name,
            subtitle=excerpt[:140],
            # The same cover both platforms show, so one summary does not look like two.
            cover_image_url=f"{_public_base_url(request)}/api/og/episode/{episode_id}.png",
            # Never primed to mail the list. Publishing web-only is reversible; an email
            # is not, and that choice stays with whoever clicks Publish.
            send_email=False,
            # The pipeline has sent publish_substack=true since Step 5f shipped, but the
            # endpoint silently dropped the unknown query param — every "published"
            # episode was actually a draft nobody saw.
            publish=publish_substack,
            dry_run=dry_run,
        )

    runners = {"vocus": _vocus, "substack": _substack}
    settled = await asyncio.gather(*(runners[p]() for p in selected), return_exceptions=True)

    results: dict[str, Any] = {}
    for name, outcome in zip(selected, settled):
        if isinstance(outcome, BaseException):
            logger.exception("syndicate: %s failed for %s", name, episode_id)
            results[name] = {"platform": name, "posted": False, "reason": f"error: {outcome}"}
        else:
            results[name] = outcome
    return {"episode_id": episode_id, "title": title, "platforms": results}


def _public_base_url(request: Request) -> str:
    """The origin an outside fetcher should use to reach this API.

    Derived from the request rather than configured: a setting has one value across dev,
    staging and production, so the dev backend handed vocus a production URL for an
    endpoint production did not have yet — a 404 and a broken thumbnail. Behind Cloudflare
    the forwarded headers carry the public host; settings.public_api_url is the last
    resort for callers that arrive without them.
    """
    proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    host = request.headers.get("x-forwarded-host", "").split(",")[0].strip()
    if host:
        return f"{proto or 'https'}://{host}"
    base = str(request.base_url).rstrip("/")
    if base and "localhost" not in base and "127.0.0.1" not in base:
        return base
    return settings.public_api_url.rstrip("/")


def _marp_size(marp_markdown: str) -> str:
    """Pull the ``size:`` directive (e.g. ``1:1``) so the editor can size the preview."""
    for line in marp_markdown.splitlines():
        s = line.strip()
        if s.startswith("size:"):
            return s.split(":", 1)[1].strip()
    return "1:1"


# ── Free-form promo posts (operator-authored text + media → Threads/Facebook) ──────
# Distinct from the episode flow above: no LLM, no idempotency. The operator writes
# everything; media is written to the VPS media store here and handed to Meta as a
# public URL at publish time (P5: GCS is gone, so is signing).
promo_router = APIRouter(prefix="/api/admin/promo", tags=["admin", "social"])


class PromoMedia(BaseModel):
    type: str = Field(..., description="'image' or 'video'")
    url: Optional[str] = Field(None, description="Public URL Meta can fetch (publish); resolved on draft load")
    path: Optional[str] = Field(None, description="Durable media location (persisted in drafts)")
    filename: Optional[str] = None


class PromoPublishBody(BaseModel):
    text: str = Field("", description="The full post text (operator-authored)")
    media: List[PromoMedia] = Field(default_factory=list)
    comments: List[str] = Field(default_factory=list, description="Text-only follow-up comments/replies")
    platforms: List[str] = Field(default_factory=lambda: ["threads", "facebook"])
    dry_run: bool = Field(True, description="Plan only; do not post (default)")


# guess_extension picks ugly-but-valid aliases for these; pin the conventional ones.
_CTYPE_EXT = {"image/jpeg": ".jpg", "video/mp4": ".mp4", "video/quicktime": ".mov"}

# Active content served from the media origin would be stored XSS — Caddy sets
# Content-Type from the extension, so an .html or .svg lands as a scriptable
# document on podcast-api.tinboker.com. SVG passes the image/* check, so reject it
# by name rather than relying on the image/ prefix.
_BLOCKED_CTYPES = {"image/svg+xml", "image/svg"}


def _safe_extension(ctype: str) -> str:
    """File extension derived from the *validated* content type.

    The client filename is never consulted: it is attacker-controlled, and the
    extension is what decides how the media origin serves the bytes back.
    """
    if ctype in _BLOCKED_CTYPES:
        raise HTTPException(status_code=415, detail=f"Unsupported media type: {ctype}")
    ext = _CTYPE_EXT.get(ctype) or mimetypes.guess_extension(ctype)
    if not ext or ext in (".html", ".htm", ".svg", ".xml"):
        raise HTTPException(status_code=415, detail=f"Unsupported media type: {ctype}")
    return ext


@promo_router.post("/media")
async def upload_promo_media(
    file: UploadFile = File(...),
    _: AdminAccess = Depends(get_admin_access),
):
    """Upload one image/video for a promo post; returns its type + its public URL.

    ponytail: the media store is served publicly, so the URL never expires and
    ``path``/``url`` are the same string — kept as two fields so stored drafts and
    the composer need no migration.
    """
    ctype = (file.content_type or "").lower().split(";", 1)[0].strip()
    if ctype.startswith("image/"):
        mtype = "image"
    elif ctype.startswith("video/"):
        mtype = "video"
    else:
        raise HTTPException(status_code=415, detail="Only image/* or video/* files are supported")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > _MAX_MEDIA_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 200 MB)")

    name = file.filename or ""
    ext = _safe_extension(ctype)
    bucket = settings.promo_media_bucket
    blob_path = f"promo-media/{uuid.uuid4().hex}{ext}"
    try:
        await _gcs.upload_bytes(bucket, blob_path, data, ctype)
    except Exception as e:  # noqa: BLE001 — surface any storage failure as a 502
        logger.exception("promo media upload failed")
        raise HTTPException(status_code=502, detail=f"Upload failed: {e}")
    url = media_url(bucket, blob_path)
    return {"type": mtype, "url": url, "path": url, "filename": name}


@promo_router.post("/publish")
async def publish_promo_post(
    body: PromoPublishBody,
    _: AdminAccess = Depends(get_admin_access),
):
    """Publish one operator-authored promo to the selected platforms.

    Dry-run by default (returns the per-platform plan). Each platform is independent:
    a Facebook block (e.g. mixed photo+video) never stops the Threads post.
    """
    platforms = [p.strip().lower() for p in body.platforms if p.strip()]
    bad = [p for p in platforms if p not in _PUBLISHERS]
    if bad:
        raise HTTPException(status_code=422, detail=f"Unknown platform(s): {', '.join(bad)}")
    if not platforms:
        raise HTTPException(status_code=422, detail="No platforms selected")

    media = [m.model_dump() for m in body.media]
    for m in media:
        if m["type"] not in ("image", "video"):
            raise HTTPException(status_code=422, detail=f"Bad media type: {m['type']}")
        if not m.get("url"):
            raise HTTPException(status_code=422, detail="Each media item needs a url to publish")

    return await promo_publisher.publish_promo(
        body.text, media, platforms, comments=body.comments, dry_run=body.dry_run
    )


# ── Promo drafts (durable, server-side; media URLs resolved on load) ───────────

class PromoDraftBody(BaseModel):
    name: str = Field("未命名草稿", max_length=200)
    text: str = ""
    media: List[PromoMedia] = Field(default_factory=list)
    comments: List[str] = Field(default_factory=list)
    platforms: List[str] = Field(default_factory=lambda: ["threads", "facebook"])


def _store_media(media: List[PromoMedia]) -> list:
    """Persist only the durable parts ({type, path, filename})."""
    return [
        {"type": m.type, "path": m.path, "filename": m.filename}
        for m in media if m.path
    ]


async def _resign_media(stored: list) -> list:
    """Resolve each stored media path into a fetchable URL for the composer/preview.

    Historical drafts hold ``gs://`` paths; ``generate_signed_url`` maps those onto
    the media store and returns the public URL (None when the file is gone).
    """
    out = []
    for m in stored or []:
        url = None
        if m.get("path"):
            try:
                url = await _gcs.generate_signed_url(m["path"])
            except Exception as e:  # noqa: BLE001 — a missing artifact shouldn't 500 the load
                logger.warning("promo draft media resolve failed for %s: %s", m.get("path"), e)
        out.append({"type": m.get("type"), "url": url, "path": m.get("path"), "filename": m.get("filename")})
    return out


@promo_router.get("/drafts")
def list_promo_drafts(_: AdminAccess = Depends(get_admin_access), db: Session = Depends(get_session)):
    """List saved promo drafts (metadata only; newest first)."""
    rows = db.query(PromoDraft).order_by(PromoDraft.updated_at.desc()).all()
    return {"drafts": [
        {
            "id": r.id, "name": r.name,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            "media_count": len(r.media or []), "comment_count": len(r.comments or []),
            "platforms": r.platforms or [],
        }
        for r in rows
    ]}


@promo_router.get("/drafts/{draft_id}")
async def get_promo_draft(
    draft_id: int,
    _: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    """One draft, with each stored media path resolved to a fetchable URL."""
    row = db.query(PromoDraft).filter(PromoDraft.id == draft_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Draft not found")
    return {
        "id": row.id, "name": row.name, "text": row.text or "",
        "media": await _resign_media(row.media), "comments": row.comments or [],
        "platforms": row.platforms or [],
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@promo_router.post("/drafts", status_code=201)
def create_promo_draft(
    body: PromoDraftBody,
    admin: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    """Save a new promo draft. Returns its id."""
    row = PromoDraft(
        name=(body.name or "").strip() or "未命名草稿",
        text=body.text or "",
        media=_store_media(body.media),
        comments=[c for c in body.comments],
        platforms=body.platforms,
        updated_by=admin.email,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name}


@promo_router.put("/drafts/{draft_id}")
def update_promo_draft(
    draft_id: int,
    body: PromoDraftBody,
    admin: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    """Overwrite an existing draft."""
    row = db.query(PromoDraft).filter(PromoDraft.id == draft_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Draft not found")
    row.name = (body.name or "").strip() or "未命名草稿"
    row.text = body.text or ""
    row.media = _store_media(body.media)
    row.comments = [c for c in body.comments]
    row.platforms = body.platforms
    row.updated_by = admin.email
    db.commit()
    return {"id": row.id, "name": row.name}


@promo_router.delete("/drafts/{draft_id}", status_code=204)
def delete_promo_draft(
    draft_id: int,
    _: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    """Delete a draft."""
    row = db.query(PromoDraft).filter(PromoDraft.id == draft_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Draft not found")
    db.delete(row)
    db.commit()


# ── Scheduled posts management ───────────────────────────────────────────

class SchedulePostRequest(BaseModel):
    post_type: str = Field(..., description="'episode' or 'promo'")
    episode_id: Optional[str] = None
    text: Optional[str] = ""
    media: Optional[List[PromoMedia]] = None
    comments: Optional[List[Any]] = None  # Support string comments for promos or dict comments for episodes
    platforms: List[str]
    scheduled_for: datetime


@router.post("/scheduled", status_code=201)
def schedule_post(
    body: SchedulePostRequest,
    admin: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    """Schedule a social media post (episode summary or promo)."""
    if body.post_type not in ("episode", "promo"):
        raise HTTPException(status_code=422, detail="post_type must be 'episode' or 'promo'")
    if body.post_type == "episode" and not body.episode_id:
        raise HTTPException(status_code=422, detail="episode_id is required for 'episode' post_type")

    # Store media cleanly (durable part only; path is what persists)
    stored_media = []
    if body.media:
        stored_media = [
            {"type": m.type, "path": m.path, "filename": m.filename}
            for m in body.media if m.path
        ]

    row = ScheduledSocialPost(
        post_type=body.post_type,
        episode_id=body.episode_id,
        text=(body.text or "").strip(),
        media=stored_media,
        comments=body.comments or [],
        platforms=body.platforms,
        scheduled_for=body.scheduled_for,
        status="pending",
        created_by=admin.email
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "status": row.status}


@router.get("/scheduled")
def list_scheduled_posts(
    status: Optional[str] = Query(None, description="pending, processing, posted, failed"),
    limit: int = Query(default=50, ge=1, le=100),
    _: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    """List scheduled social posts, sorted by scheduled_for desc."""
    query = db.query(ScheduledSocialPost)
    if status:
        query = query.filter(ScheduledSocialPost.status == status)
    rows = query.order_by(ScheduledSocialPost.scheduled_for.desc()).limit(limit).all()

    return {"posts": [
        {
            "id": r.id,
            "post_type": r.post_type,
            "episode_id": r.episode_id,
            "text": r.text,
            "media": r.media,
            "comments": r.comments,
            "platforms": r.platforms,
            "scheduled_for": r.scheduled_for.isoformat() + "Z",  # ensure Z/UTC suffix for frontend
            "status": r.status,
            "error_message": r.error_message,
            "posted_at": r.posted_at.isoformat() + "Z" if r.posted_at else None,
            "published_results": r.published_results,
            "created_by": r.created_by,
            "created_at": r.created_at.isoformat() + "Z"
        }
        for r in rows
    ]}


@router.delete("/scheduled/{post_id}", status_code=204)
def delete_scheduled_post(
    post_id: int,
    _: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    """Cancel and delete a scheduled post."""
    row = db.query(ScheduledSocialPost).filter(ScheduledSocialPost.id == post_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Scheduled post not found")
    if row.status == "processing":
        raise HTTPException(status_code=400, detail="Cannot delete a post that is currently processing")
    db.delete(row)
    db.commit()


@router.post("/scheduled/{post_id}/publish-now")
async def publish_scheduled_post_now(
    post_id: int,
    _: AdminAccess = Depends(get_admin_access),
    db: Session = Depends(get_session),
):
    """Manually trigger a scheduled post to publish immediately."""
    row = db.query(ScheduledSocialPost).filter(ScheduledSocialPost.id == post_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Scheduled post not found")
    if row.status in ("processing", "posted"):
        raise HTTPException(status_code=400, detail=f"Cannot publish post that is {row.status}")

    row.status = "pending"
    row.scheduled_for = datetime.utcnow()
    db.commit()

    from src.services.scheduled_social_worker import process_scheduled_posts
    await process_scheduled_posts()

    db.refresh(row)
    return {
        "id": row.id,
        "status": row.status,
        "error_message": row.error_message,
        "published_results": row.published_results
    }

