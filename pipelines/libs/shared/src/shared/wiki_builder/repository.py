"""Storage abstraction for wiki content.

This is the seam that keeps the repo content-agnostic: the pipeline and the
HTTP API depend on :class:`WikiRepository`, never on a particular backend.

- :class:`PostgresWikiRepository` (in :mod:`.postgres_repo`) — production.
- :class:`InMemoryWikiRepository` — test double.
- :class:`NullWikiRepository` — explicit no-op used when ``WIKI_DATABASE_URL``
  is not configured (keeps wiki ingest "best-effort, non-fatal").
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from .links import extract_links
from .models import WikiLink, WikiPage

logger = logging.getLogger(__name__)


class WikiRepository(ABC):
    @abstractmethod
    def upsert_page(self, page: WikiPage) -> WikiPage:
        """Insert or replace a page (by ``(kind, slug)``) and rebuild its links."""

    @abstractmethod
    def get_page(self, kind: str, slug: str) -> WikiPage | None: ...

    @abstractmethod
    def list_pages(
        self,
        kind: str | None = None,
        *,
        frontmatter_filter: dict[str, Any] | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[WikiPage]: ...

    @abstractmethod
    def delete_page(self, kind: str, slug: str) -> bool: ...

    @abstractmethod
    def list_links(
        self,
        *,
        src: tuple[str, str] | None = None,
        dst: tuple[str, str] | None = None,
    ) -> list[WikiLink]: ...

    @property
    def backend_name(self) -> str:
        return type(self).__name__

    def health(self) -> dict[str, str]:
        return {"status": "healthy", "backend": self.backend_name}


def _frontmatter_matches(fm: dict[str, Any], flt: dict[str, Any]) -> bool:
    for key, want in flt.items():
        have = fm.get(key)
        if isinstance(have, list):
            if want not in have and str(want) not in [str(x) for x in have]:
                return False
        elif have != want and str(have) != str(want):
            return False
    return True


class InMemoryWikiRepository(WikiRepository):
    def __init__(self) -> None:
        self._pages: dict[tuple[str, str], WikiPage] = {}
        self._links: list[WikiLink] = []

    def upsert_page(self, page: WikiPage) -> WikiPage:
        now = datetime.now(timezone.utc)
        key = (page.kind, page.slug)
        existing = self._pages.get(key)
        page.created_at = existing.created_at if existing and existing.created_at else now
        page.updated_at = now
        self._pages[key] = page
        self._links = [link for link in self._links if (link.src_kind, link.src_slug) != key]
        self._links.extend(extract_links(page.kind, page.slug, page.body, page.frontmatter))
        return page

    def get_page(self, kind: str, slug: str) -> WikiPage | None:
        return self._pages.get((kind, slug))

    def list_pages(
        self,
        kind: str | None = None,
        *,
        frontmatter_filter: dict[str, Any] | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[WikiPage]:
        items = [p for p in self._pages.values() if kind is None or p.kind == kind]
        if frontmatter_filter:
            items = [p for p in items if _frontmatter_matches(p.frontmatter, frontmatter_filter)]
        items.sort(key=lambda p: (p.kind, p.slug))
        return items[offset : offset + limit]

    def delete_page(self, kind: str, slug: str) -> bool:
        key = (kind, slug)
        existed = key in self._pages
        self._pages.pop(key, None)
        self._links = [link for link in self._links if (link.src_kind, link.src_slug) != key]
        return existed

    def list_links(
        self,
        *,
        src: tuple[str, str] | None = None,
        dst: tuple[str, str] | None = None,
    ) -> list[WikiLink]:
        out = self._links
        if src is not None:
            out = [link for link in out if (link.src_kind, link.src_slug) == src]
        if dst is not None:
            out = [link for link in out if (link.dst_kind, link.dst_slug) == dst]
        return list(out)


class NullWikiRepository(WikiRepository):
    """No-op repository for when ``WIKI_DATABASE_URL`` is unset."""

    _warned = False

    def _warn(self) -> None:
        if not NullWikiRepository._warned:
            logger.warning(
                "WIKI_DATABASE_URL is not configured — wiki ingest is a no-op. "
                "Set WIKI_DATABASE_URL to persist wiki content."
            )
            NullWikiRepository._warned = True

    def upsert_page(self, page: WikiPage) -> WikiPage:
        self._warn()
        return page

    def get_page(self, kind: str, slug: str) -> WikiPage | None:
        self._warn()
        return None

    def list_pages(self, *args: Any, **kwargs: Any) -> list[WikiPage]:
        self._warn()
        return []

    def delete_page(self, kind: str, slug: str) -> bool:
        self._warn()
        return False

    def list_links(self, **kwargs: Any) -> list[WikiLink]:
        self._warn()
        return []

    def health(self) -> dict[str, str]:
        return {"status": "degraded", "backend": "null"}
