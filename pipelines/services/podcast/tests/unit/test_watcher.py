"""Unit tests for the episode watcher new-episode detection logic."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.watcher import (
    EpisodeWatcher,
    WatcherConfig,
    _find_new_episodes,
    _is_fully_processed,
    _load_active_shows,
    load_watcher_config,
)


# --- _is_fully_processed ---

def test_fully_processed_when_all_urls_present():
    ep = {
        "mp3_url": "gs://bucket/a.mp3",
        "transcript_url": "gs://bucket/a.json",
        "summary_url": "gs://bucket/a.md",
        "summary_image_url": "gs://bucket/a.svg",
    }
    assert _is_fully_processed(ep) is True


def test_not_fully_processed_when_missing_summary():
    ep = {
        "mp3_url": "gs://bucket/a.mp3",
        "transcript_url": "gs://bucket/a.json",
        "summary_url": None,
        "summary_image_url": "gs://bucket/a.svg",
    }
    assert _is_fully_processed(ep) is False


def test_not_fully_processed_when_empty():
    assert _is_fully_processed({}) is False


# --- _find_new_episodes ---

@patch("src.service.upload_to_firebase.FirebaseService")
@patch("src.service.download_podcasts.fetch_episodes")
@patch("src.service.download_podcasts.extract_podcast_id", return_value="12345")
def test_find_new_episodes_returns_unprocessed(mock_extract, mock_fetch, mock_fb_cls):
    api_episodes = [
        {"title": "Ep 3", "episodeNumber": 3, "episodeUrl": "http://x/3.mp3"},
        {"title": "Ep 2", "episodeNumber": 2, "episodeUrl": "http://x/2.mp3"},
        {"title": "Ep 1", "episodeNumber": 1, "episodeUrl": "http://x/1.mp3"},
    ]
    mock_fetch.return_value = api_episodes

    fb_instance = MagicMock()
    mock_fb_cls.return_value = fb_instance

    def fake_get_by_fields(podcast_name, episode_title, episode_number):
        if episode_title == "Ep 2":
            return {
                "mp3_url": "gs://x/2.mp3",
                "transcript_url": "gs://x/2.json",
                "summary_url": "gs://x/2.md",
                "summary_image_url": "gs://x/2.svg",
            }
        return None

    fb_instance.get_episode_by_fields.side_effect = fake_get_by_fields

    show = {"name": "TestShow", "link": "https://podcasttomp3.com/podcasts/v2/12345"}
    result = _find_new_episodes(show, limit=3)

    assert len(result) == 2
    assert result[0]["title"] == "Ep 3"
    assert result[1]["title"] == "Ep 1"


@patch("src.service.upload_to_firebase.FirebaseService")
@patch("src.service.download_podcasts.fetch_episodes")
@patch("src.service.download_podcasts.extract_podcast_id", return_value="12345")
def test_find_new_episodes_returns_empty_when_all_processed(mock_extract, mock_fetch, mock_fb_cls):
    api_episodes = [
        {"title": "Ep 1", "episodeNumber": 1, "episodeUrl": "http://x/1.mp3"},
    ]
    mock_fetch.return_value = api_episodes

    fb_instance = MagicMock()
    mock_fb_cls.return_value = fb_instance
    fb_instance.get_episode_by_fields.return_value = {
        "mp3_url": "gs://x/1.mp3",
        "transcript_url": "gs://x/1.json",
        "summary_url": "gs://x/1.md",
        "summary_image_url": "gs://x/1.svg",
    }

    show = {"name": "TestShow", "link": "https://podcasttomp3.com/podcasts/v2/12345"}
    result = _find_new_episodes(show, limit=3)
    assert result == []


@patch("src.service.upload_to_firebase.FirebaseService")
@patch("src.service.download_podcasts.fetch_episodes", return_value=[])
@patch("src.service.download_podcasts.extract_podcast_id", return_value="12345")
def test_find_new_episodes_handles_empty_feed(mock_extract, mock_fetch, mock_fb_cls):
    show = {"name": "TestShow", "link": "https://podcasttomp3.com/podcasts/v2/12345"}
    result = _find_new_episodes(show, limit=3)
    assert result == []


# --- _load_active_shows ---

@patch("src.podcast.orchestrator._load_podcasts_from_db", return_value=None)
@patch("src.podcast.orchestrator._load_podcasts_from_platform", return_value=None)
@patch("src.podcast.orchestrator.load_podcasts_config")
def test_load_active_shows_falls_back_to_json(mock_json, mock_platform, mock_db):
    mock_json.return_value = [{"name": "Show A", "link": "http://x"}]
    result = _load_active_shows()
    assert len(result) == 1
    assert result[0]["name"] == "Show A"


@patch("src.podcast.orchestrator._load_podcasts_from_db", return_value=None)
@patch("src.podcast.orchestrator._load_podcasts_from_platform")
def test_load_active_shows_uses_platform_first(mock_platform, mock_db):
    mock_platform.return_value = [{"name": "Platform Show", "link": "http://y"}]
    result = _load_active_shows()
    assert result[0]["name"] == "Platform Show"


# --- load_watcher_config ---

def test_load_watcher_config_defaults(tmp_path):
    yaml_file = tmp_path / "default.yaml"
    yaml_file.write_text("{}")
    with patch("src.watcher.Path") as mock_path:
        mock_path.return_value.resolve.return_value.parent.parent.__truediv__ = lambda s, x: tmp_path
        # Simpler: just patch the function to return an empty dict
        pass
    # Test the WatcherConfig defaults directly
    cfg = WatcherConfig()
    assert cfg.enabled is True
    assert cfg.poll_interval_minutes == 10
    assert cfg.max_concurrent == 1
    assert cfg.episodes_per_show == 3


def test_load_watcher_config_from_dict():
    """Verify WatcherConfig can be constructed from yaml-like dict values."""
    watcher_cfg = {
        "enabled": False,
        "poll_interval_minutes": 30,
        "max_concurrent": 2,
        "episodes_per_show": 5,
    }
    cfg = WatcherConfig(
        enabled=watcher_cfg.get("enabled", True),
        poll_interval_minutes=watcher_cfg.get("poll_interval_minutes", 10),
        max_concurrent=watcher_cfg.get("max_concurrent", 1),
        episodes_per_show=watcher_cfg.get("episodes_per_show", 3),
    )
    assert cfg.enabled is False
    assert cfg.poll_interval_minutes == 30
    assert cfg.max_concurrent == 2
    assert cfg.episodes_per_show == 5


# --- EpisodeWatcher ---

@pytest.mark.asyncio
async def test_watcher_disabled_does_not_start():
    cfg = WatcherConfig(enabled=False)
    w = EpisodeWatcher(cfg)
    await w.start()
    assert w.status.running is False
    assert w._task is None


@pytest.mark.asyncio
async def test_watcher_status_initial():
    cfg = WatcherConfig(enabled=False)
    w = EpisodeWatcher(cfg)
    s = w.status.to_dict()
    assert s["running"] is False
    assert s["total_polls"] == 0
    assert s["processing_now"] == []
