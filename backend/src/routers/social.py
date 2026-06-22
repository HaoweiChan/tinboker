"""Admin/service endpoints for publishing episode summaries to Threads.

The publish endpoint accepts the TINBOKER_SOCIAL_TOKEN service token as well as an
admin JWT, so the agents' podcast pipeline can call it right after an ingest run to
fan the new episode out to Threads. It is idempotent and dry-run by default.
"""

import logging
import uuid
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.auth.admin_auth import AdminAccess, get_admin_access, get_social_access
from src.config import settings
from src.database.models import PromoDraft
from src.database.postgres import get_session
from src.services import facebook_publisher, promo_publisher, threads_publisher
from src.services.gcs_content import GCSContentService
from src.services.podcast import PodcastService
from src.services.facebook_insights_service import FacebookInsightsService
from src.services.threads_insights_service import ThreadsInsightsService

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
    _: AdminAccess = Depends(get_admin_access),
):
    """Facebook Page insights: audience (fans/followers) + engagement totals.

    Always 200 — when the page isn't configured (or the Graph API errors) the payload
    reports ``available: false`` so the admin UI shows a "not connected" state.
    """
    return await FacebookInsightsService().account_summary(days=days)


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


# ── Free-form promo posts (operator-authored text + media → Threads/Facebook) ──────
# Distinct from the episode flow above: no LLM, no idempotency. The operator writes
# everything; media is uploaded here, stored private in GCS, and handed to Meta as a
# short-lived signed URL at publish time.
promo_router = APIRouter(prefix="/api/admin/promo", tags=["admin", "social"])


class PromoMedia(BaseModel):
    type: str = Field(..., description="'image' or 'video'")
    url: Optional[str] = Field(None, description="Signed URL Meta can fetch (publish); re-signed on draft load")
    path: Optional[str] = Field(None, description="Durable gs:// location (persisted in drafts)")
    filename: Optional[str] = None


class PromoPublishBody(BaseModel):
    text: str = Field("", description="The full post text (operator-authored)")
    media: List[PromoMedia] = Field(default_factory=list)
    comments: List[str] = Field(default_factory=list, description="Text-only follow-up comments/replies")
    platforms: List[str] = Field(default_factory=lambda: ["threads", "facebook"])
    dry_run: bool = Field(True, description="Plan only; do not post (default)")


@promo_router.post("/media")
async def upload_promo_media(
    file: UploadFile = File(...),
    _: AdminAccess = Depends(get_admin_access),
):
    """Upload one image/video for a promo post; returns its type + a signed URL.

    The signed URL is valid for 12h — long enough to compose and publish in one
    session. ``ponytail: 12h window; regenerate from the gs:// path if drafts ever
    need to outlive that.``
    """
    ctype = (file.content_type or "").lower()
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
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else (ctype.split("/", 1)[-1] or mtype)
    bucket = settings.promo_media_bucket
    blob_path = f"promo-media/{uuid.uuid4().hex}.{ext}"
    gs_url = f"gs://{bucket}/{blob_path}"
    try:
        await _gcs.upload_bytes(bucket, blob_path, data, ctype)
        url = await _gcs.generate_signed_url(gs_url, expiration_hours=12)
    except Exception as e:  # noqa: BLE001 — surface any GCS failure as a 502
        logger.exception("promo media upload failed")
        raise HTTPException(status_code=502, detail=f"Upload failed: {e}")
    if not url:
        raise HTTPException(status_code=502, detail="Could not sign media URL (SA key unavailable)")
    # ``path`` (the gs:// location) is what drafts persist — the signed ``url`` expires.
    return {"type": mtype, "url": url, "path": gs_url, "filename": name}


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


# ── Promo drafts (durable, server-side; media re-signed on load) ────────────────

class PromoDraftBody(BaseModel):
    name: str = Field("未命名草稿", max_length=200)
    text: str = ""
    media: List[PromoMedia] = Field(default_factory=list)
    comments: List[str] = Field(default_factory=list)
    platforms: List[str] = Field(default_factory=lambda: ["threads", "facebook"])


def _store_media(media: List[PromoMedia]) -> list:
    """Persist only the durable parts ({type, path, filename}); the signed url expires."""
    return [
        {"type": m.type, "path": m.path, "filename": m.filename}
        for m in media if m.path
    ]


async def _resign_media(stored: list) -> list:
    """Re-sign each stored gs:// path into a fresh 12h URL for the composer/preview."""
    out = []
    for m in stored or []:
        url = None
        if m.get("path"):
            try:
                url = await _gcs.generate_signed_url(m["path"], expiration_hours=12)
            except Exception as e:  # noqa: BLE001 — a missing blob shouldn't 500 the load
                logger.warning("promo draft media re-sign failed for %s: %s", m.get("path"), e)
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
    """One draft, with media re-signed to fresh URLs (the stored signed URLs expire)."""
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
