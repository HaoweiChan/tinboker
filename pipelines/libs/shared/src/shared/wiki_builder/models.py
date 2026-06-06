"""Content-agnostic data records for the wiki store.

A ``WikiPage`` is the unit of storage: ``(kind, slug)`` identity, a free-form
``frontmatter`` dict (whatever the content pipeline wants to attach), and a
``body`` of rendered prose. The repo never inspects ``frontmatter`` semantics —
that keeps this layer infra-only and content-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Recognised page kinds. New kinds are allowed at runtime — this is just a hint.
KINDS = ("episode", "entity", "topic", "supply_chain", "contract", "news_article")

# Maps the legacy on-disk directory names (and already-singular forms) to ``kind``.
DIR_TO_KIND: dict[str, str] = {
    "episodes": "episode",
    "entities": "entity",
    "topics": "topic",
    "supply-chain": "supply_chain",
    "news": "news_article",
    "episode": "episode",
    "entity": "entity",
    "topic": "topic",
    "supply_chain": "supply_chain",
    "news_article": "news_article",
}

# Reverse: ``kind`` -> the link prefix used inside ``[[...]]`` wikilinks.
KIND_TO_LINK_PREFIX: dict[str, str] = {
    "episode": "episodes",
    "entity": "entities",
    "topic": "topics",
    "supply_chain": "supply-chain",
    "news_article": "news",
}


@dataclass
class WikiPage:
    kind: str
    slug: str
    title: str = ""
    frontmatter: dict[str, Any] = field(default_factory=dict)
    body: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "slug": self.slug,
            "title": self.title,
            "frontmatter": self.frontmatter,
            "body": self.body,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass(frozen=True)
class WikiLink:
    src_kind: str
    src_slug: str
    dst_kind: str
    dst_slug: str
    context: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "src_kind": self.src_kind,
            "src_slug": self.src_slug,
            "dst_kind": self.dst_kind,
            "dst_slug": self.dst_slug,
            "context": self.context,
        }
