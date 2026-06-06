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
