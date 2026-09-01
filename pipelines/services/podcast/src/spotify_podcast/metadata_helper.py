"""
Helper functions for fetching Spotify podcast metadata.
"""

import os
from datetime import datetime
from typing import Dict, Optional

from src.secrets_bootstrap import bootstrap

# Load secrets from GSM (idempotent — safe if already bootstrapped at entry point).
bootstrap()

from .auth import get_access_token  # noqa: E402
from .parser import SpotifyPodcastParser  # noqa: E402


def extract_metadata(episode: Optional[Dict]) -> Optional[Dict]:
    """Spotify episode object -> the metadata dict the pipeline stores.

    Shared with scripts/backfill_spotify_metadata.py, which pages a show's catalogue
    once and matches many titles against it, so it needs the extraction without the
    per-episode fetch that get_spotify_metadata performs.
    """
    if not episode:
        return None
    metadata = {
        'release_date': episode.get('release_date'),  # Format: YYYY-MM-DD
        'embed_url': episode.get('embed_url'),
        'spotify_id': episode.get('id'),
        # `or {}` / `or []`, not a .get default: Spotify returns an explicit null for
        # these on region-restricted or unavailable episodes, and a null default is not
        # substituted — .get('external_urls', {}) hands back None and the chained .get()
        # raises. Seen live on 游庭皓的財經皓角 during the backfill dry-run.
        'spotify_url': (episode.get('external_urls') or {}).get('spotify'),
        'description': episode.get('description'),
        'duration_ms': episode.get('duration_ms'),
        'images': [img.get('url') for img in (episode.get('images') or []) if img and img.get('url')],
    }
    release = metadata['release_date']
    if release:
        for fmt, length in (('%Y-%m-%d', 10), ('%Y-%m', 7), ('%Y', 4)):
            if len(release) == length:
                try:
                    metadata['release_datetime'] = datetime.strptime(release, fmt)
                except ValueError:
                    metadata['release_datetime'] = None
                break
    return metadata


def get_spotify_metadata(spotify_show_link: str, episode_title: str, limit: int = 100) -> Optional[Dict]:
    """
    Fetch Spotify metadata for an episode by matching its title.
    
    Args:
        spotify_show_link: Spotify show URL (e.g., "https://open.spotify.com/show/1zWxx5pKk0XBEzMupVC7UZ")
        episode_title: Episode title to match (e.g., "EP617 | 👾")
        limit: Maximum number of episodes to search through (default: 100)
    
    Returns:
        Dictionary with Spotify metadata if found, None otherwise.
        Contains:
        - release_date: Episode release date (YYYY-MM-DD format)
        - embed_url: Spotify embed URL
        - spotify_id: Episode ID
        - spotify_url: Episode URL
        - description: Episode description
        - duration_ms: Episode duration in milliseconds
        - images: List of image URLs
    """
    # Get credentials from environment
    client_id = os.getenv('SPOTIFY_ID') or os.getenv('SPOTIFY_CLIENT_ID')
    client_secret = (
        os.getenv('SPOTIFY_SECRET') or 
        os.getenv('SPOTIFY_SECRETE') or 
        os.getenv('SPOTIFY_CLIENT_SECRET')
    )
    
    if not client_id or not client_secret:
        print("  ⚠ Warning: Spotify credentials not found, skipping metadata fetch")
        return None
    
    try:
        # Get access token
        access_token = get_access_token(client_id, client_secret)
        if not access_token:
            print("  ⚠ Warning: Failed to get Spotify access token, skipping metadata fetch")
            return None
        
        # Initialize parser
        parser = SpotifyPodcastParser(access_token=access_token)
        
        # Extract show ID
        show_id = parser.extract_show_id(spotify_show_link)
        if not show_id:
            print(f"  ⚠ Warning: Invalid Spotify show link: {spotify_show_link}")
            return None
        
        # Find episode by title
        episode = parser.find_episode_by_title(show_id, episode_title, limit=limit)
        if not episode:
            print(f"  ⚠ Warning: Episode '{episode_title}' not found in Spotify")
            return None
        
        return extract_metadata(episode)
        
    except Exception as e:
        print(f"  ⚠ Warning: Error fetching Spotify metadata: {e}")
        return None
