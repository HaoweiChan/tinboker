"""
PostgreSQL database connection and session management using SQLAlchemy.
"""

import logging
from typing import Generator
from sqlalchemy import create_engine, event, Engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from src.config import settings

logger = logging.getLogger(__name__)

# SQLAlchemy Base for ORM models
Base = declarative_base()

# Database engine (will be initialized when needed)
engine: Engine | None = None
SessionLocal: sessionmaker | None = None


def get_database_url() -> str:
    """
    Get the database URL based on configuration.
    
    Returns:
        Database connection URL (PostgreSQL or SQLite)
    """
    if settings.use_postgres:
        # Use PostgreSQL
        db_url = settings.postgres_connection_string
        if not db_url:
            raise ValueError("PostgreSQL is enabled but DATABASE_URL is not configured")
        logger.info(f"Using PostgreSQL database: {db_url.split('@')[-1] if '@' in db_url else 'configured'}")
        return db_url
    else:
        # Use SQLite
        db_path = settings.database_path
        db_url = f"sqlite:///{db_path}"
        logger.info(f"Using SQLite database: {db_path}")
        return db_url


def init_engine():
    """Initialize database engine and session maker."""
    global engine, SessionLocal
    
    if engine is not None:
        return  # Already initialized
    
    db_url = get_database_url()
    
    # Create engine with appropriate settings
    if settings.use_postgres:
        # PostgreSQL settings
        engine = create_engine(
            db_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,  # Verify connections before using
            echo=settings.is_development,  # Log SQL in development
        )
    else:
        # SQLite settings
        engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False},  # SQLite specific
            echo=settings.is_development,
        )
        
        # Enable foreign keys for SQLite
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_conn, connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    
    # Create session maker
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    logger.info("Database engine initialized successfully")


