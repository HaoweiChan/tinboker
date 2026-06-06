"""Postgres-backed :class:`WikiRepository`.

Schema (also created by :meth:`PostgresWikiRepository.init_schema`)::

    wiki_pages(id, kind, slug, title, frontmatter JSONB, body, created_at, updated_at)
        UNIQUE (kind, slug)
    wiki_links(src_kind, src_slug, dst_kind, dst_slug, context)
        PK (src_kind, src_slug, dst_kind, dst_slug)
        FK (src_kind, src_slug) -> wiki_pages(kind, slug) ON DELETE CASCADE

``frontmatter`` is opaque JSON — the schema never needs to change when the
*content* model changes. ``wiki_links`` is a projection rebuilt on every upsert.
"""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .links import extract_links
from .models import WikiLink, WikiPage
from .repository import WikiRepository, _frontmatter_matches


def _json_dumps(obj: Any) -> str:
    # ``frontmatter`` is opaque content metadata; coerce non-JSON scalars (e.g. YAML dates,
    # Decimals) to strings so any well-formed metadata round-trips through JSONB.
    return json.dumps(obj, ensure_ascii=False, default=str)


metadata = sa.MetaData()

wiki_pages = sa.Table(
    "wiki_pages",
    metadata,
    sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("slug", sa.Text, nullable=False),
    sa.Column("title", sa.Text, nullable=False, server_default=""),
    sa.Column("frontmatter", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    sa.Column("body", sa.Text, nullable=False, server_default=""),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.Column(
        "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.UniqueConstraint("kind", "slug", name="uq_wiki_pages_kind_slug"),
    sa.Index("ix_wiki_pages_kind", "kind"),
    sa.Index("ix_wiki_pages_frontmatter", "frontmatter", postgresql_using="gin"),
)

wiki_links = sa.Table(
    "wiki_links",
    metadata,
    sa.Column("src_kind", sa.Text, primary_key=True),
    sa.Column("src_slug", sa.Text, primary_key=True),
    sa.Column("dst_kind", sa.Text, primary_key=True),
    sa.Column("dst_slug", sa.Text, primary_key=True),
    sa.Column("context", sa.Text, nullable=False, server_default=""),
    sa.ForeignKeyConstraint(
        ["src_kind", "src_slug"],
        ["wiki_pages.kind", "wiki_pages.slug"],
        ondelete="CASCADE",
        name="fk_wiki_links_src",
    ),
    sa.Index("ix_wiki_links_dst", "dst_kind", "dst_slug"),
)

podcast_shows = sa.Table(
    "podcast_shows",
    metadata,
    sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
    sa.Column("slug", sa.Text, nullable=False, unique=True),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("rss_url", sa.Text, nullable=False),
    sa.Column("spotify_url", sa.Text, nullable=True),
    sa.Column("episode_limit", sa.Integer, nullable=False, server_default="10"),
    sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
    sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
    sa.Column(
        "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    ),
)


def _row_to_page(row: sa.Row) -> WikiPage:
    return WikiPage(
        kind=row.kind,
        slug=row.slug,
        title=row.title or "",
        frontmatter=dict(row.frontmatter or {}),
        body=row.body or "",
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class PostgresWikiRepository(WikiRepository):
    def __init__(self, database_url: str) -> None:
        self.engine = sa.create_engine(
            database_url, pool_pre_ping=True, future=True, json_serializer=_json_dumps
        )

    # --- schema management ------------------------------------------------
    def init_schema(self) -> None:
        """Create the wiki tables if they do not exist (idempotent)."""
        metadata.create_all(self.engine)

    def health(self) -> dict[str, str]:
        try:
            with self.engine.connect() as conn:
                conn.execute(sa.text("SELECT 1"))
            return {"status": "healthy", "backend": "postgres"}
        except Exception as exc:  # pragma: no cover - depends on a live DB
            return {"status": "degraded", "backend": "postgres", "error": str(exc)}

    # --- CRUD -------------------------------------------------------------
    def upsert_page(self, page: WikiPage) -> WikiPage:
        with self.engine.begin() as conn:
            stmt = pg_insert(wiki_pages).values(
                kind=page.kind,
                slug=page.slug,
                title=page.title,
                frontmatter=page.frontmatter,
                body=page.body,
                updated_at=sa.func.now(),
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["kind", "slug"],
                set_={
                    "title": stmt.excluded.title,
                    "frontmatter": stmt.excluded.frontmatter,
                    "body": stmt.excluded.body,
                    "updated_at": sa.func.now(),
                },
            )
            conn.execute(stmt)

            conn.execute(
                sa.delete(wiki_links).where(
                    wiki_links.c.src_kind == page.kind,
                    wiki_links.c.src_slug == page.slug,
                )
            )
            links = extract_links(page.kind, page.slug, page.body, page.frontmatter)
            if links:
                conn.execute(
                    sa.insert(wiki_links),
                    [
                        {
                            "src_kind": link.src_kind,
                            "src_slug": link.src_slug,
                            "dst_kind": link.dst_kind,
                            "dst_slug": link.dst_slug,
                            "context": link.context,
                        }
                        for link in links
                    ],
                )

            row = conn.execute(
                sa.select(wiki_pages).where(
                    wiki_pages.c.kind == page.kind, wiki_pages.c.slug == page.slug
                )
            ).one()
        return _row_to_page(row)

    def get_page(self, kind: str, slug: str) -> WikiPage | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                sa.select(wiki_pages).where(wiki_pages.c.kind == kind, wiki_pages.c.slug == slug)
            ).one_or_none()
        return _row_to_page(row) if row is not None else None

    def list_pages(
        self,
        kind: str | None = None,
        *,
        frontmatter_filter: dict[str, Any] | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[WikiPage]:
        query = sa.select(wiki_pages)
        if kind is not None:
            query = query.where(wiki_pages.c.kind == kind)
        query = query.order_by(wiki_pages.c.kind, wiki_pages.c.slug)
        # JSONB filtering is done in Python for simplicity (small dataset, and it
        # keeps list/scalar matching identical to the in-memory backend).
        with self.engine.connect() as conn:
            rows = conn.execute(query).all()
        pages = [_row_to_page(r) for r in rows]
        if frontmatter_filter:
            pages = [p for p in pages if _frontmatter_matches(p.frontmatter, frontmatter_filter)]
        return pages[offset : offset + limit]

    def delete_page(self, kind: str, slug: str) -> bool:
        with self.engine.begin() as conn:
            result = conn.execute(
                sa.delete(wiki_pages).where(wiki_pages.c.kind == kind, wiki_pages.c.slug == slug)
            )
        return result.rowcount > 0

    def list_links(
        self,
        *,
        src: tuple[str, str] | None = None,
        dst: tuple[str, str] | None = None,
    ) -> list[WikiLink]:
        query = sa.select(wiki_links)
        if src is not None:
            query = query.where(wiki_links.c.src_kind == src[0], wiki_links.c.src_slug == src[1])
        if dst is not None:
            query = query.where(wiki_links.c.dst_kind == dst[0], wiki_links.c.dst_slug == dst[1])
        with self.engine.connect() as conn:
            rows = conn.execute(query).all()
        return [
            WikiLink(r.src_kind, r.src_slug, r.dst_kind, r.dst_slug, r.context or "") for r in rows
        ]
