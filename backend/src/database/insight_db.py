"""
PostgreSQL connection pool for ticker insights.
Data is prepared elsewhere; this module only provides read-only access.
Shares the main backend's Postgres connection (settings.postgres_connection_string).
"""
import logging
from contextlib import contextmanager
from typing import Optional, Generator, Any

from src.config import settings

logger = logging.getLogger(__name__)

_pool: Optional[Any] = None


def init_pool() -> None:
    """Initialize the insight Postgres connection pool."""
    global _pool
    conn_str = settings.postgres_connection_string
    if not conn_str:
        logger.warning("Insight Postgres not configured (no POSTGRES_PASSWORD).")
        return
    try:
        import psycopg2.pool
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=conn_str,
        )
        logger.info("Insight Postgres connection pool initialized (podcast_db).")
    except Exception as e:
        logger.warning("Could not initialize insight Postgres pool: %s", e)
        _pool = None


def close_pool() -> None:
    """Close the insight Postgres connection pool."""
    global _pool
    if _pool:
        try:
            _pool.closeall()
        except Exception as e:
            logger.warning("Error closing insight Postgres pool: %s", e)
        _pool = None


def get_pool() -> Optional[Any]:
    """Return the insight Postgres pool, or None if not configured."""
    return _pool


@contextmanager
def get_connection() -> Generator:
    """
    Yield a connection from the insight Postgres pool.
    Use as: with get_connection() as conn: ...
    """
    pool = get_pool()
    if not pool:
        raise RuntimeError("Insight Postgres pool not initialized; check POSTGRES_* env vars.")
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def is_available() -> bool:
    """Return True if the insight Postgres pool is initialized and usable."""
    return _pool is not None