def get_session() -> Generator[Session, None, None]:
    """
    Get database session (FastAPI dependency).
    
    Usage:
        @app.get("/items")
        def get_items(db: Session = Depends(get_session)):
            return db.query(Item).all()
    
    Yields:
        SQLAlchemy session
    """
    if SessionLocal is None:
        init_engine()
    
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all_tables():
    """
    Create all database tables based on SQLAlchemy models.
    
    Note: For production, use Alembic migrations instead.
    """
    if engine is None:
        init_engine()
    
    logger.info("Creating all database tables...")
    Base.metadata.create_all(bind=engine)
    # Add columns that may not exist on pre-existing tables (idempotent).
    if engine.dialect.name == "postgresql":
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE IF EXISTS stock_translations "
                "ADD COLUMN IF NOT EXISTS brand_color VARCHAR(7)"
            ))
            conn.execute(text(
                "ALTER TABLE IF EXISTS stock_translations "
                "ADD COLUMN IF NOT EXISTS aliases JSON"
            ))
            conn.execute(text(
                "ALTER TABLE IF EXISTS stock_translations "
                "ADD COLUMN IF NOT EXISTS name_preference VARCHAR(10) DEFAULT 'auto'"
            ))
            conn.execute(text(
                "ALTER TABLE IF EXISTS content_sources "
                "ADD COLUMN IF NOT EXISTS cover_image_url TEXT"
            ))
            # Unified topic registry: tag rows pre-date these columns.
            conn.execute(text(
                "ALTER TABLE IF EXISTS tag_registry "
                "ADD COLUMN IF NOT EXISTS kind VARCHAR(20) NOT NULL DEFAULT 'tag'"
            ))
            conn.execute(text(
                "ALTER TABLE IF EXISTS tag_registry "
                "ADD COLUMN IF NOT EXISTS exposure_id VARCHAR(120)"
            ))
            conn.execute(text(
                "ALTER TABLE IF EXISTS tag_registry "
                "ADD COLUMN IF NOT EXISTS icon_id VARCHAR(64)"
            ))
            conn.execute(text(
                "ALTER TABLE IF EXISTS tag_registry "
                "ADD COLUMN IF NOT EXISTS color_hex VARCHAR(16)"
            ))
            conn.execute(text(
                "ALTER TABLE IF EXISTS tag_registry "
                "ADD COLUMN IF NOT EXISTS exposure_type VARCHAR(20)"
            ))
            conn.execute(text(
                "ALTER TABLE IF EXISTS tag_registry "
                "ADD COLUMN IF NOT EXISTS description TEXT"
            ))
            conn.execute(text(
                "ALTER TABLE IF EXISTS tag_registry "
                "ADD COLUMN IF NOT EXISTS members JSONB"
            ))
            conn.execute(text(
                "ALTER TABLE IF EXISTS tag_registry "
                "ADD COLUMN IF NOT EXISTS aliases JSONB"
            ))
            conn.execute(text(
                "ALTER TABLE IF EXISTS tag_registry "
                "ADD COLUMN IF NOT EXISTS field_owners JSONB"
            ))
            conn.execute(text(
                "ALTER TABLE IF EXISTS tag_registry "
                "ADD COLUMN IF NOT EXISTS parent_id VARCHAR(120)"
            ))
            conn.execute(text(
                "ALTER TABLE IF EXISTS tag_registry "
                "ADD COLUMN IF NOT EXISTS redirect_to VARCHAR(120)"
            ))
            conn.execute(text(
                """
                CREATE TABLE IF NOT EXISTS tag_registry_audit (
                    id BIGSERIAL PRIMARY KEY,
                    tag_registry_id INTEGER,
                    exposure_id VARCHAR(120),
                    action VARCHAR(10) NOT NULL,
                    actor VARCHAR(100) NOT NULL DEFAULT 'unknown',
                    note TEXT,
                    "before" JSONB,
                    "after" JSONB,
                    at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_tag_registry_audit_exposure_id "
                "ON tag_registry_audit (exposure_id)"
            ))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_tag_registry_audit_at "
                "ON tag_registry_audit (at)"
            ))
            conn.execute(text(
                """
                CREATE TABLE IF NOT EXISTS taxonomy_changelog (
                    id BIGSERIAL PRIMARY KEY,
                    version INTEGER NOT NULL,
                    entry TEXT NOT NULL,
                    rationale TEXT,
                    actor VARCHAR(100) NOT NULL,
                    at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            ))
            conn.execute(text(
                """
                CREATE TABLE IF NOT EXISTS taxonomy_version (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    version INTEGER NOT NULL DEFAULT 0,
                    updated_by VARCHAR(100),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            ))
            conn.execute(text(
                """
                CREATE TABLE IF NOT EXISTS taxonomy_drafts (
                    id BIGSERIAL PRIMARY KEY,
                    status VARCHAR(20) NOT NULL DEFAULT 'draft',
                    payload JSONB NOT NULL,
                    diff JSONB,
                    actor VARCHAR(100) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    published_at TIMESTAMPTZ
                )
                """
            ))
            conn.execute(text(
                """
                CREATE OR REPLACE FUNCTION tag_registry_audit_trigger()
                RETURNS trigger AS $$
                DECLARE
                    audit_actor TEXT;
                    audit_note TEXT;
                BEGIN
                    audit_actor := COALESCE(
                        NULLIF(current_setting('app.taxonomy_actor', true), ''),
                        'unknown'
                    );
                    audit_note := NULLIF(current_setting('app.taxonomy_note', true), '');

                    IF TG_OP = 'INSERT' THEN
                        INSERT INTO tag_registry_audit (
                            tag_registry_id, exposure_id, action, actor, note,
                            "before", "after", at
                        )
                        VALUES (
                            NEW.id, NEW.exposure_id, TG_OP, audit_actor, audit_note,
                            NULL, to_jsonb(NEW), now()
                        );
                        RETURN NEW;
                    ELSIF TG_OP = 'UPDATE' THEN
                        INSERT INTO tag_registry_audit (
                            tag_registry_id, exposure_id, action, actor, note,
                            "before", "after", at
                        )
                        VALUES (
                            NEW.id, COALESCE(NEW.exposure_id, OLD.exposure_id), TG_OP,
                            audit_actor, audit_note, to_jsonb(OLD), to_jsonb(NEW), now()
                        );
                        RETURN NEW;
                    ELSIF TG_OP = 'DELETE' THEN
                        INSERT INTO tag_registry_audit (
                            tag_registry_id, exposure_id, action, actor, note,
                            "before", "after", at
                        )
                        VALUES (
                            OLD.id, OLD.exposure_id, TG_OP, audit_actor, audit_note,
                            to_jsonb(OLD), NULL, now()
                        );
                        RETURN OLD;
                    END IF;
                    RETURN NULL;
                END;
                $$ LANGUAGE plpgsql SECURITY DEFINER;
                """
            ))
            conn.execute(text(
                "DROP TRIGGER IF EXISTS tag_registry_audit_iud ON tag_registry"
            ))
            conn.execute(text(
                """
                CREATE TRIGGER tag_registry_audit_iud
                AFTER INSERT OR UPDATE OR DELETE ON tag_registry
                FOR EACH ROW EXECUTE FUNCTION tag_registry_audit_trigger()
                """
            ))
            # stock_daily_ohlc predates the whole-market TWSE/TPEx fetcher (was an unused
            # US/yfinance orphan) — add the columns the fetcher writes.
            conn.execute(text(
                "ALTER TABLE IF EXISTS stock_daily_ohlc "
                "ADD COLUMN IF NOT EXISTS trading_value DOUBLE PRECISION"
            ))
            conn.execute(text(
                "ALTER TABLE IF EXISTS stock_daily_ohlc "
                "ADD COLUMN IF NOT EXISTS source VARCHAR(20)"
            ))
            conn.commit()
    elif engine.dialect.name == "sqlite":
        # SQLite has no "ADD COLUMN IF NOT EXISTS" — check PRAGMA first.
        with engine.connect() as conn:
            cols = {row[1] for row in conn.execute(text("PRAGMA table_info(stock_translations)"))}
            if cols and "aliases" not in cols:
                conn.execute(text("ALTER TABLE stock_translations ADD COLUMN aliases JSON"))
                conn.commit()
            if cols and "name_preference" not in cols:
                conn.execute(text("ALTER TABLE stock_translations ADD COLUMN name_preference VARCHAR(10) DEFAULT 'auto'"))
                conn.commit()
            cs_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(content_sources)"))}
            if cs_cols and "cover_image_url" not in cs_cols:
                conn.execute(text("ALTER TABLE content_sources ADD COLUMN cover_image_url TEXT"))
                conn.commit()
            tr_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(tag_registry)"))}
            if tr_cols and "kind" not in tr_cols:
                conn.execute(text("ALTER TABLE tag_registry ADD COLUMN kind VARCHAR(20) NOT NULL DEFAULT 'tag'"))
                conn.commit()
            if tr_cols and "exposure_id" not in tr_cols:
                conn.execute(text("ALTER TABLE tag_registry ADD COLUMN exposure_id VARCHAR(120)"))
                conn.commit()
            if tr_cols and "icon_id" not in tr_cols:
                conn.execute(text("ALTER TABLE tag_registry ADD COLUMN icon_id VARCHAR(64)"))
                conn.commit()
            if tr_cols and "color_hex" not in tr_cols:
                conn.execute(text("ALTER TABLE tag_registry ADD COLUMN color_hex VARCHAR(16)"))
                conn.commit()
            if tr_cols and "exposure_type" not in tr_cols:
                conn.execute(text("ALTER TABLE tag_registry ADD COLUMN exposure_type VARCHAR(20)"))
                conn.commit()
            if tr_cols and "description" not in tr_cols:
                conn.execute(text("ALTER TABLE tag_registry ADD COLUMN description TEXT"))
                conn.commit()
            if tr_cols and "members" not in tr_cols:
                conn.execute(text("ALTER TABLE tag_registry ADD COLUMN members JSON"))
                conn.commit()
            if tr_cols and "aliases" not in tr_cols:
                conn.execute(text("ALTER TABLE tag_registry ADD COLUMN aliases JSON"))
                conn.commit()
            if tr_cols and "field_owners" not in tr_cols:
                conn.execute(text("ALTER TABLE tag_registry ADD COLUMN field_owners JSON"))
                conn.commit()
            if tr_cols and "parent_id" not in tr_cols:
                conn.execute(text("ALTER TABLE tag_registry ADD COLUMN parent_id VARCHAR(120)"))
                conn.commit()
            if tr_cols and "redirect_to" not in tr_cols:
                conn.execute(text("ALTER TABLE tag_registry ADD COLUMN redirect_to VARCHAR(120)"))
                conn.commit()
    # Clean up obsolete cryptocurrency tag registry rows (idempotent)
    with engine.connect() as conn:
        conn.execute(text(
            "DELETE FROM tag_registry WHERE slug IN ('cryptocurrency', 'sector_cryptocurrency') "
            "OR exposure_id IN ('sector_cryptocurrency', 'theme_cryptocurrency')"
        ))
        conn.commit()
    logger.info("Database tables created successfully")


def drop_all_tables():
    """
    Drop all database tables.
    
    WARNING: This will delete all data! Use only for development/testing.
    """
    if engine is None:
        init_engine()
    
    logger.warning("Dropping all database tables...")
    Base.metadata.drop_all(bind=engine)
    logger.warning("Database tables dropped successfully")
