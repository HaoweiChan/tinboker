"""Pick content-store repository implementations from the environment.

``EPISODE_DATABASE_URL`` set   -> Postgres implementations (all 5 repos share one engine)
``EPISODE_DATABASE_URL`` unset -> Null implementations (no-op, warns once on first use)
"""

from __future__ import annotations

import os
from typing import NamedTuple

from .repository import (
    EpisodeRepository,
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


class ContentRepositories(NamedTuple):
    episodes: EpisodeRepository
    podcasts: PodcastRepository
    tickers: TickerRepository
    ticker_insights: TickerInsightRepository
    trending_tickers: TrendingTickerRepository


def get_repositories(database_url: str | None = None) -> ContentRepositories:
    """Return all content repositories for the given DB URL (or $EPISODE_DATABASE_URL).

    Calling ``init_schema()`` on the returned repos is the caller's responsibility
    (the podcast API does this at startup; scripts call it explicitly).
    """
    url = database_url if database_url is not None else os.environ.get("EPISODE_DATABASE_URL")
    if not url:
        return ContentRepositories(
            episodes=NullEpisodeRepository(),
            podcasts=NullPodcastRepository(),
            tickers=NullTickerRepository(),
            ticker_insights=NullTickerInsightRepository(),
            trending_tickers=NullTrendingTickerRepository(),
        )

    import sqlalchemy as sa

    from .postgres_repo import (
        PostgresEpisodeRepository,
        PostgresPodcastRepository,
        PostgresTickerInsightRepository,
        PostgresTickerRepository,
        PostgresTrendingTickerRepository,
        init_schema,
    )

    engine = sa.create_engine(url, pool_pre_ping=True)
    init_schema(engine)

    return ContentRepositories(
        episodes=PostgresEpisodeRepository(engine),
        podcasts=PostgresPodcastRepository(engine),
        tickers=PostgresTickerRepository(engine),
        ticker_insights=PostgresTickerInsightRepository(engine),
        trending_tickers=PostgresTrendingTickerRepository(engine),
    )
