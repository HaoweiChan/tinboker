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
        "ticker_recommendations_public_url": "https://example.test/recs.json",
    }

    episode = await transformer.to_episode(
        raw,
        content_fields={"summary_content", "events_markdown_content"},
    )

    assert episode.summary_content == "content:gs://bucket/summary.md"
    assert episode.events_markdown_content == "content:gs://bucket/events.md"
    assert episode.transcript == ""
    assert episode.ticker_recommendations_content is None
    assert gcs.calls == [
        ("gcs", "gs://bucket/summary.md"),
        ("gcs", "gs://bucket/events.md"),
    ]


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
