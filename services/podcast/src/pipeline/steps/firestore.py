"""
Step 5: Upload to Firestore

This module handles uploading episode data to Firestore.
"""

from ..config import PipelineConfig
from ..episode_data import EpisodeData
from ..service_container import ServiceContainer
from ..utils import create_episode_object


def upload_to_firestore(
    config: PipelineConfig,
    services: ServiceContainer,
    episode_data: EpisodeData
) -> None:
    """
    Upload episode data to Firestore.
    
    Args:
        config: Pipeline configuration
        services: Service container
        episode_data: Episode data (mutated in place)
    """
    # Determine if we should upload to Firestore
    # Skip if rerun_from is "validate"
    should_upload = config.rerun_from in [None, "download", "transcribe", "summarize", "upload"]
    
    if not should_upload:
        return
    
    # Need Firebase service
    if not services.firebase_service:
        print("  ⚠ Warning: Firebase service not available, skipping Firestore upload")
        return
    
    # Need GCS URLs
    if not episode_data.gcs_urls:
        print("  ⚠ Warning: GCS URLs not available, skipping Firestore upload")
        return
    
    episode_title = episode_data.api_data.get('title', 'Untitled Episode')
    print(f"  📝 Uploading to Firestore: {episode_title}")
    
    # Create PodcastEpisode object
    episode = create_episode_object(
        episode_data=episode_data,
        gcs_urls=episode_data.gcs_urls,
        spotify_metadata=episode_data.spotify_metadata,
        summary_result=episode_data.summary_result
    )
    
    # Upload to Firestore
    services.firebase_service.upload_podcast_data(
        podcast_name=episode_data.podcast_name,
        episode=episode,
        gcs_service=None,  # Already uploaded above
        tags=episode_data.tags if episode_data.tags else None,
        tickers=episode_data.tickers if episode_data.tickers else None
    )
    
    episode_data.episode = episode
    print("  ✓ Uploaded to Firestore")

