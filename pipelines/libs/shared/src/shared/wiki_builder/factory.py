"""Pick a repository implementation from the environment.

``WIKI_DATABASE_URL`` set  -> Postgres-backed repositories
``WIKI_DATABASE_URL`` unset -> :class:`NullWikiRepository` (no-op, warns once) / None
"""

from __future__ import annotations

import os

from .repository import NullWikiRepository, WikiRepository


def get_repository(database_url: str | None = None) -> WikiRepository:
    url = database_url if database_url is not None else os.environ.get("WIKI_DATABASE_URL")
    if not url:
        return NullWikiRepository()
    from .postgres_repo import PostgresWikiRepository

    return PostgresWikiRepository(url)


def get_show_repository(database_url: str | None = None):
    """Return a :class:`PostgresShowRepository` or ``None`` if no DB URL is configured."""
    url = database_url if database_url is not None else os.environ.get("WIKI_DATABASE_URL")
    if not url:
        return None
    import sqlalchemy as sa

    from .shows import PostgresShowRepository

    engine = sa.create_engine(url, pool_pre_ping=True, future=True)
    return PostgresShowRepository(engine)
