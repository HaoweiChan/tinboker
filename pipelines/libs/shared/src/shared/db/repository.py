"""Storage abstraction for the consolidated content store.

- :class:`EpisodeRepository` / :class:`PodcastRepository` / :class:`TickerRepository`
  / :class:`TickerInsightRepository` / :class:`TrendingTickerRepository` — ABCs.
- ``InMemory*`` variants — test doubles, no I/O.
- ``Null*`` variants — no-op used when ``EPISODE_DATABASE_URL`` is not configured.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

from .models import Episode, Podcast, Ticker, TickerInsight, TrendingTicker

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Episode
# ---------------------------------------------------------------------------


class EpisodeRepository(ABC):
    @abstractmethod
    def upsert(self, episode: Episode) -> Episode: ...

    @abstractmethod
    def get(self, episode_id: str) -> Optional[Episode]: ...

    @abstractmethod
    def list_recent(self, *, limit: int = 20, offset: int = 0) -> list[Episode]: ...

    @abstractmethod
    def list_by_podcast(
        self, podcast_name: str, *, limit: int = 20, offset: int = 0
    ) -> list[Episode]: ...

    @abstractmethod
    def list_by_ticker(self, ticker: str, *, limit: int = 20) -> list[Episode]: ...

    @abstractmethod
    def list_by_tag(self, tag: str, *, limit: int = 20) -> list[Episode]: ...

    @abstractmethod
    def count(self) -> int: ...

    @abstractmethod
    def list_all_tags(self) -> list[tuple[str, int]]:
        """Return (tag, count) pairs ordered by count descending."""
        ...


class InMemoryEpisodeRepository(EpisodeRepository):
    def __init__(self) -> None:
        self._store: dict[str, Episode] = {}

    def upsert(self, episode: Episode) -> Episode:
        now = datetime.now(timezone.utc)
        existing = self._store.get(episode.id)
        episode.created_at = existing.created_at if existing and existing.created_at else now
        episode.updated_at = now
        self._store[episode.id] = episode
        return episode

    def get(self, episode_id: str) -> Optional[Episode]:
        return self._store.get(episode_id)

    def list_recent(self, *, limit: int = 20, offset: int = 0) -> list[Episode]:
        items = sorted(
            self._store.values(),
            key=lambda e: e.created_time or 0,
            reverse=True,
        )
        return items[offset : offset + limit]

    def list_by_podcast(
        self, podcast_name: str, *, limit: int = 20, offset: int = 0
    ) -> list[Episode]:
        items = [e for e in self._store.values() if e.podcast_name == podcast_name]
        items.sort(key=lambda e: e.created_time or 0, reverse=True)
        return items[offset : offset + limit]

    def list_by_ticker(self, ticker: str, *, limit: int = 20) -> list[Episode]:
        items = [e for e in self._store.values() if ticker in e.related_tickers]
        items.sort(key=lambda e: e.created_time or 0, reverse=True)
        return items[:limit]

    def list_by_tag(self, tag: str, *, limit: int = 20) -> list[Episode]:
        items = [e for e in self._store.values() if tag in e.tags]
        items.sort(key=lambda e: e.created_time or 0, reverse=True)
        return items[:limit]

    def count(self) -> int:
        return len(self._store)

    def list_all_tags(self) -> list[tuple[str, int]]:
        from collections import Counter
        counter: Counter[str] = Counter()
        for ep in self._store.values():
            counter.update(ep.tags)
        return sorted(counter.items(), key=lambda x: -x[1])


class NullEpisodeRepository(EpisodeRepository):
    _warned = False

    def _warn(self) -> None:
        if not NullEpisodeRepository._warned:
            logger.warning("EPISODE_DATABASE_URL not set — episode DB writes are no-ops.")
            NullEpisodeRepository._warned = True

    def upsert(self, episode: Episode) -> Episode:
        self._warn()
        return episode

    def get(self, episode_id: str) -> Optional[Episode]:
        self._warn()
        return None

    def list_recent(self, **_: object) -> list[Episode]:
        self._warn()
        return []

    def list_by_podcast(self, podcast_name: str, **_: object) -> list[Episode]:
        self._warn()
        return []

    def list_by_ticker(self, ticker: str, **_: object) -> list[Episode]:
        self._warn()
        return []

    def list_by_tag(self, tag: str, **_: object) -> list[Episode]:
        self._warn()
        return []

    def count(self) -> int:
        return 0

    def list_all_tags(self) -> list[tuple[str, int]]:
        return []


# ---------------------------------------------------------------------------
# Podcast
# ---------------------------------------------------------------------------


class PodcastRepository(ABC):
    @abstractmethod
    def upsert(self, podcast: Podcast) -> Podcast: ...

    @abstractmethod
    def get(self, name: str) -> Optional[Podcast]: ...

    @abstractmethod
    def list_all(self) -> list[Podcast]: ...


class InMemoryPodcastRepository(PodcastRepository):
    def __init__(self) -> None:
        self._store: dict[str, Podcast] = {}

    def upsert(self, podcast: Podcast) -> Podcast:
        now = datetime.now(timezone.utc)
        existing = self._store.get(podcast.name)
        podcast.created_at = existing.created_at if existing and existing.created_at else now
        podcast.updated_at = now
        self._store[podcast.name] = podcast
        return podcast

    def get(self, name: str) -> Optional[Podcast]:
        return self._store.get(name)

    def list_all(self) -> list[Podcast]:
        return sorted(self._store.values(), key=lambda p: p.name)


class NullPodcastRepository(PodcastRepository):
    def upsert(self, podcast: Podcast) -> Podcast:
        return podcast

    def get(self, name: str) -> Optional[Podcast]:
        return None

    def list_all(self) -> list[Podcast]:
        return []


# ---------------------------------------------------------------------------
# Ticker
# ---------------------------------------------------------------------------


class TickerRepository(ABC):
    @abstractmethod
    def upsert(self, ticker: Ticker) -> Ticker: ...

    @abstractmethod
    def get(self, symbol: str) -> Optional[Ticker]: ...

    @abstractmethod
    def list_all(self) -> list[Ticker]: ...


class InMemoryTickerRepository(TickerRepository):
    def __init__(self) -> None:
        self._store: dict[str, Ticker] = {}

    def upsert(self, ticker: Ticker) -> Ticker:
        self._store[ticker.symbol] = ticker
        return ticker

    def get(self, symbol: str) -> Optional[Ticker]:
        return self._store.get(symbol)

    def list_all(self) -> list[Ticker]:
        return sorted(self._store.values(), key=lambda t: t.symbol)


class NullTickerRepository(TickerRepository):
    def upsert(self, ticker: Ticker) -> Ticker:
        return ticker

    def get(self, symbol: str) -> Optional[Ticker]:
        return None

    def list_all(self) -> list[Ticker]:
        return []


# ---------------------------------------------------------------------------
# TickerInsight
# ---------------------------------------------------------------------------


class TickerInsightRepository(ABC):
    @abstractmethod
    def upsert(self, insight: TickerInsight) -> TickerInsight: ...

    @abstractmethod
    def get(self, episode_id: str, ticker: str) -> Optional[TickerInsight]: ...

    @abstractmethod
    def list_by_ticker(
        self,
        ticker: str,
        *,
        start_date: Optional[str] = None,  # YYYY-MM-DD
        end_date: Optional[str] = None,
        limit: int = 100,
    ) -> list[TickerInsight]: ...

    @abstractmethod
    def list_by_podcaster(
        self,
        podcaster: str,
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
    ) -> list[TickerInsight]: ...

    @abstractmethod
    def list_by_episode(self, episode_id: str) -> list[TickerInsight]: ...


class InMemoryTickerInsightRepository(TickerInsightRepository):
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], TickerInsight] = {}

    def upsert(self, insight: TickerInsight) -> TickerInsight:
        if not insight.created_at:
            insight.created_at = datetime.now(timezone.utc)
        self._store[(insight.episode_id, insight.ticker)] = insight
        return insight

    def get(self, episode_id: str, ticker: str) -> Optional[TickerInsight]:
        return self._store.get((episode_id, ticker))

    def list_by_ticker(
        self,
        ticker: str,
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
    ) -> list[TickerInsight]:
        items = [i for i in self._store.values() if i.ticker == ticker]
        if start_date:
            items = [i for i in items if (i.podcast_launch_time or "") >= start_date]
        if end_date:
            items = [i for i in items if (i.podcast_launch_time or "") <= end_date + "Z"]
        items.sort(key=lambda i: i.podcast_launch_time or "", reverse=True)
        return items[:limit]

    def list_by_podcaster(
        self,
        podcaster: str,
        *,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
    ) -> list[TickerInsight]:
        items = [i for i in self._store.values() if i.podcaster == podcaster]
        if start_date:
            items = [i for i in items if (i.podcast_launch_time or "") >= start_date]
        if end_date:
            items = [i for i in items if (i.podcast_launch_time or "") <= end_date + "Z"]
        items.sort(key=lambda i: i.podcast_launch_time or "", reverse=True)
        return items[:limit]

    def list_by_episode(self, episode_id: str) -> list[TickerInsight]:
        return [i for i in self._store.values() if i.episode_id == episode_id]


class NullTickerInsightRepository(TickerInsightRepository):
    def upsert(self, insight: TickerInsight) -> TickerInsight:
        return insight

    def get(self, episode_id: str, ticker: str) -> Optional[TickerInsight]:
        return None

    def list_by_ticker(self, ticker: str, **_: object) -> list[TickerInsight]:
        return []

    def list_by_podcaster(self, podcaster: str, **_: object) -> list[TickerInsight]:
        return []

    def list_by_episode(self, episode_id: str) -> list[TickerInsight]:
        return []


# ---------------------------------------------------------------------------
# TrendingTicker
# ---------------------------------------------------------------------------


class TrendingTickerRepository(ABC):
    @abstractmethod
    def upsert(self, trending: TrendingTicker) -> TrendingTicker: ...

    @abstractmethod
    def get(self, ticker: str) -> Optional[TrendingTicker]: ...

    @abstractmethod
    def list_trending(self, *, days: int = 30, limit: int = 100) -> list[TrendingTicker]: ...


class InMemoryTrendingTickerRepository(TrendingTickerRepository):
    def __init__(self) -> None:
        self._store: dict[str, TrendingTicker] = {}

    def upsert(self, trending: TrendingTicker) -> TrendingTicker:
        if not trending.computed_at:
            trending.computed_at = datetime.now(timezone.utc)
        self._store[trending.ticker] = trending
        return trending

    def get(self, ticker: str) -> Optional[TrendingTicker]:
        return self._store.get(ticker)

    def list_trending(self, *, days: int = 30, limit: int = 100) -> list[TrendingTicker]:
        def _count(t: TrendingTicker) -> int:
            if days == 30:
                return t.count_30d
            if days == 90:
                return t.count_90d
            return t.count_all_time

        items = sorted(self._store.values(), key=_count, reverse=True)
        return items[:limit]


class NullTrendingTickerRepository(TrendingTickerRepository):
    def upsert(self, trending: TrendingTicker) -> TrendingTicker:
        return trending

    def get(self, ticker: str) -> Optional[TrendingTicker]:
        return None

    def list_trending(self, **_: object) -> list[TrendingTicker]:
        return []
