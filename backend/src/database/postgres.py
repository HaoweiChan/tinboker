"""
PostgreSQL database connection and session management using SQLAlchemy.
"""

import logging
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, event, Engine, text
from sqlalchemy.exc import DBAPIError
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
            connect_args={
                "options": f"-c idle_in_transaction_session_timeout={_IDLE_IN_TRANSACTION_TIMEOUT_MS}"
            },
            echo=settings.sql_echo,
        )
    else:
        # SQLite settings
        engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False},  # SQLite specific
            echo=settings.sql_echo,
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


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Session for non-FastAPI (plain sync) code: commits on success, always closes.

    ``get_session`` above is the request-scoped dependency and never commits; the
    user/notification data layer runs outside the dependency system and writes.
    """
    if SessionLocal is None:
        init_engine()

    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# Boot-time DDL runs against the one Postgres instance dev, staging and prod share, so a
# lock it cannot get must never hang startup: on 2026-10-01 an ALTER on tag_registry
# waited ~5h behind another container's idle-in-transaction session and prod answered
# 502 the whole time.
_BOOT_DDL_LOCK_TIMEOUT = "5s"
_PG_LOCK_NOT_AVAILABLE = "55P03"
# Backstop for a session that is opened and never closed: Postgres ends it instead of
# letting it pin its locks. Generous, because some startup seeds hold a session across
# external HTTP calls.
_IDLE_IN_TRANSACTION_TIMEOUT_MS = 300_000

# Columns added to tables that pre-date them: (table, column, type).
_PG_BOOT_COLUMNS: list[tuple[str, str, str]] = [
    # Billing PR 3b.
    ("subscriptions", "paid_until", "TIMESTAMPTZ"),
    ("subscriptions", "promo_code", "VARCHAR(32)"),
    ("stock_translations", "brand_color", "VARCHAR(7)"),
    ("stock_translations", "aliases", "JSON"),
    ("stock_translations", "name_preference", "VARCHAR(10) DEFAULT 'auto'"),
    ("content_sources", "cover_image_url", "TEXT"),
    # Comments synced before we stored the API's own permalink have none; the
    # UI hides the link rather than guessing a URL that 404s.
    ("threads_comments", "permalink", "TEXT"),
    ("threads_comments", "root_post_text", "TEXT"),
    ("social_posts", "format", "VARCHAR(40)"),
    ("social_posts", "subject", "VARCHAR(80)"),
    ("social_posts", "origin", "VARCHAR(20)"),
    ("social_posts", "delivery", "VARCHAR(20)"),
    ("social_posts", "permalink", "TEXT"),
    ("social_posts", "post_snapshot", "JSON"),
    ("social_posts", "provider_snapshot", "JSONB"),
    ("social_posts", "tracking_error", "VARCHAR(80)"),
    ("content_sources", "social_enabled", "BOOLEAN NOT NULL DEFAULT TRUE"),
    ("ticker_performance_snapshots", "price_break_date", "VARCHAR(10)"),
    ("sector_performance_snapshots", "price_break_date", "VARCHAR(10)"),
    # Unified topic registry: tag rows pre-date these columns.
    ("tag_registry", "kind", "VARCHAR(20) NOT NULL DEFAULT 'tag'"),
    ("tag_registry", "exposure_id", "VARCHAR(120)"),
    ("tag_registry", "icon_id", "VARCHAR(64)"),
    ("tag_registry", "color_hex", "VARCHAR(16)"),
    ("tag_registry", "exposure_type", "VARCHAR(20)"),
    ("tag_registry", "description", "TEXT"),
    ("tag_registry", "members", "JSONB"),
    ("tag_registry", "aliases", "JSONB"),
    ("tag_registry", "field_owners", "JSONB"),
    ("tag_registry", "parent_id", "VARCHAR(120)"),
    ("tag_registry", "redirect_to", "VARCHAR(120)"),
    # stock_daily_ohlc predates the whole-market TWSE/TPEx fetcher (was an unused
    # US/yfinance orphan) — add the columns the fetcher writes.
    ("stock_daily_ohlc", "trading_value", "DOUBLE PRECISION"),
    ("stock_daily_ohlc", "source", "VARCHAR(20)"),
    # Screener (issue #450 Part A): 投信 net-shares column added on top of the
    # original foreign/total pair. Pre-existing rows stay NULL until the next
    # tw_daily_ohlc_refresh cycle backfills them.
    ("stock_institutional_daily", "trust_net_shares", "DOUBLE PRECISION"),
    # analytics_snapshots predates syndication read counts; rows before the
    # first snapshot that records them stay NULL, which the growth chart skips.
    ("analytics_snapshots", "vocus_reads", "INTEGER"),
    ("analytics_snapshots", "vocus_articles", "INTEGER"),
    ("analytics_snapshots", "substack_reads", "INTEGER"),
    ("analytics_snapshots", "substack_posts", "INTEGER"),
    # Membership entitlement (PR 1 — admin-granted only, no billing yet).
    ("users", "member_until", "TIMESTAMPTZ"),
    # Picks swiped away in 走勢. Pre-existing rows get '[]', not NULL — every
    # reader treats this as a list and create_all won't backfill a default.
    ("users", "dismissed_picks", "JSONB NOT NULL DEFAULT '[]'::jsonb"),
]


def _is_lock_timeout(exc: DBAPIError) -> bool:
    orig = exc.orig
    return (getattr(orig, "pgcode", None) or getattr(orig, "sqlstate", None)) == _PG_LOCK_NOT_AVAILABLE


def _boot_ddl(*statements: str) -> bool:
    """Run boot-time DDL as one transaction that gives up on a lock after a few seconds.

    Returns False (after a warning) when the lock was not available; any other error
    propagates.
    """
    try:
        with engine.begin() as conn:
            conn.execute(text(f"SET LOCAL lock_timeout = '{_BOOT_DDL_LOCK_TIMEOUT}'"))
            for statement in statements:
                conn.execute(text(statement))
        return True
    except DBAPIError as exc:
        if not _is_lock_timeout(exc):
            raise
        logger.warning(
            "Boot DDL skipped: no lock within %s (another session holds the table): %s",
            _BOOT_DDL_LOCK_TIMEOUT, " ".join(statements[0].split())[:120],
        )
        return False


def _pg_missing_columns(columns: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """The entries of ``columns`` whose table exists but lacks the column."""
    with engine.connect() as conn:
        existing = {
            (row[0], row[1])
            for row in conn.execute(text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = current_schema()"
            ))
        }
    tables = {table for table, _ in existing}
    return [c for c in columns if c[0] in tables and (c[0], c[1]) not in existing]


def _ensure_pg_columns() -> None:
    """Add the _PG_BOOT_COLUMNS that are missing.

    ``ADD COLUMN IF NOT EXISTS`` takes its ACCESS EXCLUSIVE lock before it looks at the
    column, so it queues behind any open reader even when there is nothing to add.
    Reading the catalog first means a normal boot issues no ALTER at all. When an ALTER
    is needed and the lock times out, the column really is missing — raise rather than
    serve queries against it.
    """
    for table, column, sql_type in _pg_missing_columns(_PG_BOOT_COLUMNS):
        if _boot_ddl(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {sql_type}"):
            continue
        # Another container booting the same release may have added it meanwhile.
        if _pg_missing_columns([(table, column, sql_type)]):
            raise RuntimeError(
                f"Boot DDL: {table}.{column} is missing and could not be added within "
                f"{_BOOT_DDL_LOCK_TIMEOUT} (table locked by another session — look for "
                f"'idle in transaction' in pg_stat_activity). Refusing to start."
            )


def create_all_tables():
    """
    Create all database tables based on SQLAlchemy models.
    
    Note: For production, use Alembic migrations instead.
    """
    if engine is None:
        init_engine()
    
    logger.info("Creating all database tables...")
    Base.metadata.create_all(bind=engine)
    # Billing PR 3b: safely upgrade the pre-existing subscription table and scope
    # outstanding mandates by gateway environment.
    subscription_indexes = (
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_one_open_sub_per_user_env "
        "ON subscriptions (user_id, gateway_env) "
        "WHERE status IN ('pending', 'active', 'cancelling')",
        "DROP INDEX IF EXISTS uq_one_active_sub_per_user",
    )
    if engine.dialect.name == "postgresql":
        # Add columns that may not exist on pre-existing tables (idempotent).
        _ensure_pg_columns()
        _boot_ddl(*subscription_indexes)
        _boot_ddl(
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
        )
        _boot_ddl(
            "CREATE INDEX IF NOT EXISTS ix_tag_registry_audit_exposure_id "
            "ON tag_registry_audit (exposure_id)"
        )
        _boot_ddl(
            "CREATE INDEX IF NOT EXISTS ix_tag_registry_audit_at "
            "ON tag_registry_audit (at)"
        )
        _boot_ddl(
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
        )
        _boot_ddl(
            """
            CREATE TABLE IF NOT EXISTS taxonomy_version (
                id INTEGER PRIMARY KEY DEFAULT 1,
                version INTEGER NOT NULL DEFAULT 0,
                updated_by VARCHAR(100),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        _boot_ddl(
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
        )
        _boot_ddl(
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
        )
        # DROP TRIGGER needs ACCESS EXCLUSIVE on tag_registry, so only (re)create the
        # trigger when it is absent; the function above carries the logic.
        with engine.connect() as conn:
            has_audit_trigger = conn.execute(text(
                "SELECT 1 FROM pg_trigger WHERE tgname = 'tag_registry_audit_iud' "
                "AND tgrelid = to_regclass('tag_registry')"
            )).first()
        if not has_audit_trigger:
            _boot_ddl(
                "DROP TRIGGER IF EXISTS tag_registry_audit_iud ON tag_registry",
                """
                CREATE TRIGGER tag_registry_audit_iud
                AFTER INSERT OR UPDATE OR DELETE ON tag_registry
                FOR EACH ROW EXECUTE FUNCTION tag_registry_audit_trigger()
                """,
            )
    elif engine.dialect.name == "sqlite":
        with engine.begin() as conn:
            billing_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(subscriptions)"))}
            if "paid_until" not in billing_cols:
                conn.execute(text("ALTER TABLE subscriptions ADD COLUMN paid_until TIMESTAMP"))
            if "promo_code" not in billing_cols:
                conn.execute(text("ALTER TABLE subscriptions ADD COLUMN promo_code VARCHAR(32)"))
            for statement in subscription_indexes:
                conn.execute(text(statement))
        # SQLite has no "ADD COLUMN IF NOT EXISTS" — check PRAGMA first.
        with engine.connect() as conn:
            cols = {row[1] for row in conn.execute(text("PRAGMA table_info(stock_translations)"))}
            if cols and "aliases" not in cols:
                conn.execute(text("ALTER TABLE stock_translations ADD COLUMN aliases JSON"))
                conn.commit()
            if cols and "name_preference" not in cols:
                conn.execute(text("ALTER TABLE stock_translations ADD COLUMN name_preference VARCHAR(10) DEFAULT 'auto'"))
                conn.commit()
            snap_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(analytics_snapshots)"))}
            for column in ("vocus_reads", "vocus_articles", "substack_reads", "substack_posts"):
                if snap_cols and column not in snap_cols:
                    conn.execute(text(f"ALTER TABLE analytics_snapshots ADD COLUMN {column} INTEGER"))
                    conn.commit()
            cs_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(content_sources)"))}
            if cs_cols and "cover_image_url" not in cs_cols:
                conn.execute(text("ALTER TABLE content_sources ADD COLUMN cover_image_url TEXT"))
                conn.commit()
            u_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(users)"))}
            if u_cols and "dismissed_picks" not in u_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN dismissed_picks JSON"))
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
            social_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(social_posts)"))}
            if social_cols and "provider_snapshot" not in social_cols:
                conn.execute(text("ALTER TABLE social_posts ADD COLUMN provider_snapshot JSON"))
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
            # Screener (issue #450 Part A): 投信 net-shares column.
            si_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(stock_institutional_daily)"))}
            if si_cols and "trust_net_shares" not in si_cols:
                conn.execute(text("ALTER TABLE stock_institutional_daily ADD COLUMN trust_net_shares FLOAT"))
                conn.commit()
            # Membership entitlement (PR 1 — admin-granted only, no billing yet).
            users_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(users)"))}
            if users_cols and "member_until" not in users_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN member_until TIMESTAMP"))
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
