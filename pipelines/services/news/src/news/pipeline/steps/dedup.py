"""Step 2 — deterministic slug + duplicate detection.

The slug is a hash of the canonical URL, so re-seeing the same article always
maps to the same ``news_article`` page. Whether to *skip* it is decided after
extraction (:func:`is_duplicate`): an existing page with an identical content
hash means nothing changed.
"""

from __future__ import annotations

from shared.wiki_builder import news_slug
from shared.wiki_builder.repository import WikiRepository

from ..article import Article, FeedEntry


def dedup(entries: list[FeedEntry], repo: WikiRepository) -> list[Article]:
    """Convert feed entries to :class:`Article` records.

    Attaches the deterministic ``slug`` and the existing page's ``content_hash``
    (when the article was ingested before). Entries that collapse to the same
    slug within this batch are de-duplicated here.
    """
    articles: list[Article] = []
    seen: set[str] = set()
    for entry in entries:
        slug = news_slug(entry.url)
        if slug in seen:
            continue
        seen.add(slug)
        article = Article.from_feed_entry(entry)
        article.slug = slug
        existing = repo.get_page("news_article", slug)
        article.existing_content_hash = (
            str(existing.frontmatter.get("content_hash") or "") or None
            if existing is not None
            else None
        )
        articles.append(article)
    return articles


def is_duplicate(article: Article) -> bool:
    """True when this article is already ingested unchanged — skip re-ingesting it."""
    return article.is_unchanged
