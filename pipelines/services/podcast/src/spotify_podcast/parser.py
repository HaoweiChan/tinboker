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
        Find an episode by matching its title, paging until ``limit`` is reached.

        Args:
            show_id: Spotify show ID
            episode_title: Episode title to search for (e.g., "EP617 | 👾")
            limit: Maximum number of episodes to search through (default: 100)

        Returns:
            Episode dictionary if found, None otherwise

        The previous implementation hand-unrolled exactly two pages, so it could never
        see past the newest 100 episodes — on a daily show that is about four months,
        which is why most of the back catalogue had no Spotify metadata at all. It also
        returned a partial match found on page 1 without ever looking at page 2, so a
        loose match could beat an exact one. Both are fixed here: page until ``limit``,
        then prefer an exact title across everything collected.
        """
        normalized_search = episode_title.strip().lower()
        if not normalized_search:
            return None

        episodes: list[Dict] = []
        offset = 0
        while len(episodes) < limit:
            result = self.get_episodes(show_id, limit=min(limit - len(episodes), 50), offset=offset)
            if not result or not result.get("items"):
                break
            batch = result["items"]
            # Spotify puts a literal null in `items` for episodes unavailable in the
            # token's market, and iterating those raised AttributeError inside
            # get_spotify_metadata — which swallowed it as a bare "Error fetching
            # Spotify metadata". Seen on 游庭皓的財經皓角, 353 episodes.
            episodes.extend(e for e in batch if e)
            if not result.get("next") or not batch:
                break
            # Advance by the RAW batch length: the nulls still occupy those offsets.
            offset += len(batch)

        if not episodes:
            return None

        # Exact title wins, and it has to win globally — not just within the first page.
        for episode in episodes:
            if (episode.get('name') or '').strip().lower() == normalized_search:
                return episode

        # Fall back to containment either way round. Guarded on length: a Spotify title
        # like "EP1" is a substring of half the back catalogue, and matching it would
        # attach the wrong episode's URL — worse than attaching none.
        MIN_PARTIAL = 8
        for episode in episodes:
            name = (episode.get('name') or '').strip().lower()
            if not name:
                continue
            if len(normalized_search) >= MIN_PARTIAL and normalized_search in name:
                return episode
            if len(name) >= MIN_PARTIAL and name in normalized_search:
                return episode

        return None

