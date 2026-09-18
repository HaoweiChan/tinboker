"""A blank podcast_name must not mint an orphan ``e3b0c442_`` (sha256 of "") episode id."""

from __future__ import annotations

from datetime import datetime

import pytest
from src.models.podcast_models import PodcastEpisode
from src.service.upload_to_firebase import FirebaseService


def _episode() -> PodcastEpisode:
    return PodcastEpisode(
        mp3_url="",
        transcript_url="",
        summary_url="",
        summary_image_url="",
        related_tickers=[],
        created_time=datetime(2026, 1, 1),
        episode_title="EP623 | 🎆",
        podcast_name="",
    )


@pytest.mark.parametrize("name", ["", "   ", None])
def test_blank_podcast_name_raises(name):
    service = FirebaseService.__new__(FirebaseService)  # skip client init
    with pytest.raises(ValueError, match="podcast_name"):
        service._generate_episode_id(name, _episode())


def test_named_podcast_keeps_existing_id_shape():
    service = FirebaseService.__new__(FirebaseService)
    assert service._generate_episode_id("Gooaye 股癌", _episode()) == "Gooaye_a0da28594697bbb7"
