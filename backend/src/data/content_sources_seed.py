"""
Seed data for the content_sources table.

Mirrors the current tinboker-agents config at the time of writing:
  - services/podcast/podcasts_tw.json  (6 TW shows)
  - services/podcast/podcasts_en.json  (14 EN shows)
  - services/news/feeds.json           (6 RSS feeds)

This is an insert-only seed (see ContentSourceService.seed_from_config): it populates
empty tables and never overwrites operator edits. Once Phase 2 flips the agents pipeline
to pull GET /api/sources, this module is just the initial bootstrap — the table becomes
the source of truth.
"""

# Podcast shows. language encodes content language (zh-TW | en).
PODCAST_SOURCES: list[dict] = [
    # --- Taiwan (zh-TW) ---
    {
        "source_type": "podcast", "language": "zh-TW", "region": "TW",
        "name": "Gooaye 股癌",
        "feed_url": "https://podcasttomp3.com/podcasts/v2/358931",
        "spotify_url": "https://open.spotify.com/show/1zWxx5pKk0XBEzMupVC7UZ",
        "lookback_days": 30,
        "transcript_service": "groq", "transcript_model": "whisper-large-v3",
        "active": True,
    },
    {
        "source_type": "podcast", "language": "zh-TW", "region": "TW",
        "name": "游庭皓的財經皓角",
        "feed_url": "https://podcasttomp3.com/podcasts/v2/1196687",
        "spotify_url": "https://open.spotify.com/show/1HOGxT9M7a6kpcDi4q27Q7",
        "lookback_days": 30,
        "transcript_service": "groq", "transcript_model": "whisper-large-v3",
        "active": True,
    },
    {
        "source_type": "podcast", "language": "zh-TW", "region": "TW",
        "name": "財報狗",
        "feed_url": "https://podcasttomp3.com/podcasts/v2/1244950",
        "spotify_url": "https://open.spotify.com/show/02nixW8CEcAuGOp31YdpLt",
        "lookback_days": 30,
        "transcript_service": "groq", "transcript_model": "whisper-large-v3",
        "active": True,
    },
    {
        "source_type": "podcast", "language": "zh-TW", "region": "TW",
        "name": "財經M平方",
        "feed_url": "https://podcasttomp3.com/podcasts/v2/153128",
        "spotify_url": "https://open.spotify.com/show/6JZtemUFcwHTrTprarLVwL",
        "lookback_days": 30,
        "transcript_service": "groq", "transcript_model": "whisper-large-v3",
        "active": True,
    },
    {
        "source_type": "podcast", "language": "zh-TW", "region": "TW",
        "name": "財女珍妮",
        "feed_url": "https://podcasttomp3.com/podcasts/v2/3474880",
        "spotify_url": "https://open.spotify.com/show/3dTKJkvceKNHaYoh7Przbg",
        "lookback_days": 30,
        "transcript_service": "groq", "transcript_model": "whisper-large-v3",
        "active": True,
    },
    {
        "source_type": "podcast", "language": "zh-TW", "region": "TW",
        "name": "財經一路發",
        "feed_url": "https://podcasttomp3.com/podcasts/v2/5714050",
        "spotify_url": "https://open.spotify.com/show/16vk9uoUXgbtWqIMbwyHsa",
        "lookback_days": 30,
        "transcript_service": "groq", "transcript_model": "whisper-large-v3",
        "active": True,
    },
    # --- English (en) ---
    {
        "source_type": "podcast", "language": "en",
        "name": "Bloomberg Masters in Business Podcast",
        "feed_url": "https://podcasttomp3.com/podcasts/v2/4112705",
        "spotify_url": "https://open.spotify.com/show/5LGxKlY6fzXS3tGsjB23Cb",
        "lookback_days": 30, "active": True,
    },
    {
        "source_type": "podcast", "language": "en",
        "name": "Exchanges at Goldman Sachs",
        "feed_url": "https://podcasttomp3.com/podcasts/v2/753888",
        "spotify_url": "https://open.spotify.com/episode/2qNxiLun8EvNNnowUp3iaN",
        "lookback_days": 30, "active": True,
    },
    {
        "source_type": "podcast", "language": "en",
        "name": "CNBC's Fast Money",
        "feed_url": "https://podcasttomp3.com/podcasts/v2/385199",
        "spotify_url": "https://open.spotify.com/show/6bdGOAWb664x8wXfoiwFTV",
        "lookback_days": 30, "active": True,
    },
    {
        "source_type": "podcast", "language": "en",
        "name": "The Disciplined Investor",
        "feed_url": "https://podcasttomp3.com/podcasts/v2/745155",
        "spotify_url": "https://open.spotify.com/show/5vtvEVDPUi4221imwhXyXt",
        "lookback_days": 30, "active": True,
    },
    {
        "source_type": "podcast", "language": "en",
        "name": "Invest Like the Best",
        "feed_url": "https://podcasttomp3.com/podcasts/v2/982387",
        "spotify_url": "https://open.spotify.com/show/22fi0RqfoBACCuQDv97wFO",
        "lookback_days": 30, "active": True,
    },
    {
        "source_type": "podcast", "language": "en",
        "name": "Inside the Strategy Room",
        "feed_url": "https://podcasttomp3.com/podcasts/v2/768284",
        "spotify_url": "https://open.spotify.com/show/4TcFfiQ0e6OYuc5kRDLxqj",
        "lookback_days": 30, "active": True,
    },
    {
        "source_type": "podcast", "language": "en",
        "name": "The Tech M&A Podcast",
        "feed_url": "https://podcasttomp3.com/podcasts/v2/688826",
        "spotify_url": "https://open.spotify.com/show/4t1zDAifgsv0kvdBagRjBj",
        "lookback_days": 30, "active": True,
    },
    {
        "source_type": "podcast", "language": "en",
        "name": "The Long View",
        "feed_url": "https://podcasttomp3.com/podcasts/v2/558036",
        "spotify_url": "https://open.spotify.com/show/21UMpSDjAl7HzyQ0M0wvLw",
        "lookback_days": 30, "active": True,
    },
    {
        "source_type": "podcast", "language": "en",
        "name": "The Meb Faber Show",
        "feed_url": "https://podcasttomp3.com/podcasts/v2/743157",
        "spotify_url": "https://open.spotify.com/show/4RajWGfe80Wfy9J6rswE4L",
        "lookback_days": 30, "active": True,
    },
    {
        "source_type": "podcast", "language": "en",
        "name": "Motley Fool Money",
        "feed_url": "https://podcasttomp3.com/podcasts/v2/51305",
        "spotify_url": "https://open.spotify.com/show/7tXRc97C1fA0epHAGQuJOE",
        "lookback_days": 30, "active": True,
    },
    {
        "source_type": "podcast", "language": "en",
        "name": "Private Equity Funcast",
        "feed_url": "https://podcasttomp3.com/podcasts/v2/215225",
        "spotify_url": "https://open.spotify.com/show/0klTgf4aQagSa7pWacqjJ5",
        "lookback_days": 30, "active": True,
    },
    {
        "source_type": "podcast", "language": "en",
        "name": "The Intrinsic Value Podcast",
        "feed_url": "https://podcasttomp3.com/podcasts/v2/786362",
        "spotify_url": "https://open.spotify.com/show/7dnn22EWyo6MLsPaR492BM",
        "lookback_days": 30, "active": True,
    },
    {
        "source_type": "podcast", "language": "en",
        "name": "Capital Allocators",
        "feed_url": "https://podcasttomp3.com/podcasts/v2/222998",
        "spotify_url": "https://open.spotify.com/show/3q6PrjHVfRzpD2lN1g2XRU",
        "lookback_days": 30, "active": True,
    },
    {
        "source_type": "podcast", "language": "en",
        "name": "Dealcast",
        "feed_url": "https://podcasttomp3.com/podcasts/v2/4585725",
        "spotify_url": "https://open.spotify.com/show/2zBShB8SrybR8GPHlH0lBD",
        "lookback_days": 30, "active": True,
    },
]

