import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from src.config import settings
from src.database.db import init_db
from fastapi.responses import JSONResponse
from fastapi import FastAPI, Request, status
from src.cache.redis_client import RedisClient
from src.routers.news import router as news_router
from fastapi.middleware.cors import CORSMiddleware
from src.routers.stock import router as stock_router
from src.routers.graph import router as graph_router
from src.routers.company import router as company_router
from src.routers.content import router as content_router
from src.routers.websocket import router as websocket_router
from src.routers.visual_graph import router as visual_graph_router
from src.routers.websocket_prices import router as websocket_prices_router
from src.routers.podcast import router as podcast_router
from src.routers.episodes import router as episodes_router
from src.routers.tags import router as tags_router
from src.routers.auth import router as auth_router
from src.routers.user import router as user_router
from src.routers.search import router as search_router, init_search_index
from src.routers.analytics import router as analytics_router
from src.routers.recommendations import router as recommendations_router
from src.routers.ticker_insights import router as ticker_insights_router
from src.routers.translations import router as translations_router
from src.routers.admin_translations import router as admin_translations_router
from src.routers.sources import router as sources_router
from src.routers.admin_sources import router as admin_sources_router
from src.routers.admin_pipeline import router as admin_pipeline_router
from src.routers.admin_pipeline_trial import router as admin_pipeline_trial_router
from src.routers.admin_system import router as admin_system_router
from src.routers.admin_analytics import router as admin_analytics_router
from src.routers.notifications import router as notifications_router
from src.routers.comments import router as comments_router, comments_router as comments_delete_router
from src.routers.articles import router as articles_router
from src.routers.admin_articles import router as admin_articles_router
from src.routers.admin_tags import router as admin_tags_router
from src.routers.social import router as social_router
from src.routers.seo import router as seo_router
from src.middleware.cloudflare import CloudflareMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    # --- Startup ---
    # Always initialise raw SQLite tables (stocks, news, graphs, comments, etc.)
    # regardless of whether PostgreSQL is used for ORM models.
    init_db()

    if not settings.use_postgres:
        from src.database.postgres import init_engine, create_all_tables
        init_engine()
        create_all_tables()
    else:
        from src.database.postgres import init_engine, create_all_tables
        try:
            init_engine()
            # Idempotent: creates any missing tables and ALTERs in missing columns
            # (e.g. stock_translations.aliases / name_preference) so the ORM schema
            # stays in sync. Previously only run on the SQLite path, which left
            # Postgres tables missing newly-added columns -> translation queries 500'd.
            create_all_tables()
            print("PostgreSQL connection initialized")
        except Exception as e:
            print(f"Warning: Could not initialize PostgreSQL: {e}")
            print("Falling back to SQLite...")
            from src.database.postgres import init_engine as init_orm_engine, create_all_tables
            init_orm_engine()
            create_all_tables()

    rec_conn_str = settings.postgres_connection_string
    if rec_conn_str:
        try:
            from src.database import insight_db
            insight_db.init_pool()
            print("Insight Postgres pool initialized.")
        except Exception as e:
            print(f"Warning: Could not initialize insight Postgres: {e}")
    else:
        print("Info: Insight Postgres not configured.")

    await RedisClient.initialize()
    await init_search_index()

    # Seed missing translations and backfill brand colors (insert-only, never overwrites)
    try:
        from src.data.brand_colors import BRAND_COLORS
        from src.data.seed_data import TRANSLATIONS
        from src.data.us_stocks import US_STOCK_TRANSLATIONS
        from src.database.postgres import get_session
        from src.services.translation_service import TranslationService
        for session in get_session():
            svc = TranslationService(session)
            tw_inserted = svc.backfill_translations(TRANSLATIONS, BRAND_COLORS)
            if tw_inserted:
                print(f"Backfilled {tw_inserted} new TW/core stock translation(s).")
            us_inserted = svc.backfill_translations(US_STOCK_TRANSLATIONS, BRAND_COLORS)
            if us_inserted:
                print(f"Backfilled {us_inserted} new US stock translation(s).")
            updated = svc.backfill_brand_colors(BRAND_COLORS)
            if updated:
                print(f"Backfilled brand_color for {updated} stock translation(s).")
            break
    except Exception as e:
        print(f"Warning: translation seed/backfill skipped: {e}")

    # Seed followed content sources (podcasts + news feeds) from config (insert-only).
    try:
        from src.data.content_sources_seed import ALL_SOURCES
        from src.database.postgres import get_session
        from src.services.content_source_service import ContentSourceService
        for session in get_session():
            inserted = ContentSourceService(session).seed_from_config(ALL_SOURCES)
            if inserted:
                print(f"Seeded {inserted} new content source(s).")
            break
    except Exception as e:
        print(f"Warning: content source seed skipped: {e}")

    # Seed tag registry (insert-only when table is empty).
    try:
        from src.database.postgres import get_session as _gs
        from src.tag_registry import seed_if_empty
        for session in _gs():
            seed_if_empty(session)
            break
    except Exception as e:
        print(f"Warning: tag registry seed skipped: {e}")

    # Backfill podcast cover art (Spotify oEmbed) in the background — best-effort,
    # must NOT block startup/health (external HTTP).
    async def _backfill_covers_bg():
        def _run() -> int:
            from src.database.postgres import get_session
            from src.services.content_source_service import ContentSourceService
            result = 0
            for session in get_session():
                result = ContentSourceService(session).backfill_missing_covers()
                break
            return result
        try:
            covered = await asyncio.to_thread(_run)
            if covered:
                print(f"Backfilled {covered} podcast cover image(s).")
        except Exception as e:
            print(f"Warning: cover backfill skipped: {e}")

    asyncio.create_task(_backfill_covers_bg())

    yield

    # --- Shutdown ---
    await RedisClient.close_all()
    try:
        from src.database import insight_db
        insight_db.close_pool()
    except Exception:
        pass


