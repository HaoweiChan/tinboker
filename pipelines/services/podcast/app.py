"""FastAPI application for Podcast Downloader API."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from shared.config import load_yaml_config

# Pull secrets from Google Secret Manager into os.environ before any
# router/service module that calls os.getenv() at import time.
from src.secrets_bootstrap import bootstrap

bootstrap()

from src.routers import episode, podcast, shows, wiki  # noqa: E402, I001
from src.routers.content import (  # noqa: E402, I001
    episode_router as content_episode_router,
    insights_router,
    podcast_router as content_podcast_router,
    tags_router,
)

app = FastAPI(
    title="Podcast Downloader API",
    description="API for managing podcast episode processing",
    version="1.0.0"
)

# Configure CORS to allow all origins (for testing with public URLs)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(episode.router)
app.include_router(podcast.router)
app.include_router(wiki.router)
app.include_router(shows.router)
# Postgres-backed content API (Phase D)
app.include_router(content_podcast_router)
app.include_router(content_episode_router)
app.include_router(insights_router)
app.include_router(tags_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Podcast Downloader API",
        "version": "1.0.0",
        "endpoints": {
            "podcast_shows": "/api/podcast/shows (GET - all shows with thumbnails)",
            "podcast_show": "/api/podcast/shows/{podcast_name} (GET - single show metadata)",
            "rerun_summarize_post": "/api/episodes/rerun-summarize (POST with JSON body: {\"episode_id\": \"<episode_id>\"})",
            "rerun_summarize_get": "/api/episodes/rerun-summarize/{episode_id} (GET)",
            "wiki_pages": "/api/wiki/pages (list; GET/PUT/DELETE /api/wiki/pages/{kind}/{slug})",
            "wiki_index": "/api/wiki/index (GET - knowledge wiki index; ?format=md for markdown)",
            "health": "/health",
            "docs": "/docs"
        }
    }


@app.get("/health")
async def health():
    """Global health check endpoint."""
    return {"status": "healthy"}


@app.get("/api/config")
async def get_config():
    """Read-only: the effective podcast pipeline configuration (configs/default.yaml).

    Non-secret deployment constants only — secrets come from GSM, never this file.
    Consumed by the platform admin Pipeline Settings page.
    """
    cfg = load_yaml_config(Path(__file__).parent / "configs" / "default.yaml")
    return {"source": "services/podcast/configs/default.yaml", "settings": cfg}
