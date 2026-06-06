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
