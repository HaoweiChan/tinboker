"""Contract tests for the in-memory content-store repositories.

Mirrors the style of test_wiki_repository.py — no I/O, no network.
"""



from shared.db import (
    Episode,
    InMemoryEpisodeRepository,
    InMemoryPodcastRepository,
    InMemoryTickerInsightRepository,
    InMemoryTickerRepository,
    InMemoryTrendingTickerRepository,
    NullEpisodeRepository,
    Podcast,
    Ticker,
    TickerInsight,
    TrendingTicker,
    get_repositories,
)

# ---------------------------------------------------------------------------
# EpisodeRepository
# ---------------------------------------------------------------------------


def _ep(id: str = "ep1", podcast_name: str = "TestPod", **kw) -> Episode:
    return Episode(id=id, podcast_name=podcast_name, **kw)


def test_episode_upsert_get():
    repo = InMemoryEpisodeRepository()
    ep = repo.upsert(_ep("e1", episode_title="Hello"))
    assert ep.created_at is not None
    assert ep.updated_at is not None

    got = repo.get("e1")
    assert got is not None and got.episode_title == "Hello"


def test_episode_upsert_preserves_created_at():
    repo = InMemoryEpisodeRepository()
    first = repo.upsert(_ep("e1"))
    ts = first.created_at
    second = repo.upsert(_ep("e1", episode_title="Updated"))
    assert second.created_at == ts
    assert repo.get("e1").episode_title == "Updated"


def test_episode_list_recent():
    repo = InMemoryEpisodeRepository()
    repo.upsert(_ep("e1", created_time=1000))
    repo.upsert(_ep("e2", created_time=3000))
    repo.upsert(_ep("e3", created_time=2000))

    recent = repo.list_recent(limit=2)
    assert [e.id for e in recent] == ["e2", "e3"]

    all_ep = repo.list_recent(limit=10)
    assert len(all_ep) == 3


def test_episode_list_recent_returns_empty_when_no_data():
    repo = InMemoryEpisodeRepository()
    assert repo.list_recent(limit=5) == []


def test_episode_list_by_podcast():
    repo = InMemoryEpisodeRepository()
    repo.upsert(_ep("e1", podcast_name="A", created_time=1000))
    repo.upsert(_ep("e2", podcast_name="B", created_time=2000))
    repo.upsert(_ep("e3", podcast_name="A", created_time=3000))

    assert [e.id for e in repo.list_by_podcast("A")] == ["e3", "e1"]
    assert [e.id for e in repo.list_by_podcast("B")] == ["e2"]
    assert repo.list_by_podcast("C") == []


def test_episode_list_by_ticker():
    repo = InMemoryEpisodeRepository()
    repo.upsert(_ep("e1", related_tickers=["NVDA", "AAPL"], created_time=1000))
    repo.upsert(_ep("e2", related_tickers=["NVDA"], created_time=2000))
    repo.upsert(_ep("e3", related_tickers=["AAPL"], created_time=3000))

    nvda = repo.list_by_ticker("NVDA")
    assert [e.id for e in nvda] == ["e2", "e1"]
    assert repo.list_by_ticker("MSFT") == []


def test_episode_list_by_tag():
    repo = InMemoryEpisodeRepository()
    repo.upsert(_ep("e1", tags=["AI", "半導體"], created_time=1000))
    repo.upsert(_ep("e2", tags=["AI"], created_time=2000))

    ai = repo.list_by_tag("AI")
    assert [e.id for e in ai] == ["e2", "e1"]
    assert repo.list_by_tag("missing") == []


def test_episode_count():
    repo = InMemoryEpisodeRepository()
    assert repo.count() == 0
    repo.upsert(_ep("e1"))
    repo.upsert(_ep("e2"))
    assert repo.count() == 2


# ---------------------------------------------------------------------------
# PodcastRepository
# ---------------------------------------------------------------------------


def test_podcast_upsert_get_list():
    repo = InMemoryPodcastRepository()
    p = repo.upsert(Podcast(name="股癌", language="zh"))
    assert p.created_at is not None

    got = repo.get("股癌")
    assert got is not None and got.language == "zh"
    assert repo.get("missing") is None

    repo.upsert(Podcast(name="Dealcast", language="en"))
    all_pods = repo.list_all()
    assert len(all_pods) == 2
    assert all_pods[0].name == "Dealcast"  # sorted alphabetically


def test_podcast_upsert_preserves_created_at():
    repo = InMemoryPodcastRepository()
    first = repo.upsert(Podcast(name="P"))
    ts = first.created_at
    second = repo.upsert(Podcast(name="P", description="Updated"))
    assert second.created_at == ts
    assert repo.get("P").description == "Updated"


# ---------------------------------------------------------------------------
# TickerRepository
# ---------------------------------------------------------------------------


def test_ticker_upsert_get_list():
    repo = InMemoryTickerRepository()
    repo.upsert(Ticker(symbol="NVDA", name="NVIDIA", market="US"))
    repo.upsert(Ticker(symbol="2330", name="台積電", market="TW"))

    assert repo.get("NVDA").name == "NVIDIA"
    assert repo.get("MISSING") is None
    assert [t.symbol for t in repo.list_all()] == ["2330", "NVDA"]  # sorted


