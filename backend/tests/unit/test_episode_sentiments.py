import json

from src.services.episode_sentiments import _parse


def test_parse_accepts_sentiment_and_sentiment_label_fields():
    content = json.dumps(
        {
            "ticker_recommendations": [
                {"ticker": "NVDA", "sentiment": "BULLISH"},
                {"ticker": "ORCL", "sentiment_label": "BEARISH"},
                {"ticker": "TSM", "sentiment": "UNKNOWN"},
                {"ticker": "", "sentiment": "BULLISH"},
            ]
        }
    )

    assert _parse(content) == {"NVDA": "BULLISH", "ORCL": "BEARISH"}


async def test_resolve_urls_reads_only_the_requested_docs(monkeypatch):
    """Resolving a few URLs must not rebuild the recent feed (that made the endpoint 12s cold)."""
    from src.services import episode_sentiments, postgres_mirror_service
    from src.services.podcast import PodcastService

    asked = []

    class _Store:
        def get_documents_batch(self, collection, ids):
            asked.append((collection, list(ids)))
            return [
                {"id": "E1", "ticker_insights_public_url": "https://m/e1.json"},
                {"id": "E2", "ticker_recommendations_public_url": "https://m/e2.json"},  # legacy field
                {"id": "E3"},
            ]

    async def _no_feed(*a, **k):
        raise AssertionError("get_recent_episodes must not be called")

    monkeypatch.setattr(postgres_mirror_service, "content_read_service", lambda: _Store())
    monkeypatch.setattr(PodcastService, "get_recent_episodes", _no_feed)
    svc = episode_sentiments.EpisodeSentimentService(gcs=object())
    out = await svc._resolve_urls(["E1", "E2", "E3"])
    assert out == {"E1": "https://m/e1.json", "E2": "https://m/e2.json"}
    assert asked == [("episodes", ["E1", "E2", "E3"])]
