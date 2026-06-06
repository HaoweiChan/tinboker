"""Step 7 — write the enriched article into the shared Postgres wiki.

Delegates to ``wiki_builder.ingest_news_article``: it upserts the
``news_article`` page (claims + paragraph-level citations in frontmatter) and
append-only enriches the shared entity/topic pages.
"""

from __future__ import annotations

from typing import Callable

from shared.wiki_builder import ingest_news_article
from shared.wiki_builder.repository import WikiRepository

from ..article import Article


def wiki_write(
    article: Article,
    repo: WikiRepository,
    *,
    conflict_checker: Callable[[dict, dict], bool] | None = None,
) -> Article:
    """Persist the article and its entity/topic enrichment via the wiki repository.

    When ``conflict_checker`` is supplied, Phase-2 contradiction detection runs
    inside ``ingest_news_article``.
    """
    ingest_news_article(
        repository=repo,
        url=article.url,
        title=article.title,
        source=article.source,
        date=article.published or None,
        content_hash=article.content_hash,
        paragraphs=article.paragraph_dicts(),
        claims=article.claims,
        tags=article.tags,
        entities=article.entities,
        summary=article.summary,
        conflict_checker=conflict_checker,
    )
    return article
