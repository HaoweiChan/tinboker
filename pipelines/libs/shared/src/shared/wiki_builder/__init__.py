"""Shared wiki builder.

Persists episode/entity/topic/supply-chain *content* into a pluggable
:class:`WikiRepository` (Postgres in production). Markdown is a *view*
(see :mod:`.views`), never the storage format — so this repo stays
infra-only and content-agnostic.
"""

from .factory import get_repository, get_show_repository
from .ingest import ingest_episode, ingest_news_article, ingest_supply_chain
from .models import KINDS, WikiLink, WikiPage
from .records import (
    CLAIM_STATUSES,
    EVENT_TYPES,
    normalize_claim,
    normalize_event_type,
    render_entity_page,
    render_episode_page,
    render_news_article_page,
    render_supply_chain_page,
    render_topic_page,
)
from .repository import InMemoryWikiRepository, NullWikiRepository, WikiRepository
from .shows import PodcastShow, PostgresShowRepository
from .slugify import canonicalize_url, episode_slug, news_slug, slugify, ticker_slug
from .views import build_index_markdown, page_to_markdown

__all__ = [
    "KINDS",
    "EVENT_TYPES",
    "CLAIM_STATUSES",
    "WikiPage",
    "WikiLink",
    "WikiRepository",
    "InMemoryWikiRepository",
    "NullWikiRepository",
    "get_repository",
    "get_show_repository",
    "ingest_episode",
    "ingest_news_article",
    "ingest_supply_chain",
    "render_episode_page",
    "render_entity_page",
    "render_topic_page",
    "render_supply_chain_page",
    "render_news_article_page",
    "normalize_claim",
    "normalize_event_type",
    "page_to_markdown",
    "build_index_markdown",
    "slugify",
    "ticker_slug",
    "episode_slug",
    "news_slug",
    "canonicalize_url",
    "PodcastShow",
    "PostgresShowRepository",
]
