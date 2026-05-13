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
        
        # Extract relevant metadata
        metadata = {
            'release_date': episode.get('release_date'),  # Format: YYYY-MM-DD
            'embed_url': episode.get('embed_url'),
            'spotify_id': episode.get('id'),
            'spotify_url': episode.get('external_urls', {}).get('spotify'),
            'description': episode.get('description'),
            'duration_ms': episode.get('duration_ms'),
            'images': [img.get('url') for img in episode.get('images', []) if img.get('url')],
        }
        
        # Parse release_date to datetime if available
        if metadata['release_date']:
            try:
                # Spotify returns dates in YYYY-MM-DD format
                release_date_str = metadata['release_date']
                if len(release_date_str) == 10:  # YYYY-MM-DD
                    metadata['release_datetime'] = datetime.strptime(release_date_str, '%Y-%m-%d')
                elif len(release_date_str) == 7:  # YYYY-MM
                    metadata['release_datetime'] = datetime.strptime(release_date_str, '%Y-%m')
                elif len(release_date_str) == 4:  # YYYY
                    metadata['release_datetime'] = datetime.strptime(release_date_str, '%Y')
            except ValueError:
                # If parsing fails, just keep the string
                metadata['release_datetime'] = None
        
        return metadata
        
    except Exception as e:
        print(f"  ⚠ Warning: Error fetching Spotify metadata: {e}")
        return None
