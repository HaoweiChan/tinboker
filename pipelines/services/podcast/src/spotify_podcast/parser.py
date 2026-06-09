"""
Core parser for Spotify podcast shows and episodes.
"""

from typing import Dict, List, Optional

import requests


class SpotifyPodcastParser:
    """Parser for Spotify podcast shows and episodes."""
    
    BASE_URL = "https://api.spotify.com/v1"
    
    def __init__(self, access_token: Optional[str] = None):
        """
        Initialize the parser.
        
        Args:
            access_token: Spotify API access token. If None, will need to be set later.
        """
        self.access_token = access_token
        self.headers = {}
        if access_token:
            self.headers = {"Authorization": f"Bearer {access_token}"}
    
    def extract_show_id(self, show_input: str) -> Optional[str]:
        """
        Extract show ID from Spotify URL or return show ID if already provided.
        
        Args:
            show_input: Spotify show URL (e.g., https://open.spotify.com/show/1zWxx5pKk0XBEzMupVC7UZ)
                       or show ID directly
        
        Returns:
            Show ID or None if invalid
        """
        # If it's already a show ID (22 characters, alphanumeric)
        if len(show_input) == 22 and show_input.replace('-', '').replace('_', '').isalnum():
            return show_input
        
        # Try to extract from URL
        try:
            if "/show/" in show_input:
                show_id = show_input.split("/show/")[1].split("?")[0].split("/")[0]
                if len(show_id) == 22:
                    return show_id
        except Exception:
            pass
        
        return None
    
    def get_show_info(self, show_id: str) -> Optional[Dict]:
        """
        Get show information from Spotify API.
        
        Args:
            show_id: Spotify show ID
        
        Returns:
            Show information dictionary or None
        """
        if not self.access_token:
            raise ValueError("Access token required. Please authenticate first.")
        
        url = f"{self.BASE_URL}/shows/{show_id}"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise ValueError(f"Error fetching show info: {e}") from e
    
    def get_episodes(self, show_id: str, limit: int = 50, offset: int = 0) -> Optional[Dict]:
        """
        Get episodes for a show.
        
        Args:
            show_id: Spotify show ID
            limit: Maximum number of episodes to return (default: 50, max: 50)
            offset: Offset for pagination
        
        Returns:
            Episodes dictionary with 'items' list and pagination info, or None
        """
        if not self.access_token:
            raise ValueError("Access token required. Please authenticate first.")
        
        url = f"{self.BASE_URL}/shows/{show_id}/episodes"
        params = {"limit": min(limit, 50), "offset": offset}
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Add embed URLs to episodes
            if "items" in data:
                for episode in data["items"]:
                    episode_id = episode.get('id')
                    if episode_id:
                        episode['embed_url'] = f"https://open.spotify.com/embed/episode/{episode_id}"
            
            return data
        except requests.exceptions.RequestException as e:
            raise ValueError(f"Error fetching episodes: {e}") from e
    
    def get_all_episodes(self, show_id: str) -> List[Dict]:
        """
        Get all episodes for a show (handles pagination).
        
        Args:
            show_id: Spotify show ID
        
        Returns:
            List of all episodes with embed URLs added
        """
        all_episodes = []
        offset = 0
        limit = 50
        
        while True:
            result = self.get_episodes(show_id, limit=limit, offset=offset)
            if not result or "items" not in result:
                break
            
            episodes = result["items"]
            if not episodes:
                break
            
            all_episodes.extend(episodes)
            
            # Check if there are more pages
            if not result.get("next"):
                break
            
            offset += limit
        
        return all_episodes
    
    def find_episode_by_title(self, show_id: str, episode_title: str, limit: int = 100) -> Optional[Dict]:
        """
        Find an episode by matching its title.
        
        Args:
            show_id: Spotify show ID
            episode_title: Episode title to search for (e.g., "EP617 | 👾")
            limit: Maximum number of episodes to search through (default: 100)
        
        Returns:
            Episode dictionary if found, None otherwise
        """
        # Normalize the search title (remove extra spaces, lowercase for comparison)
        normalized_search = episode_title.strip().lower()
        
        # Fetch episodes (up to limit)
        result = self.get_episodes(show_id, limit=min(limit, 50), offset=0)
        if not result or "items" not in result:
            return None
        
        episodes = result["items"]
        
        # Try exact match first
        for episode in episodes:
            episode_name = episode.get('name', '').strip()
            if episode_name.lower() == normalized_search:
                return episode
        
        # Try partial match (in case of slight differences)
        for episode in episodes:
            episode_name = episode.get('name', '').strip()
            # Check if the normalized search title is contained in episode name or vice versa
            if normalized_search in episode_name.lower() or episode_name.lower() in normalized_search:
                return episode
        
        # If not found in first batch and there are more episodes, search more
        if result.get("next") and limit > 50:
            # Get more episodes
            result2 = self.get_episodes(show_id, limit=min(limit - 50, 50), offset=50)
            if result2 and "items" in result2:
                for episode in result2["items"]:
                    episode_name = episode.get('name', '').strip()
                    if episode_name.lower() == normalized_search:
                        return episode
                    if normalized_search in episode_name.lower() or episode_name.lower() in normalized_search:
                        return episode
        
        return None

