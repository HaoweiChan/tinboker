"""Authentication module for FastAPI API key authentication."""

import os

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

# API Key header name
API_KEY_HEADER_NAME = "X-API-Key"

# Create API key header dependency
api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)


def get_api_key_from_env() -> str:
    """
    Get API key from environment variable.
    
    Returns:
        API key string
        
    Raises:
        ValueError: If API key is not set in environment
    """
    api_key = os.getenv("PODCAST_API_KEY")
    if not api_key:
        raise ValueError(
            "PODCAST_API_KEY environment variable is not set. "
            "Please set it before starting the server."
        )
    return api_key


async def verify_api_key(api_key_header_value: str = Security(api_key_header)) -> str:
    """
    Verify the API key from the request header.
    
    Args:
        api_key_header_value: API key from X-API-Key header
        
    Returns:
        The API key if valid
        
    Raises:
        HTTPException: If API key is missing or invalid
    """
    if not api_key_header_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key is missing. Please provide X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    try:
        expected_api_key = get_api_key_from_env()
    except ValueError as e:
        # If API key is not configured, allow access (for development)
        # In production, you should always require API key
        print(f"Warning: {e}")
        return api_key_header_value
    
    if api_key_header_value != expected_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    return api_key_header_value
