"""Podcast show registry API — CRUD for the list of shows the pipeline monitors.

Reads are open; writes require X-API-Key.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from shared.wiki_builder import PodcastShow, get_show_repository
from shared.wiki_builder.shows import PostgresShowRepository

from ..auth import verify_api_key

router = APIRouter(prefix="/api/shows", tags=["shows"])

_repo: PostgresShowRepository | None = None


def get_repo() -> PostgresShowRepository:
    global _repo
    if _repo is None:
        _repo = get_show_repository()
    if _repo is None:
        raise HTTPException(status_code=503, detail="Show registry unavailable (no WIKI_DATABASE_URL)")
    return _repo


# --- Pydantic models ---

class ShowOut(BaseModel):
    slug: str
    name: str
    rss_url: str
    spotify_url: str | None
    episode_limit: int
    active: bool
    created_at: str | None
    updated_at: str | None

    @classmethod
    def from_show(cls, s: PodcastShow) -> "ShowOut":
        return cls(
            slug=s.slug,
            name=s.name,
            rss_url=s.rss_url,
            spotify_url=s.spotify_url,
            episode_limit=s.episode_limit,
            active=s.active,
            created_at=s.created_at.isoformat() if s.created_at else None,
            updated_at=s.updated_at.isoformat() if s.updated_at else None,
        )


class ShowIn(BaseModel):
    name: str
    rss_url: str
    spotify_url: str | None = None
    episode_limit: int = Field(default=10, ge=1)
    active: bool = True


class ActivePatch(BaseModel):
    active: bool


# --- Routes ---

@router.get("", response_model=list[ShowOut])
def list_shows(active_only: bool = False, repo: PostgresShowRepository = Depends(get_repo)):
    """List all podcast shows. Pass ?active_only=true to filter to active shows only."""
    return [ShowOut.from_show(s) for s in repo.list_shows(active_only=active_only)]


@router.get("/{slug}", response_model=ShowOut)
def get_show(slug: str, repo: PostgresShowRepository = Depends(get_repo)):
    show = repo.get_show(slug)
    if show is None:
        raise HTTPException(status_code=404, detail=f"Show '{slug}' not found")
    return ShowOut.from_show(show)


@router.put("/{slug}", response_model=ShowOut, dependencies=[Depends(verify_api_key)])
def upsert_show(slug: str, body: ShowIn, repo: PostgresShowRepository = Depends(get_repo)):
    """Create or update a show. Slug is derived from the URL path."""
    show = PodcastShow(
        slug=slug,
        name=body.name,
        rss_url=body.rss_url,
        spotify_url=body.spotify_url,
        episode_limit=body.episode_limit,
        active=body.active,
    )
    return ShowOut.from_show(repo.upsert_show(show))


@router.patch("/{slug}", response_model=ShowOut, dependencies=[Depends(verify_api_key)])
def set_active(slug: str, body: ActivePatch, repo: PostgresShowRepository = Depends(get_repo)):
    """Activate or deactivate a show without touching other fields."""
    show = repo.set_active(slug, body.active)
    if show is None:
        raise HTTPException(status_code=404, detail=f"Show '{slug}' not found")
    return ShowOut.from_show(show)


@router.delete("/{slug}", dependencies=[Depends(verify_api_key)])
def delete_show(slug: str, repo: PostgresShowRepository = Depends(get_repo)):
    if not repo.delete_show(slug):
        raise HTTPException(status_code=404, detail=f"Show '{slug}' not found")
    return {"deleted": slug}
