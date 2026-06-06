"""
Unit tests for EpisodeProcessor logic.
"""

import pytest
from src.pipeline import EpisodeProcessor
from src.pipeline.episode_data import EpisodeData


def _make_episode_data(**kwargs) -> EpisodeData:
    defaults = dict(
        api_data={"title": "Test Episode", "episodeNumber": 1},
        podcast_name="Test Podcast",
        language="en",
    )
    defaults.update(kwargs)
    return EpisodeData(**defaults)


@pytest.mark.unit
class TestShouldSkipEpisode:
    def test_normal_mode_not_processed(self, base_config, base_context):
        processor = EpisodeProcessor(base_config, base_context)
        episode_data = _make_episode_data()
        assert processor._should_skip_episode(episode_data) is False

    def test_normal_mode_fully_processed(self, base_config, base_context):
        processor = EpisodeProcessor(base_config, base_context)
        episode_data = _make_episode_data(
            episode_id="test_id",
            gcs_urls={
                "mp3_url": "gs://test/test.mp3",
                "transcript_url": "gs://test/test.json",
                "summary_url": "gs://test/test.md",
                "summary_image_url": "gs://test/test.svg",
            },
        )
        assert processor._should_skip_episode(episode_data) is True

    def test_rerun_from_download(self, base_config, base_context):
        base_config.rerun_from = "download"
        processor = EpisodeProcessor(base_config, base_context)
        episode_data = _make_episode_data(
            episode_id="test_id",
            gcs_urls={
                "mp3_url": "gs://test/test.mp3",
                "transcript_url": "gs://test/test.json",
                "summary_url": "gs://test/test.md",
                "summary_image_url": "gs://test/test.svg",
            },
        )
        assert processor._should_skip_episode(episode_data) is False

    def test_rerun_from_transcribe(self, base_config, base_context):
        base_config.rerun_from = "transcribe"
        processor = EpisodeProcessor(base_config, base_context)
        episode_data = _make_episode_data(episode_id="test_id")
        assert processor._should_skip_episode(episode_data) is False

    def test_rerun_from_summarize_with_transcript(self, base_config, base_context):
        base_config.rerun_from = "summarize"
        processor = EpisodeProcessor(base_config, base_context)
        episode_data = _make_episode_data(episode_id="test_id", transcript_text="Test transcript")
        assert processor._should_skip_episode(episode_data) is False

    def test_rerun_from_summarize_no_transcript(self, base_config, base_context):
        base_config.rerun_from = "summarize"
        processor = EpisodeProcessor(base_config, base_context)
        episode_data = _make_episode_data(episode_id="test_id", transcript_text=None)
        assert processor._should_skip_episode(episode_data) is True

    def test_rerun_from_upload_with_urls(self, base_config, base_context):
        base_config.rerun_from = "upload"
        processor = EpisodeProcessor(base_config, base_context)
        episode_data = _make_episode_data(
            episode_id="test_id",
            gcs_urls={"mp3_url": "gs://test/test.mp3"},
        )
        assert processor._should_skip_episode(episode_data) is False

    def test_rerun_from_upload_no_urls(self, base_config, base_context):
        base_config.rerun_from = "upload"
        processor = EpisodeProcessor(base_config, base_context)
        episode_data = _make_episode_data(episode_id="test_id", gcs_urls=None)
        assert processor._should_skip_episode(episode_data) is True

    def test_rerun_from_validate_with_episode(self, base_config, base_context):
        base_config.rerun_from = "validate"
        processor = EpisodeProcessor(base_config, base_context)
        episode_data = _make_episode_data(episode_id="test_id")
        assert processor._should_skip_episode(episode_data) is False

    def test_rerun_from_validate_no_episode(self, base_config, base_context):
        base_config.rerun_from = "validate"
        processor = EpisodeProcessor(base_config, base_context)
        episode_data = _make_episode_data(episode_id=None)
        assert processor._should_skip_episode(episode_data) is True


@pytest.mark.unit
class TestLoadExistingData:
    def test_loads_gcs_urls_from_firestore(self, base_config, base_context, sample_firestore_episode):
        processor = EpisodeProcessor(base_config, base_context)
        base_context.firebase_service.get_episode_by_fields.return_value = sample_firestore_episode

        episode_data = _make_episode_data(
            api_data={
                "title": sample_firestore_episode["episode_title"],
                "episodeNumber": sample_firestore_episode["episode_number"],
            }
        )
        processor._load_existing_data(episode_data)

        assert episode_data.episode_id == sample_firestore_episode["id"]
        assert episode_data.gcs_urls is not None
        assert episode_data.gcs_urls["mp3_url"] == sample_firestore_episode["mp3_url"]
        assert episode_data.gcs_urls["transcript_url"] == sample_firestore_episode["transcript_url"]

    def test_clears_when_no_episode_found(self, base_config, base_context):
        processor = EpisodeProcessor(base_config, base_context)
        base_context.firebase_service.get_episode_by_fields.return_value = None

        episode_data = _make_episode_data()
        processor._load_existing_data(episode_data)

        assert episode_data.episode_id is None
        assert episode_data.gcs_urls is None
