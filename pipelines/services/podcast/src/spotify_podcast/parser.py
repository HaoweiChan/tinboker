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
    
    def get_all_episodes(self, show_id: str, limit: Optional[int] = None) -> List[Dict]:
        """
        Get a show's episodes, paginating until exhausted or ``limit`` is collected.

        Args:
            show_id: Spotify show ID
            limit: stop once this many episodes are collected (None = the whole show)

        Returns:
            List of episodes, nulls removed

        Spotify puts a literal null in ``items`` for episodes unavailable in the token's
        market. Callers iterate these and ``episode.get(...)`` raises, which
        get_spotify_metadata swallowed as a bare "Error fetching Spotify metadata" — the
        failure seen against 游庭皓的財經皓角. The offset still advances by the raw batch
        length, because those nulls occupy their positions.
        """
        all_episodes: List[Dict] = []
        offset = 0
        page = 50

        while True:
            want = page if limit is None else min(page, limit - len(all_episodes))
            if want <= 0:
                break
            result = self.get_episodes(show_id, limit=want, offset=offset)
            if not result or "items" not in result:
                break

            episodes = result["items"]
            if not episodes:
                break

            all_episodes.extend(e for e in episodes if e)

            if not result.get("next"):
                break

            offset += len(episodes)

        return all_episodes
    
    @staticmethod
    def match_title(episodes: list[Dict], episode_title: str) -> Optional[Dict]:
        """Pick the episode whose title matches, exact first across the whole list.

        Separated from fetching so a caller with many titles for one show can page the
        catalogue once and match against it in memory. Doing it per title cost one full
        pagination each, which rate-limited Spotify at around 100 episodes.
        """
        normalized_search = (episode_title or "").strip().lower()
        if not normalized_search:
            return None

        for episode in episodes:
            if (episode.get("name") or "").strip().lower() == normalized_search:
                return episode

        # Containment either way round, guarded on length: a Spotify title like "EP1" is
        # a substring of half a back catalogue, and attaching the wrong episode's URL is
        # worse than attaching none.
        MIN_PARTIAL = 8
        for episode in episodes:
            name = (episode.get("name") or "").strip().lower()
            if not name:
                continue
            if len(normalized_search) >= MIN_PARTIAL and normalized_search in name:
                return episode
            if len(name) >= MIN_PARTIAL and name in normalized_search:
                return episode
        return None

    def find_episode_by_title(self, show_id: str, episode_title: str, limit: int = 100) -> Optional[Dict]:
        """Find one episode by title. Pages the catalogue, so do not call it in a loop.

        For many titles from the same show use ``get_all_episodes`` once and
        ``match_title`` per title — see scripts/backfill_spotify_metadata.py.
        """
        if not (episode_title or "").strip():
            return None
        return self.match_title(self.get_all_episodes(show_id, limit=limit), episode_title)

