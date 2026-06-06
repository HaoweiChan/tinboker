"""
Step 1: Download MP3 + Fetch Spotify Metadata

This module handles downloading episode MP3 files and fetching Spotify metadata.
"""

from pathlib import Path

from ..config import PipelineConfig
from ..episode_data import EpisodeData
from ..service_container import ServiceContainer


def download_episode(
    config: PipelineConfig,
    services: ServiceContainer,
    episode_data: EpisodeData
) -> None:
    """
    Download episode MP3 file and fetch Spotify metadata.
    
    Both operations are independent and can be done in parallel.
    Spotify metadata is fetched here because:
    1. We have episode_title from the start (no dependencies)
    2. created_time from Spotify is needed for Step 4 (episode ID generation)
    3. Both are "data gathering" operations
    
    Args:
        config: Pipeline configuration
        services: Service container
        episode_data: Episode data (mutated in place)
    """
    # Part 1: Download MP3
    # Skip download if rerun_from is "summarize", "upload", or "validate" (we don't need MP3)
    # Download if rerun_from is None (full pipeline), "download", or "transcribe" (need MP3)
    should_download = config.rerun_from in [None, "download", "transcribe"]
    
    if should_download:
        # Check if already downloaded (idempotency)
        if episode_data.mp3_path and episode_data.mp3_path.exists():
            pass  # Already have MP3
        else:
            episode_title = episode_data.api_data.get('title', 'Untitled Episode')
            
            # Try to get download URL from API data first (normal flow)
            episode_url = episode_data.api_data.get('episodeUrl')
            
            # If no episodeUrl, check if we have mp3_url in GCS URLs (when using --episode from Firestore)
            mp3_url = None
            if not episode_url and episode_data.gcs_urls:
                mp3_url = episode_data.gcs_urls.get('mp3_url')
            
            if mp3_url and services.gcs_service:
                # Download from GCS (when using --episode from Firestore or rerunning from transcribe)
                print(f"  ↓ Downloading MP3 from GCS: {episode_title}")
                try:
                    if config.use_file_mode:
                        # File mode: download to persistent directory
                        from src.service.download_podcasts import sanitize_filename
                        downloads_dir = config.downloads_dir / episode_data.podcast_name
                        downloads_dir.mkdir(parents=True, exist_ok=True)
                        safe_title = sanitize_filename(episode_title)
                        mp3_path = downloads_dir / f"{safe_title}.mp3"
                    else:
                        # Streaming mode: download to temp file
                        import tempfile
                        if config.temp_dir:
                            temp_dir = Path(config.temp_dir)
                        else:
                            temp_dir = Path(tempfile.gettempdir())
                        temp_dir.mkdir(parents=True, exist_ok=True)
                        mp3_path = temp_dir / f"{episode_title.replace('/', '_')}.mp3"
                    
                    # Download from GCS
                    services.gcs_service.download_file_by_gcs_url(mp3_url, mp3_path)
                    episode_data.mp3_path = mp3_path
                    print(f"  ✓ Downloaded MP3 from GCS: {episode_title}")
                except Exception as e:
                    raise ValueError(f"Failed to download MP3 from GCS: {e}")
            elif episode_url:
                # Download from original source (normal flow from API)
            
                # Download based on mode
                if config.use_file_mode:
                    # File mode: download to persistent directory
                    from src.service.download_podcasts import download_file
                    downloads_dir = config.downloads_dir / episode_data.podcast_name
                    downloads_dir.mkdir(parents=True, exist_ok=True)
                    
                    # Create filename
                    from src.service.download_podcasts import sanitize_filename
                    safe_title = sanitize_filename(episode_title)
                    mp3_path = downloads_dir / f"{safe_title}.mp3"
                    
                    # Download file
                    success = download_file(
                        episode_url,
                        mp3_path,
                        episode_title,
                        check_existing=True
                    )
                    if not success:
                        raise ValueError(f"Failed to download MP3: {episode_title}")
                else:
                    # Streaming mode: download to temp file
                    from src.service.download_podcasts import download_file_to_temp
                    mp3_path = download_file_to_temp(
                        episode_url,
                        episode_title,
                        config.temp_dir
                    )
                    if not mp3_path:
                        raise ValueError(f"Failed to download MP3 to temp: {episode_title}")
                
                episode_data.mp3_path = mp3_path
                print(f"  ↓ Downloaded: {episode_title}")
            else:
                # Neither episodeUrl nor mp3_url is available
                raise ValueError("No download URL in episode data. When using --episode, ensure the episode has mp3_url in Firestore. When using normal flow, ensure episodeUrl is available from the API.")
    else:
        # Skip download when rerun_from is "summarize", "upload", or "validate"
        if config.rerun_from in ["summarize", "upload", "validate"]:
            episode_title = episode_data.api_data.get('title', 'Untitled Episode')
            print(f"  ⏭ Skipping MP3 download (rerun_from={config.rerun_from})")
    
    # Part 2: Fetch Spotify metadata (independent of download)
    episode_title = episode_data.api_data.get('title', 'Untitled Episode')
    
    # Check if Spotify metadata already exists (loaded from Firestore)
    if episode_data.spotify_metadata:
        print("  🎵 Spotify metadata: Already available (from Firestore)")
        spotify_id = episode_data.spotify_metadata.get('spotify_id')
        spotify_url = episode_data.spotify_metadata.get('spotify_url')
        release_date = episode_data.spotify_metadata.get('release_date')
        if spotify_id:
            print(f"    ✓ Spotify ID: {spotify_id}")
        if spotify_url:
            print(f"    ✓ Spotify URL: {spotify_url}")
        if release_date:
            print(f"    ✓ Release Date: {release_date}")
    elif config.spotify_show_link:
        # Try to fetch Spotify metadata
        try:
            from src.spotify_podcast.metadata_helper import get_spotify_metadata
            print(f"  🎵 Fetching Spotify metadata: {episode_title}")
            print(f"    Show Link: {config.spotify_show_link}")
            
            metadata = get_spotify_metadata(
                config.spotify_show_link,
                episode_title
            )
            episode_data.spotify_metadata = metadata
            
            # Use Spotify release_date as created_time if available
            # (needed for Step 4: episode ID generation)
            if metadata:
                spotify_id = metadata.get('spotify_id')
                spotify_url = metadata.get('spotify_url')
                release_date = metadata.get('release_date')
                duration_ms = metadata.get('duration_ms')
                
                print("  ✓ Spotify metadata fetched successfully")
                if spotify_id:
                    print(f"    ✓ Spotify ID: {spotify_id}")
                if spotify_url:
                    print(f"    ✓ Spotify URL: {spotify_url}")
                if release_date:
                    print(f"    ✓ Release Date: {release_date}")
                if duration_ms:
                    duration_min = duration_ms // 60000
                    print(f"    ✓ Duration: {duration_min} minutes")
                
                if metadata.get('release_datetime'):
                    episode_data.created_time = metadata['release_datetime']
            else:
                print(f"  ⚠ Warning: Spotify metadata not found for episode '{episode_title}'")
        except Exception as e:
            print(f"  ⚠ Warning: Error fetching Spotify metadata: {e}")
            # Continue without metadata - it's optional
    else:
        # No Spotify link configured
        print("  🎵 Spotify: Not configured (no spotify_show_link in config)")



