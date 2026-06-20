import pytest

from src.services.episode_transformer import EpisodeTransformer


class FakeGCSContentService:
    def __init__(self):
        self.calls = []

    async def fetch_gcs_content(self, url: str) -> str:
        self.calls.append(("gcs", url))
        return f"content:{url}"

    async def fetch_url_content(self, url: str) -> str:
        self.calls.append(("url", url))
        return f"content:{url}"


@pytest.mark.asyncio
async def test_to_episode_hydrates_only_requested_content_fields():
    gcs = FakeGCSContentService()
    transformer = EpisodeTransformer(gcs_service=gcs)
    raw = {
        "id": "ep1",
        "podcast_name": "財經一路發",
        "created_time": 1,
        "summary_url": "gs://bucket/summary.md",
        "transcript_url": "gs://bucket/transcript.json",
        "events_markdown_url": "gs://bucket/events.md",
        "ticker_insights_public_url": "https://example.test/insights.json",
    }

    episode = await transformer.to_episode(
        raw,
        content_fields={"summary_content", "events_markdown_content"},
    )

    assert episode.summary_content == "content:gs://bucket/summary.md"
    assert episode.events_markdown_content == "content:gs://bucket/events.md"
    assert episode.transcript == ""
    assert episode.ticker_insights_content is None
    assert gcs.calls == [
        ("gcs", "gs://bucket/summary.md"),
        ("gcs", "gs://bucket/events.md"),
    ]


@pytest.mark.asyncio
async def test_to_episode_maps_legacy_ticker_insight_fields():
    transformer = EpisodeTransformer(gcs_service=FakeGCSContentService())
    raw = {
        "id": "ep1",
        "podcast_name": "財經一路發",
        "created_time": 1,
        "ticker_recommendations_public_url": "https://example.test/legacy.json",
        "ticker_recommendations_content": '{"ticker_insights":[]}',
    }

    episode = await transformer.to_episode(raw, enrich_content=False)

    assert episode.ticker_insights_public_url == "https://example.test/legacy.json"
    assert episode.ticker_insights_content == '{"ticker_insights":[]}'


@pytest.mark.asyncio
async def test_to_episode_preserves_sector_exposure_fields_and_defaults_old_docs():
    transformer = EpisodeTransformer(gcs_service=FakeGCSContentService())
    old = await transformer.to_episode(
        {"id": "old", "podcast_name": "股癌", "created_time": 1},
        enrich_content=False,
    )

    assert old.sector_exposures == []
    assert old.unresolved_market_trends == []
    assert old.sector_exposure_ids == []

    raw = {
        "id": "ep1",
        "podcast_name": "股癌",
        "created_time": 1,
        "sector_exposures": [{"exposure_id": "theme_ai_server"}],
        "unresolved_market_trends": [{"normalized_text": "cpo"}],
        "sector_exposure_ids": ["theme_ai_server"],
        "sector_ids": [],
        "theme_ids": ["ai_server"],
        "unresolved_market_trend_ids": ["cpo"],
    }
    episode = await transformer.to_episode(raw, enrich_content=False)

    assert episode.sector_exposures == [{"exposure_id": "theme_ai_server"}]
    assert episode.unresolved_market_trends == [{"normalized_text": "cpo"}]
    assert episode.sector_exposure_ids == ["theme_ai_server"]
    assert episode.theme_ids == ["ai_server"]
    assert episode.unresolved_market_trend_ids == ["cpo"]


def test_is_content_incomplete_respects_requested_content_fields():
    raw = {
        "summary_url": "gs://bucket/summary.md",
        "summary_content": "ok",
        "transcript_url": "gs://bucket/transcript.json",
        "transcript": "",
    }

    assert not EpisodeTransformer.is_content_incomplete(
        raw,
        content_fields={"summary_content"},
    )
    assert EpisodeTransformer.is_content_incomplete(raw)