app = FastAPI(
    title=settings.api_title,
    description="Backend API for TinBoker - Financial podcast insights platform",
    version=settings.api_version,
    lifespan=lifespan,
    servers=[
        {
            "url": f"http://localhost:{settings.port}",
            "description": "Development server"
        },
        {
            "url": "https://api.tinboker.com",
            "description": "Production server"
        }
    ]
)


# CORS Configuration
# In non-prod, allow Vercel/Cloudflare Pages preview URLs so PR previews can hit the
# dev/staging API. In production this wildcard is DISABLED: with allow_credentials=True
# any attacker-deployed *.pages.dev / *.vercel.app site would otherwise be a trusted
# credentialed origin. Prod is restricted to the explicit CORS_ORIGINS allowlist only.
_preview_origin_regex = (
    None if settings.is_production
    else r"https://.*\.(vercel\.app|pages\.dev)$"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=_preview_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS", "PUT", "DELETE", "PATCH"],
    allow_headers=["*"],  # Allow all headers (including X-Silent-Error, etc.)
    max_age=86400,
)
# Note: WebSocket connections are handled separately and don't use CORS middleware

# Cloudflare middleware for trusted proxy handling (extracts real client IP)
app.add_middleware(CloudflareMiddleware)

# Register routers
app.include_router(graph_router)
app.include_router(company_router)
app.include_router(stock_router)
app.include_router(content_router)
app.include_router(websocket_router)
app.include_router(websocket_prices_router)
app.include_router(news_router)
app.include_router(visual_graph_router)
app.include_router(podcast_router)
app.include_router(episodes_router)
app.include_router(tags_router)
app.include_router(auth_router)
app.include_router(user_router)
app.include_router(search_router)
app.include_router(recommendations_router)
app.include_router(ticker_insights_router)
app.include_router(analytics_router, prefix="/api/analytics", tags=["analytics"])
app.include_router(translations_router)
app.include_router(admin_translations_router)
app.include_router(sources_router)
app.include_router(admin_sources_router)
app.include_router(admin_pipeline_router)
app.include_router(admin_pipeline_trial_router)
app.include_router(admin_system_router)
app.include_router(admin_analytics_router)
app.include_router(notifications_router)
app.include_router(comments_router)
app.include_router(comments_delete_router)
app.include_router(articles_router)
app.include_router(admin_articles_router)
app.include_router(admin_tags_router)
app.include_router(social_router)
app.include_router(seo_router)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions"""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An internal server error occurred",
                "status": 500
            }
        }
    )


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint with component status."""
    import os
    redis_available = await RedisClient.is_available()
    
    # Check Redis configuration
    redis_url = settings.redis_connection_string
    redis_url_configured = redis_url is not None
    redis_url_from_env = "REDIS_URL" in os.environ
    
    # Mask password in URL for logging
    redis_url_display = None
    if redis_url:
        if "@" in redis_url and ":" in redis_url.split("@")[0]:
            parts = redis_url.split("@")
            redis_url_display = f"redis://:***@{parts[1]}" if len(parts) > 1 else redis_url
        else:
            redis_url_display = redis_url
    
    # Check database connectivity
    db_status = {"status": "unknown", "type": "unknown"}
    if settings.use_postgres:
        db_status["type"] = "postgresql"
        try:
            from src.database.postgres import engine
            if engine:
                from sqlalchemy import text
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                db_status["status"] = "connected"
            else:
                db_status["status"] = "not_initialized"
        except Exception as e:
            db_status["status"] = "error"
            db_status["error"] = str(e)
    else:
        db_status["type"] = "sqlite"
        try:
            from src.database.db import get_db_session
            with get_db_session() as session:
                session.execute("SELECT 1")
            db_status["status"] = "connected"
        except Exception as e:
            db_status["status"] = "error"
            db_status["error"] = str(e)
    
    # Check insight DB (podcast_db) connectivity
    rec_db_status = {"status": "unknown"}
    try:
        from src.database.insight_db import is_available as rec_is_available
        if rec_is_available():
            rec_db_status["status"] = "connected"
        else:
            rec_conn_str = settings.postgres_connection_string
            rec_db_status["status"] = "not_configured" if not rec_conn_str else "pool_not_initialized"
    except Exception as e:
        rec_db_status["status"] = "error"
        rec_db_status["error"] = str(e)

    # Determine overall health
    overall_status = "healthy"
    if db_status["status"] != "connected":
        overall_status = "degraded"
    
    health_status = {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "database": db_status,
        "recommendation_db": rec_db_status,
        "redis": {
            "available": redis_available,
            "status": "connected" if redis_available else "disconnected",
            "configured": redis_url_configured,
        }
    }
    
    # Add cache statistics if Redis is available
    if redis_available:
        try:
            redis = await RedisClient.get_client()
            if redis:
                info = await redis.info("stats")
                health_status["redis"]["keyspace_hits"] = int(info.get("keyspace_hits", 0))
                health_status["redis"]["keyspace_misses"] = int(info.get("keyspace_misses", 0))
                total_requests = health_status["redis"]["keyspace_hits"] + health_status["redis"]["keyspace_misses"]
                if total_requests > 0:
                    health_status["redis"]["hit_rate"] = round(
                        health_status["redis"]["keyspace_hits"] / total_requests, 4
                    )
                else:
                    health_status["redis"]["hit_rate"] = 0.0
        except Exception as e:
            health_status["redis"]["error"] = str(e)
    
    return health_status


