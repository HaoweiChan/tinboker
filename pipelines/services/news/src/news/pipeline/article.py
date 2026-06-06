"""Data carried through the news pipeline.

A :class:`FeedEntry` is what ``fetch_feeds`` yields; an :class:`Article`
accumulates state as it flows through dedup → extract → enrich → resolve →
wiki_write. Keeping one mutable record per article (rather than re-threading
tuples) mirrors ``EpisodeData`` in the podcast pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FeedEntry:
    """One article reference parsed from an RSS feed."""

    url: str
    title: str
    source: str
    published: str = ""  # YYYY-MM-DD, or "" when the feed omits a date
    rss_summary: str = ""
    rss_content: str = ""  # content:encoded, when the feed provides it


@dataclass
class Paragraph:
    """A single extracted paragraph with a stable content hash."""

    index: int
    hash: str
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "hash": self.hash, "text": self.text}


@dataclass
class Article:
    """An article as it moves through the pipeline."""

    url: str
    title: str
    source: str
    published: str = ""
    rss_summary: str = ""
    rss_content: str = ""

    # set by dedup
    slug: str = ""
    existing_content_hash: str | None = None

    # set by extract
    paragraphs: list[Paragraph] = field(default_factory=list)
    content_hash: str = ""

    # set by dict_prepass
    candidate_entities: list[str] = field(default_factory=list)

    # set by llm_enrich
    claims: list[dict[str, Any]] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    summary: str = ""
    raw_mentions: list[str] = field(default_factory=list)

    # set by resolve — the entity list ingest_news_article() consumes
    entities: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_feed_entry(cls, entry: FeedEntry) -> "Article":
        return cls(
            url=entry.url,
            title=entry.title,
            source=entry.source,
            published=entry.published,
            rss_summary=entry.rss_summary,
            rss_content=entry.rss_content,
        )

    @property
    def is_unchanged(self) -> bool:
        """True when an identical article (same content hash) is already ingested."""
        return (
            self.existing_content_hash is not None
            and self.content_hash != ""
            and self.existing_content_hash == self.content_hash
        )

    def paragraph_dicts(self) -> list[dict[str, Any]]:
        return [p.to_dict() for p in self.paragraphs]
