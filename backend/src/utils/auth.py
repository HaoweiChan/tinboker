"""
Authentication utilities for Google OAuth and JWT tokens
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from src.config import settings

# Try to import Google Auth library for OAuth token verification
try:
    from google.oauth2 import id_token
    from google.auth.transport import requests
    GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    GOOGLE_AUTH_AVAILABLE = False
    id_token = None
    requests = None


def verify_google_token(id_token_str: str) -> Dict[str, Any]:
    """
    Verify Google OAuth ID token (not Firebase token)
    
    This verifies tokens from @react-oauth/google which uses Google OAuth Client ID,
    not Firebase tokens. The token audience will be the OAuth Client ID.
    
    Args:
        id_token_str: Google OAuth ID token from frontend
        
    Returns:
        Decoded token payload containing user information
        
    Raises:
        ValueError: If token is invalid or verification fails
    """
    if not GOOGLE_AUTH_AVAILABLE:
        raise ValueError(
            "google-auth library is required for Google OAuth. "
            "Install it with: pip install google-auth"
        )
    
    # Get Google Client ID from settings
    # Check multiple possible environment variable names for flexibility
    client_id = (
        os.getenv("GOOGLE_CLIENT_ID") or 
        os.getenv("OAUTH_CLIENT_ID") or 
        settings.google_client_id
    )
    
    if not client_id:
        raise ValueError(
            "Google OAuth Client ID not configured. "
            "Set GOOGLE_CLIENT_ID or OAUTH_CLIENT_ID in .env file or environment variables."
        )
    
    try:
        # Verify the Google OAuth ID token
        # The request object is needed for token verification
        request_obj = requests.Request()
        
        # First, try to verify the token normally
        # If it fails due to clock skew, we'll handle it manually
        try:
            decoded_token = id_token.verify_oauth2_token(
                id_token_str,
                request_obj,
                client_id
            )
        except ValueError as e:
            error_msg = str(e)
            # Check if it's a clock skew error (token used too early)
            if "too early" in error_msg.lower() or ("clock" in error_msg.lower() and "set correctly" in error_msg.lower()):
                # Retry with clock_skew tolerance instead of blocking sleep
                decoded_token = id_token.verify_oauth2_token(
                    id_token_str,
                    request_obj,
                    client_id,
                    clock_skew_in_seconds=10,
                )
            else:
                # Re-raise other ValueError exceptions
                raise
        
        # Extract user information
        # Google OAuth tokens use 'sub' as the user ID, not 'uid'
        user_info = {
            'uid': decoded_token.get('sub'),  # Google OAuth uses 'sub' as user ID
            'email': decoded_token.get('email'),
            'name': decoded_token.get('name'),
            'picture': decoded_token.get('picture'),
            'email_verified': decoded_token.get('email_verified', False),
        }
        
        # Ensure we have at least email and sub
        if not user_info['uid']:
            raise ValueError("Token missing 'sub' (user ID) claim")
        if not user_info['email']:
            raise ValueError("Token missing 'email' claim")
        
        return user_info
    except ValueError:
        # Re-raise ValueError as-is (these are our validation errors)
        raise
    except Exception as e:
        raise ValueError(f"Google OAuth token verification failed: {str(e)}")


def verify_google_access_token(access_token: str) -> Dict[str, Any]:
    """
    Verify Google OAuth Access Token by calling UserInfo endpoint
    
    Args:
        access_token: Google OAuth Access Token
        
    Returns:
        User information dict
        
    Raises:
        ValueError: If token is invalid
    """
    import requests
    
    try:
        response = requests.get(
            'https://www.googleapis.com/oauth2/v3/userinfo',
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10
        )
        
        if response.status_code != 200:
            raise ValueError(f"Invalid access token or failed request (Status: {response.status_code})")
            
        user_info = response.json()
        
        # Normalize fields to match ID token structure
        # UserInfo endpoint returns 'sub' as user ID
        result = {
            'uid': user_info.get('sub'),
            'email': user_info.get('email'),
            'name': user_info.get('name'),
            'picture': user_info.get('picture'),
            'email_verified': user_info.get('email_verified', False),
        }
        
        if not result['uid'] or not result['email']:
            raise ValueError("UserInfo missing required fields (sub/email)")
            
        return result
        
    except Exception as e:
        raise ValueError(f"Google Access Token verification failed: {str(e)}")


def create_jwt_token(user_id: str, email: str) -> str:
    """
    Create a JWT session token for the user
    
    Args:
        user_id: User's unique identifier
        email: User's email address
        
    Returns:
        Encoded JWT token string
    """
    if not settings.jwt_secret_key:
        raise ValueError("JWT_SECRET_KEY not configured")
    
    expiration = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expiration_hours or 24)

    payload = {
        'sub': user_id,  # Subject (user ID)
        'email': email,
        'exp': expiration,
        'iat': datetime.now(timezone.utc),
        'type': 'access',
    }

    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )

    return token


def create_refresh_token(user_id: str, email: str) -> str:
    """
    Create a long-lived JWT refresh token for the user.

    The client exchanges this (via /api/auth/refresh) for a fresh access token
    without re-running Google OAuth, so a user stays logged in until the refresh
    token itself expires.

    Args:
        user_id: User's unique identifier
        email: User's email address

    Returns:
        Encoded JWT refresh token string
    """
    if not settings.jwt_secret_key:
        raise ValueError("JWT_SECRET_KEY not configured")

    expiration = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_expiration_days or 60)

    payload = {
        'sub': user_id,
        'email': email,
        'exp': expiration,
        'iat': datetime.now(timezone.utc),
        'type': 'refresh',
    }

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm
    )


def verify_jwt_token(token: str, expected_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Verify and decode a JWT session token

    Args:
        token: JWT token string
        expected_type: If set ("access" or "refresh"), reject tokens whose
            ``type`` claim does not match. Legacy tokens minted before the
            refresh-token rollout have no ``type`` claim and are treated as
            "access" for backward compatibility.

    Returns:
        Decoded token payload or None if invalid
    """
    if not settings.jwt_secret_key:
        return None

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
    except JWTError:
        return None

    if expected_type is not None:
        token_type = payload.get('type', 'access')
        if token_type != expected_type:
            return None

    return payload