# ---------------------------------------------------------------------------
# TickerInsightRepository
# ---------------------------------------------------------------------------


def _insight(episode_id: str = "e1", ticker: str = "NVDA", **kw) -> TickerInsight:
    return TickerInsight(episode_id=episode_id, ticker=ticker, **kw)


def test_ticker_insight_upsert_get():
    repo = InMemoryTickerInsightRepository()
    ins = repo.upsert(_insight("e1", "NVDA", bluf_thesis="Bullish on AI"))
    assert ins.created_at is not None
    assert repo.get("e1", "NVDA").bluf_thesis == "Bullish on AI"
    assert repo.get("e1", "AAPL") is None


def test_ticker_insight_list_by_ticker():
    repo = InMemoryTickerInsightRepository()
    repo.upsert(_insight("e1", "NVDA", podcaster="A", podcast_launch_time="2026-05-10T08:00:00Z"))
    repo.upsert(_insight("e2", "NVDA", podcaster="B", podcast_launch_time="2026-05-12T08:00:00Z"))
    repo.upsert(_insight("e3", "AAPL", podcaster="A", podcast_launch_time="2026-05-11T08:00:00Z"))

    nvda = repo.list_by_ticker("NVDA")
    assert [i.episode_id for i in nvda] == ["e2", "e1"]  # newest first

    filtered = repo.list_by_ticker("NVDA", start_date="2026-05-11")
    assert [i.episode_id for i in filtered] == ["e2"]


def test_ticker_insight_list_by_podcaster():
    repo = InMemoryTickerInsightRepository()
    repo.upsert(_insight("e1", "NVDA", podcaster="股癌", podcast_launch_time="2026-05-10T08:00:00Z"))
    repo.upsert(_insight("e2", "AAPL", podcaster="股癌", podcast_launch_time="2026-05-12T08:00:00Z"))
    repo.upsert(_insight("e3", "NVDA", podcaster="M觀點", podcast_launch_time="2026-05-11T08:00:00Z"))

    gooaye = repo.list_by_podcaster("股癌")
    assert len(gooaye) == 2
    assert gooaye[0].episode_id == "e2"  # newest first


def test_ticker_insight_list_by_episode():
    repo = InMemoryTickerInsightRepository()
    repo.upsert(_insight("e1", "NVDA"))
    repo.upsert(_insight("e1", "AAPL"))
    repo.upsert(_insight("e2", "NVDA"))

    assert len(repo.list_by_episode("e1")) == 2
    assert len(repo.list_by_episode("e2")) == 1


# ---------------------------------------------------------------------------
# TrendingTickerRepository
# ---------------------------------------------------------------------------


def test_trending_ticker_upsert_get():
    repo = InMemoryTrendingTickerRepository()
    t = repo.upsert(TrendingTicker(ticker="NVDA", count_30d=10, count_90d=25))
    assert t.computed_at is not None
    assert repo.get("NVDA").count_30d == 10
    assert repo.get("MISSING") is None


def test_trending_ticker_list_trending():
    repo = InMemoryTrendingTickerRepository()
    repo.upsert(TrendingTicker(ticker="NVDA", count_30d=10, count_90d=25, count_all_time=100))
    repo.upsert(TrendingTicker(ticker="AAPL", count_30d=15, count_90d=20, count_all_time=80))
    repo.upsert(TrendingTicker(ticker="MSFT", count_30d=5, count_90d=30, count_all_time=60))

    by_30d = repo.list_trending(days=30)
    assert [t.ticker for t in by_30d] == ["AAPL", "NVDA", "MSFT"]

    by_90d = repo.list_trending(days=90)
    assert [t.ticker for t in by_90d] == ["MSFT", "NVDA", "AAPL"]

    by_all = repo.list_trending(days=0)
    assert [t.ticker for t in by_all] == ["NVDA", "AAPL", "MSFT"]


def test_trending_ticker_list_limit():
    repo = InMemoryTrendingTickerRepository()
    for i in range(5):
        repo.upsert(TrendingTicker(ticker=f"T{i}", count_30d=i))
    assert len(repo.list_trending(limit=3)) == 3


# ---------------------------------------------------------------------------
# Null repositories (no-op)
# ---------------------------------------------------------------------------


def test_null_episode_repo():
    repo = NullEpisodeRepository()
    ep = _ep("e1")
    assert repo.upsert(ep) is ep
    assert repo.get("e1") is None
    assert repo.list_recent() == []
    assert repo.count() == 0


# ---------------------------------------------------------------------------
# Factory — null path (no URL)
# ---------------------------------------------------------------------------


def test_get_repositories_null_when_no_url(monkeypatch):
    monkeypatch.delenv("EPISODE_DATABASE_URL", raising=False)
    repos = get_repositories(database_url=None)
    assert repos.episodes.list_recent() == []
    assert repos.podcasts.list_all() == []
    assert repos.ticker_insights.list_by_ticker("NVDA") == []
    assert repos.trending_tickers.list_trending() == []
