"""Step 4 — deterministic dictionary prepass (the "NLP before LLM" cheap pass).

Matches paragraph + title text against the alias index and records the
candidate canonical entities, which become hints for the enrichment LLM call.
"""

from __future__ import annotations

from ...alias_index import AliasIndex
from ..article import Article


def dict_prepass(article: Article, index: AliasIndex) -> Article:
    """Populate ``article.candidate_entities`` with canonical slugs found by the dictionary."""
    found: dict[str, None] = {}
    for entity in index.find_in_text(article.title):
        found.setdefault(entity.slug, None)
    for para in article.paragraphs:
        for entity in index.find_in_text(para.text):
            found.setdefault(entity.slug, None)
    article.candidate_entities = list(found)
    return article
