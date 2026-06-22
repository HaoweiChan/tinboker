"""
Authentication routes for Google OAuth
"""
from fastapi import APIRouter, HTTPException, Header
from typing import Optional
from src.models.user import AuthResponse
from src.database.user_db import get_or_create_user, get_user_by_email
from src.utils.auth import (
    verify_google_token,
    verify_google_access_token,
    create_jwt_token,
    create_refresh_token,
    verify_jwt_token,
)

router = APIRouter(prefix="/api/auth", tags=["authentication"])


@router.post("/google", response_model=AuthResponse)
async def google_login(request: dict):
    """
    Authenticate user with Google ID token or Access Token
    
    Request body (one of):
    {
        "idToken": "google-id-token-string"
    }
    OR
    {
        "accessToken": "google-access-token-string"
    }
    """
    id_token = request.get("idToken")
    access_token = request.get("accessToken")
    
    if not id_token and not access_token:
        raise HTTPException(
            status_code=400,
            detail="idToken or accessToken is required"
        )
    
    try:
        if id_token:
            # Verify Google ID token
            google_user = verify_google_token(id_token)
        else:
            # Verify Google Access Token
            google_user = verify_google_access_token(access_token)
        
        # Get or create user in database
        user = get_or_create_user(
            google_id=google_user['uid'],
            email=google_user['email'],
            name=google_user.get('name', 'User'),
            avatar=google_user.get('picture'),
            email_verified=google_user.get('email_verified', False)
        )
        
        # Create JWT session tokens
        jwt_token = create_jwt_token(user.id, user.email)
        refresh_token = create_refresh_token(user.id, user.email)

        return AuthResponse(
            user=user,
            token=jwt_token,
            refresh_token=refresh_token,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=401,
            detail=f"Authentication failed: {str(e)}"
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Auth endpoint internal error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred during authentication. Please try again later."
        )


@router.get("/me")
async def get_current_user(authorization: Optional[str] = Header(None)):
    """
    Get current authenticated user from JWT token
    
    Headers:
        Authorization: Bearer <jwt-token>
    
    Returns:
        User information
    """
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authorization header is required"
        )
    
    # Extract token from "Bearer <token>"
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise ValueError("Invalid authorization scheme")
    except ValueError:
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization header format. Expected: Bearer <token>"
        )
    
    # Verify JWT token (reject refresh tokens used as access tokens)
    payload = verify_jwt_token(token, expected_type="access")
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )

    # Get user from database
    user = get_user_by_email(payload['email'])

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )
    
    return user


@router.get("/is-admin")
async def check_is_admin(authorization: Optional[str] = Header(None)):
    """
    Check if the current JWT user is in the ADMIN_EMAILS list.
    Used by non-production environments to gate access.
    Returns { "is_admin": bool } — never raises 4xx so the frontend can handle the result gracefully.
    """
    if not authorization:
        return {"is_admin": False}
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            return {"is_admin": False}
    except ValueError:
        return {"is_admin": False}

    payload = verify_jwt_token(token)
    if not payload:
        return {"is_admin": False}

    from src.config import settings
    email = (payload.get("email") or "").lower()
    admin_set = {e.lower() for e in settings.admin_emails}
    return {"is_admin": email in admin_set}


@router.post("/dev-token", response_model=AuthResponse)
async def dev_token_login(request: dict):
    """
    Bypass Google OAuth for automated browser testing (Cursor browser MCP).
    Only available when ENVIRONMENT != production and DEV_BYPASS_TOKEN is set.
    """
    from src.config import settings

    if settings.environment == "production":
        raise HTTPException(status_code=404, detail="Not found")
    if not settings.dev_bypass_token:
        raise HTTPException(status_code=403, detail="Dev bypass not configured")

    token = request.get("token")
    if not token or token != settings.dev_bypass_token:
        raise HTTPException(status_code=401, detail="Invalid bypass token")

    email = settings.admin_emails[0] if settings.admin_emails else "dev@tinboker.com"
    user = get_or_create_user(
        google_id="dev-bypass-user",
        email=email,
        name="Dev Browser",
        avatar=None,
        email_verified=True,
    )
    jwt_token = create_jwt_token(user.id, user.email)
    refresh_token = create_refresh_token(user.id, user.email)
    return AuthResponse(user=user, token=jwt_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=AuthResponse)
async def refresh_token_endpoint(request: dict):
    """
    Exchange a valid refresh token for a fresh access token.

    Request body:
    {
        "refresh_token": "<jwt-refresh-token>"
    }

    The frontend calls this transparently when an access token expires, so the
    user stays logged in without re-running Google OAuth. Returns a rotated
    refresh token alongside the new access token.
    """
    refresh_token = request.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="refresh_token is required")

    payload = verify_jwt_token(refresh_token, expected_type="refresh")
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user = get_user_by_email(payload["email"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Issue a fresh access token and rotate the refresh token.
    new_access = create_jwt_token(user.id, user.email)
    new_refresh = create_refresh_token(user.id, user.email)
    return AuthResponse(user=user, token=new_access, refresh_token=new_refresh)


@router.post("/logout")
async def logout():
    """
    Logout endpoint (client-side token removal)
    
    Note: Since we're using stateless JWT tokens, logout is handled
    client-side by removing the token. This endpoint exists for
    consistency and future token blacklisting if needed.
    """
    return {"message": "Logged out successfully"}

