"""
Spotify Podcast Parser

A Python library for fetching episode metadata from Spotify podcasts using the Spotify Web API.
"""

__version__ = "1.0.0"

from .auth import get_access_token
from .metadata_helper import get_spotify_metadata
from .parser import SpotifyPodcastParser

__all__ = ["SpotifyPodcastParser", "get_access_token", "get_spotify_metadata"]