# Diagnostic endpoint for Redis setup
@app.get("/health/redis")
async def redis_diagnostic():
    """Detailed Redis diagnostic endpoint"""
    import os
    from src.cache.redis_client import RedisClient
    
    diagnostic = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "environment": {
            "REDIS_URL_env_var_exists": "REDIS_URL" in os.environ,
            "REDIS_URL_value_length": len(os.environ.get("REDIS_URL", "")) if "REDIS_URL" in os.environ else 0,
            "REDIS_URL_preview": os.environ.get("REDIS_URL", "NOT SET")[:50] + "..." if len(os.environ.get("REDIS_URL", "")) > 50 else os.environ.get("REDIS_URL", "NOT SET")
        },
        "configuration": {
            "redis_connection_string_configured": settings.redis_connection_string is not None,
            "redis_connection_string_preview": None
        },
        "connection": {
            "redis_client_exists": RedisClient._client is not None,
            "redis_available": await RedisClient.is_available()
        }
    }
    
    # Show connection string preview (masked)
    if settings.redis_connection_string:
        conn_str = settings.redis_connection_string
        if "@" in conn_str:
            parts = conn_str.split("@")
            diagnostic["configuration"]["redis_connection_string_preview"] = f"redis://:***@{parts[1]}" if len(parts) > 1 else conn_str
        else:
            diagnostic["configuration"]["redis_connection_string_preview"] = conn_str
    
    # Try to connect and get info
    if diagnostic["connection"]["redis_available"]:
        try:
            redis = await RedisClient.get_client()
            if redis:
                info = await redis.info("server")
                diagnostic["connection"]["redis_version"] = info.get("redis_version", "unknown")
                diagnostic["connection"]["connected_clients"] = info.get("connected_clients", 0)
        except Exception as e:
            diagnostic["connection"]["error"] = str(e)
    else:
        diagnostic["connection"]["error"] = "Redis not available - check REDIS_URL environment variable"
    
    return diagnostic


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": settings.api_title,
        "version": settings.api_version,
        "environment": settings.environment,
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    
    # Check if nest_asyncio is present and handle event loop conflict
    try:
        import nest_asyncio
        # Apply nest_asyncio patch if needed
        nest_asyncio.apply()
        # Force use of asyncio loop instead of uvloop
        uvicorn.run(
            app,
            host=settings.host,
            port=settings.port,
            loop="asyncio",
            timeout_graceful_shutdown=5,
        )
    except ImportError:
        # If nest_asyncio is not present, use default (which may use uvloop)
        uvicorn.run(
            app,
            host=settings.host,
            port=settings.port,
            timeout_graceful_shutdown=5,
        )

