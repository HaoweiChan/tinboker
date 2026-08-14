"""Consolidated content store — episodes, podcasts, tickers, insights, trending."""

from .factory import ContentRepositories, get_repositories
from .models import Episode, Podcast, Ticker, TickerInsight, TrendingTicker
from .repository import (
    EpisodeRepository,
    InMemoryEpisodeRepository,
    InMemoryPodcastRepository,
    InMemoryTickerInsightRepository,
    InMemoryTickerRepository,
    InMemoryTrendingTickerRepository,
    NullEpisodeRepository,
    NullPodcastRepository,
    NullTickerInsightRepository,
    NullTickerRepository,
    NullTrendingTickerRepository,
    PodcastRepository,
    TickerInsightRepository,
    TickerRepository,
    TrendingTickerRepository,
)

__all__ = [
    # models
    "Episode",
    "Podcast",
    "Ticker",
    "TickerInsight",
    "TrendingTicker",
    # ABCs
    "EpisodeRepository",
    "PodcastRepository",
    "TickerRepository",
    "TickerInsightRepository",
    "TrendingTickerRepository",
    # in-memory
    "InMemoryEpisodeRepository",
    "InMemoryPodcastRepository",
    "InMemoryTickerRepository",
    "InMemoryTickerInsightRepository",
    "InMemoryTrendingTickerRepository",
    # null
    "NullEpisodeRepository",
    "NullPodcastRepository",
    "NullTickerRepository",
    "NullTickerInsightRepository",
    "NullTrendingTickerRepository",
    # factory
    "ContentRepositories",
    "get_repositories",
]

def libpq_url(url: str | None) -> str | None:
    """A connection URL psycopg can actually parse.

    ``EPISODE_DATABASE_URL`` is stored in SQLAlchemy's form,
    ``postgresql+psycopg://…``, because most readers pass it to ``create_engine``. The
    ``+psycopg`` dialect suffix is SQLAlchemy-only: handed to ``psycopg.connect`` it fails
    with ``missing "=" after "postgresql+psycopg://…"``.

    One value with two consumers and no owner for the difference. This is that owner —
    call it at every ``psycopg.connect`` boundary rather than storing a second copy of the
    URL, which would drift the moment either changed.

    Left it broken for at least three days: the hourly trending timer failed 72 times in
    72 hours, and the podcast ingest swallowed the same error per-podcast and exited 0.
    """
    if not url:
        return url
    scheme, sep, rest = url.partition("://")
    return f"{scheme.split('+', 1)[0]}{sep}{rest}" if sep else url
