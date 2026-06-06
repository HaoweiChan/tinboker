"""tinboker-news — financial-news ingest into the shared Postgres wiki.

Ingest-only: a batch CLI (no HTTP server). It pulls RSS feeds, extracts article
text, derives typed claims + entity mentions, and writes them into the *same*
wiki that ``services/podcast`` writes to — via the ``tinboker-shared``
``wiki_builder.ingest_news_article`` entry point. The webui keeps reading the
existing ``/api/wiki/*`` routes on ``podcast-api.service``.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
