"""
Authentication utilities for Spotify API.
"""

from typing import Optional

import requests


def get_access_token(client_id: str, client_secret: str) -> Optional[str]:
    """
    Get Spotify API access token using Client Credentials flow.
    
    Args:
        client_id: Spotify app client ID
        client_secret: Spotify app client secret
    
    Returns:
        Access token or None if authentication fails
    """
    url = "https://accounts.spotify.com/api/token"
    data = {
        "grant_type": "client_credentials"
    }
    auth = (client_id, client_secret)
    
    try:
        response = requests.post(url, data=data, auth=auth)
        response.raise_for_status()
        return response.json()["access_token"]
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Failed to get access token: {e}") from e

