"""
Configuration management for TinBoker Backend.

This module handles:
- System/application configuration (with defaults)
- Secret tokens (loaded from .env file)
- Environment-based settings

Best Practices:
- Secrets: Stored in .env file (never committed to git)
- System config: Can be set via environment variables or use defaults
- All config is type-safe and validated
"""

from typing import Optional, Union, Tuple, Type
from dotenv import load_dotenv
from pydantic import field_validator, model_validator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource
from src.config_loader import GCPSecretManagerSource

load_dotenv()


class Settings(BaseSettings):
    """
    Application settings with type safety and validation.
    
    Secrets are loaded from .env file.
    System config can be overridden via environment variables.
    """
    
    # ==================== Secrets (from .env) ====================
    # These should NEVER have defaults and should be in .env
    finmind_api_key: Optional[str] = None
    # Optional pool of FinMind free-tier keys (comma-separated) → GSM secret FINMIND_API_KEYS.
    # Each key has its own hourly quota, so a pool multiplies our ceiling. Falls back to the
    # single finmind_api_key when unset.
    finmind_api_keys: Optional[str] = None
    massive_api_key: Optional[str] = None
    podcast_api_key: Optional[str] = None  # API key for external podcast API (Netcup server)
    
    # Google OAuth Configuration
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    
    
    # JWT Configuration
    jwt_secret_key: Optional[str] = None
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: Optional[int] = 24

    # Admin Authentication (from GSM: ADMIN_EMAILS)
    admin_emails: list[str] = []  # Comma-separated list of admin email addresses

    # Dev bypass token for automated browser testing (e.g. Cursor browser MCP)
    dev_bypass_token: Optional[str] = None

    # Non-expiring service token for the headless translation backfill agent
    # (env var: TINBOKER_WRITE_TOKEN — same name the agent's MCP uses). Grants access
    # to the translation list + bulk-write endpoints ONLY (not full admin). Generate
    # with `openssl rand -hex 32`; store in GSM. Unset = disabled.
    tinboker_write_token: Optional[str] = None

    # Service token for the article authoring MCP / headless agent.
    # Scoped to article CRUD endpoints only.
    tinboker_article_token: Optional[str] = None
    tinboker_article_author_id: Optional[str] = None
    tinboker_article_author_name: Optional[str] = None
    tinboker_article_author_avatar: Optional[str] = None

    # ==================== Social / Threads publishing ====================
    # Meta Threads Graph API credentials. Generate a long-lived access token for
    # the brand's Threads account + its numeric user id; store both in GSM.
    # Unset = posting disabled (the publisher runs in dry-run only).
    threads_access_token: Optional[str] = None
    threads_user_id: Optional[str] = None
    threads_api_base: str = "https://graph.threads.net/v1.0"
    # Service token that lets the agents pipeline (post-ingest) trigger a Threads
    # publish run without an admin JWT. Scoped to the threads publish endpoint only.
    # Generate with `openssl rand -hex 32`; store in GSM. Unset = disabled.
    tinboker_social_token: Optional[str] = None
    # Only auto-post episodes published within this many days (recency guard that
    # caps blast radius even if the idempotency store is reset). 0 = no cap.
    threads_max_age_days: int = 4

    # ==================== SEO ====================
    # Public site origin — used to build episode permalinks in Threads posts and
    # the dynamic sitemap. No trailing slash.
    site_url: str = "https://tinboker.com"
    # Google Search Console property to read analytics for. Domain properties use
    # the "sc-domain:tinboker.com" form; URL-prefix properties use the full URL.
    # Unset = SEO monitoring disabled.
    gsc_site_url: Optional[str] = None
    # Path to a Google service-account JSON with Search Console read access. Falls
    # back to GOOGLE_APPLICATION_CREDENTIALS / ADC when unset (the same credentials
    # firebase-admin already uses on the VPS, once added as a GSC property user).
    google_application_credentials: Optional[str] = None

    @field_validator("admin_emails", mode="before")
    @classmethod
    def parse_admin_emails(cls, v: Union[str, list, None]) -> list[str]:
        """Parse admin emails from comma-separated string or list"""
        if v is None or v == "":
            return []
        if isinstance(v, str):
            if v.strip().startswith("["):
                import json
                return json.loads(v)
            return [email.strip().lower() for email in v.split(",") if email.strip()]
        return [email.lower() for email in v]

    # Cloudflare Analytics (from GSM: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ZONE_TAG)
    cloudflare_api_token: Optional[str] = None  # Cloudflare API token for analytics
    cloudflare_zone_tag: Optional[str] = None  # Cloudflare zone ID for tinboker.com
    
    @field_validator("jwt_expiration_hours", mode="before")
    @classmethod
    def parse_jwt_expiration_hours(cls, v: Union[str, int, None]) -> Optional[int]:
        """Parse JWT expiration hours, handling empty strings"""
        if v is None or v == "":
            return 24  # Default
        if isinstance(v, str):
            if v.strip() == "":
                return 24  # Default
            return int(v)
        return int(v) if v else 24
    
    @model_validator(mode='after')
    def enforce_production_postgres(self):
        """Enforce PostgreSQL usage in production environment"""
        if self.environment.lower() == "production" and not self.use_postgres:
            # Force enable Postgres in production to prevent data loss
            self.use_postgres = True
        return self
    
    # ==================== System Configuration ====================
    # These have sensible defaults but can be overridden via env vars
    
    # Data source configuration
    use_finmind: bool = True  # Use FinMind API instead of mock data
    
    # Server configuration
    host: str = "0.0.0.0"
    port: int = 5174  # Default port for local development. Render sets PORT env var which is automatically read (case-insensitive)
    
    # CORS configuration
    # Can be set as comma-separated string in env: "http://localhost:5173,https://tinboker.com"
    # Or as JSON array: '["http://localhost:5173","https://tinboker.com"]'
    # Note: Vercel preview URLs (https://*.vercel.app) are automatically allowed via regex pattern
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
        "https://tinboker.com",
        "https://www.tinboker.com",
        "https://dev.tinboker.com",
        "https://staging.tinboker.com",
    ]
    
    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: Union[str, list]) -> list[str]:
        """Parse CORS origins from string or list"""
        if isinstance(v, str):
            # Try JSON first (pydantic will handle it)
            # If not JSON, treat as comma-separated
            if v.strip().startswith("["):
                # JSON array - let pydantic parse it
                import json
                return json.loads(v)
            else:
                # Comma-separated string
                return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v
    
    # API configuration
    api_title: str = "TinBoker Backend API"
    api_version: str = "1.0.0"
    
    # Environment
    environment: str = "development"  # development, staging, production

    # ==================== Release scoping ====================
    # Restrict the public podcast catalog to a launch subset. Each value is a
    # content_sources.language code (e.g. "zh-TW"). Empty list = no language
    # restriction (show every followed show). Default: zh-TW-only launch.
    # Override via env RELEASE_PODCAST_LANGUAGES="zh-TW,en" or "" to disable.
    release_podcast_languages: list[str] = ["zh-TW"]
    # Hide episodes whose publish time (released_at_ms) is older than this many
    # days. 0 = no recency cap. Keep 0 until the agents pipeline backfills a
    # reliable released_at_ms (created_time is ingestion time, not publish time);
    # then flip RELEASE_EPISODE_MAX_AGE_DAYS=30 to enable the 1-month window.
    release_episode_max_age_days: int = 0

    @field_validator("release_podcast_languages", mode="before")
    @classmethod
    def parse_release_podcast_languages(cls, v: Union[str, list, None]) -> list[str]:
        """Parse release language allowlist from comma-separated string or list."""
        if v is None:
            return []
        if isinstance(v, str):
            s = v.strip()
            if s == "":
                return []
            if s.startswith("["):
                import json
                return json.loads(s)
            return [lang.strip() for lang in s.split(",") if lang.strip()]
        return list(v)

    # Database configuration
    database_path: str = "data/tinboker.db"  # SQLite database file path
    use_postgres: bool = False  # Toggle between SQLite and PostgreSQL
    postgres_url: Optional[str] = None  # PostgreSQL connection URL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "podcast_db"
    postgres_user: str = "podcast_user"
    postgres_password: Optional[str] = None
    
    @property
    def postgres_connection_string(self) -> Optional[str]:
        """Get PostgreSQL connection string from DATABASE_URL or individual settings."""
        import os
        from urllib.parse import quote
        # Render provides DATABASE_URL automatically
        if "DATABASE_URL" in os.environ:
            return os.environ["DATABASE_URL"]

        if self.postgres_url:
            return self.postgres_url

        # Build from individual settings; URL-encode the password so special chars
        # like '#' and '@' don't corrupt the connection URL.
        if self.postgres_password:
            pw = quote(self.postgres_password, safe='')
            return f"postgresql://{self.postgres_user}:{pw}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

        return None

    # Redis configuration
    redis_url: Optional[str] = None  # Redis connection URL (Render provides REDIS_URL)
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: Optional[str] = None
    
    @property
    def redis_connection_string(self) -> Optional[str]:
        """Get Redis connection string from REDIS_URL or individual settings."""
        import os
        # Render provides REDIS_URL automatically
        if "REDIS_URL" in os.environ:
            return os.environ["REDIS_URL"]
        
        if self.redis_url:
            return self.redis_url
        
        # Build from individual settings
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        else:
            return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
    
    # WebSocket configuration
    websocket_update_interval: int = 5  # seconds
    intraday_snapshot_retention_days: int = 30
    
    # External Podcast API (Netcup server) configuration
    netcup_api_url: str = Field(
        default="http://159.195.45.195:8000",
        validation_alias="NETCUP_IP"
    )
    
    model_config = SettingsConfigDict(
        # Load from .env file
        env_file=".env",
        env_file_encoding="utf-8",
        # Allow case-insensitive env var names
        case_sensitive=False,
        # Allow extra fields (for flexibility)
        extra="ignore"
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        """
        Define priority of settings sources.
        Priority (Highest to Lowest):
        1. Constructor arguments (init_settings)
        2. Environment variables (env_settings)
        3. .env file (dotenv_settings)
        4. GCP Secret Manager (GCPSecretManagerSource)
        """
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            GCPSecretManagerSource(settings_cls),
        )
    
    @property
    def finmind_api_key_pool(self) -> list[str]:
        """
        Ordered list of FinMind API keys to rotate across.

        Prefers the comma-separated FINMIND_API_KEYS pool; falls back to the single
        FINMIND_API_KEY. De-duplicates while preserving order.
        """
        raw = self.finmind_api_keys or self.finmind_api_key or ""
        seen: set[str] = set()
        pool: list[str] = []
        for k in raw.split(","):
            k = k.strip()
            if k and k not in seen:
                seen.add(k)
                pool.append(k)
        return pool

    @property
    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.environment.lower() == "production"
    
    @property
    def is_development(self) -> bool:
        """Check if running in development environment"""
        return self.environment.lower() == "development"


# Global settings instance
# This will be initialized when the module is imported
settings = Settings()
