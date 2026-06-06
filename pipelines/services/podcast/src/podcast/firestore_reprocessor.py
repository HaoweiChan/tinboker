"""Firestore episode reprocessing logic.

Handles fetching episodes from Firestore and re-running pipeline steps
(download, transcribe, summarize) on them.
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from src.pipeline import EpisodeProcessor, PipelineConfig, ServiceContainer
from src.pipeline.episode_data import EpisodeData
from src.pipeline.utils import determine_language


def process_firestore_episode(
    firestore_episode: Dict,
    episode_id: str,
    *,
    config_file: Path,
    rerun_from: Optional[str],
    transcript_service: str,
    use_file_mode: bool,
    reuse_existing_transcript: bool,
    base_config: PipelineConfig,
    service_container: ServiceContainer,
    podcast_config_mapping: Dict,
    podcasts: List[Dict],
) -> bool:
    """Process a single episode fetched from Firestore."""
    podcast_name = firestore_episode.get("podcast_name")
    if not podcast_name:
        print("✗ Error: Episode missing podcast_name field")
        return False

    transcript_option = podcast_config_mapping.get(podcast_name, {})
    episode_stt_service = transcript_option.get("transcript_service", transcript_service)
    episode_stt_model = transcript_option.get("model")

    podcast_json_config = None
    for podcast in podcasts:
        if podcast.get("name") == podcast_name:
            podcast_json_config = podcast
            break

    episode_spotify_show_link = None
    if podcast_json_config:
        episode_spotify_show_link = podcast_json_config.get("spotify_show_link")
    else:
        available_names = [p.get("name") for p in podcasts]
        print(f"  Warning: Podcast '{podcast_name}' not found in config")
        print(f"  Available podcasts in config: {available_names}")

    print(f"  Podcast: {podcast_name}")
    print(f"  STT Service: {episode_stt_service}" + (f" (Model: {episode_stt_model})" if episode_stt_model else " (default model)"))

    api_episode_data = {
        "title": firestore_episode.get("episode_title", ""),
        "episodeNumber": firestore_episode.get("episode_number"),
    }

    if rerun_from == "download":
        _fetch_episode_url_from_api(
            api_episode_data, firestore_episode, podcast_json_config, podcast_name
        )

    podcast_config = PipelineConfig(
        config_file=config_file,
        podcast_name=podcast_name,
        podcast_link="",
        spotify_show_link=episode_spotify_show_link,
        episode_limit=1,
        stt_service_name=episode_stt_service,
        stt_model=episode_stt_model,
        rerun_from=rerun_from,
        reuse_existing_transcript=reuse_existing_transcript,
        use_file_mode=use_file_mode,
        temp_dir=base_config.temp_dir,
    )

    processor = EpisodeProcessor(podcast_config, service_container)

    episode_data = EpisodeData(
        api_data=api_episode_data,
        podcast_name=podcast_name,
        language=determine_language(podcast_name),
    )
    episode_data.episode_id = episode_id

    _load_gcs_urls(episode_data, firestore_episode, rerun_from)
    _load_spotify_metadata(episode_data, firestore_episode)
    _load_created_time(episode_data, firestore_episode)
    _load_transcript_for_summarize(episode_data, firestore_episode, rerun_from, service_container)

    print(f"\nProcessing episode: {api_episode_data.get('title', 'Unknown')}")
    return processor.process_episode(api_episode_data)


def _fetch_episode_url_from_api(
    api_episode_data: Dict, firestore_episode: Dict, podcast_json_config: Optional[Dict], podcast_name: str
) -> None:
    if not (podcast_json_config and podcast_json_config.get("link")):
        print(f"  Warning: Podcast '{podcast_name}' not found in config or missing link")
        return
    try:
        from src.service.download_podcasts import extract_podcast_id, fetch_episodes
        podcast_id = extract_podcast_id(podcast_json_config["link"])
        api_episodes = fetch_episodes(podcast_id)
        episode_title = firestore_episode.get("episode_title", "")
        for api_ep in api_episodes:
            if api_ep.get("title") == episode_title:
                api_episode_data["episodeUrl"] = api_ep.get("episodeUrl")
                print("  Found episode in API, using original download URL")
                break
        if not api_episode_data.get("episodeUrl"):
            print(f"  Warning: Episode '{episode_title}' not found in API")
    except Exception as e:
        print(f"  Warning: Failed to fetch episode from API: {e}")


def _load_gcs_urls(episode_data: EpisodeData, firestore_episode: Dict, rerun_from: Optional[str]) -> None:
    if not (firestore_episode.get("mp3_url") or firestore_episode.get("transcript_url")):
        return
    url_keys = ["mp3_url", "transcript_url", "mp3_public_url", "transcript_public_url"]
    if rerun_from != "summarize":
        url_keys += [
            "summary_url", "summary_image_url", "summary_public_url", "summary_image_public_url",
            "events_markdown_url", "events_markdown_public_url",
            "sentences_markdown_url", "sentences_markdown_public_url",
            "pptx_url", "pptx_public_url",
            "marp_markdown_url", "marp_markdown_public_url",
            "ticker_recommendations_url", "ticker_recommendations_public_url",
            "ticker_marp_markdown_url", "ticker_marp_markdown_public_url",
        ]
    episode_data.gcs_urls = {k: firestore_episode.get(k) for k in url_keys}


def _load_spotify_metadata(episode_data: EpisodeData, firestore_episode: Dict) -> None:
    if not firestore_episode.get("spotify_id"):
        return
    episode_data.spotify_metadata = {
        "spotify_id": firestore_episode.get("spotify_id"),
        "spotify_url": firestore_episode.get("spotify_url"),
        "spotify_embed_url": firestore_episode.get("spotify_embed_url"),
        "release_date": firestore_episode.get("spotify_release_date"),
        "description": firestore_episode.get("spotify_description"),
        "duration_ms": firestore_episode.get("spotify_duration_ms"),
        "images": firestore_episode.get("spotify_images", []),
    }


def _load_created_time(episode_data: EpisodeData, firestore_episode: Dict) -> None:
    created_time = firestore_episode.get("created_time")
    if not created_time:
        return
    if isinstance(created_time, str):
        episode_data.created_time = datetime.fromisoformat(created_time)
    elif isinstance(created_time, datetime):
        episode_data.created_time = created_time


def _load_transcript_for_summarize(
    episode_data: EpisodeData,
    firestore_episode: Dict,
    rerun_from: Optional[str],
    service_container: ServiceContainer,
) -> None:
    if rerun_from != "summarize" or not service_container.gcs_service:
        return
    transcript_url = firestore_episode.get("transcript_url")
    if not transcript_url:
        return
    try:
        transcript_data = service_container.gcs_service.download_transcript_by_gcs_url(transcript_url)
        if transcript_data and transcript_data.get("text"):
            episode_data.transcript_text = transcript_data.get("text", "")
            episode_data.transcript_words = transcript_data.get("words")
            sentences_data = transcript_data.get("sentences", [])
            if sentences_data:
                from src.models.podcast_models import Sentence
                episode_data.transcript_sentences = [
                    Sentence(**s) if isinstance(s, dict) else s for s in sentences_data
                ]
            print(f"  Loaded transcript from GCS ({len(episode_data.transcript_text):,} characters)")
            if episode_data.transcript_sentences:
                print(f"  Sentence-level timing available ({len(episode_data.transcript_sentences)} sentences)")
    except Exception as e:
        print(f"  Warning: Could not download transcript from GCS: {e}")