# News RSS feeds. region encodes the feed region (US | TW).
NEWS_SOURCES: list[dict] = [
    {"source_type": "news", "region": "US", "name": "Yahoo Finance",
     "feed_url": "https://finance.yahoo.com/news/rssindex", "lookback_days": 30, "active": True},
    {"source_type": "news", "region": "US", "name": "CNBC Top News",
     "feed_url": "https://www.cnbc.com/id/100003114/device/rss/rss.html", "lookback_days": 30, "active": True},
    {"source_type": "news", "region": "US", "name": "NASDAQ Markets",
     "feed_url": "https://www.nasdaq.com/feed/rssoutbound?category=Markets", "lookback_days": 30, "active": True},
    {"source_type": "news", "region": "US", "name": "MarketWatch Top Stories",
     "feed_url": "http://feeds.marketwatch.com/marketwatch/topstories/", "lookback_days": 30, "active": True},
    {"source_type": "news", "region": "TW", "name": "cnYES 鉅亨網 頭條",
     "feed_url": "https://news.cnyes.com/rss/v1/news/category/headline", "lookback_days": 30, "active": True},
    {"source_type": "news", "region": "TW", "name": "經濟日報 證券",
     "feed_url": "https://money.udn.com/rssfeed/news/1001/5590?ch=money", "lookback_days": 30, "active": True},
]

ALL_SOURCES: list[dict] = PODCAST_SOURCES + NEWS_SOURCES
