"""
Admin authentication via Google OAuth + ADMIN_EMAILS whitelist.
Access is granted to any signed-in user whose email appears in ADMIN_EMAILS (GSM).
"""

import logging
import secrets
from typing import Optional
from pydantic import BaseModel
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from src.config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer()


class AdminAccess(BaseModel):
    """Admin access data extracted from the user's JWT."""
    email: str
    user_id: Optional[str] = None


def is_admin_email(email: str) -> bool:
    if not email or not settings.admin_emails:
        return False
    return email.lower() in settings.admin_emails


async def get_admin_access(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> AdminAccess:
    """
    FastAPI dependency: accepts a regular user JWT (from Google OAuth).
    Grants access if the user's email is in the ADMIN_EMAILS whitelist (GSM).

    Returns:
    - 401 when the token is missing, invalid, or expired (so the frontend can
      silently refresh the access token via its 401 interceptor).
    - 403 when the token is valid but the email is not in the admin allowlist.
    """
    try:
        from src.utils.auth import verify_jwt_token
        user_data = verify_jwt_token(credentials.credentials)
        if user_data and "email" in user_data:
            email = user_data["email"]
            if is_admin_email(email):
                return AdminAccess(email=email, user_id=user_data.get("sub"))
            # Valid JWT, but not an admin email → 403 (the right status; no refresh will help).
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required. Sign in with a whitelisted Google account.",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.debug(f"Token verification failed: {e}")
    # Token missing / invalid / expired → 401 so the browser can refresh.
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token. Please re-authenticate.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_translation_access(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> AdminAccess:
    """
    Dependency for the translation list + bulk-write endpoints.

    Accepts EITHER a whitelisted admin JWT (the admin UI) OR the non-expiring
    TINBOKER_WRITE_TOKEN service token (the headless backfill agent). The service
    token is scoped to these translation endpoints only — it does not unlock other
    admin routes.
    """
    token = credentials.credentials

    # 1. Admin JWT path (same as get_admin_access).
    try:
        from src.utils.auth import verify_jwt_token
        user_data = verify_jwt_token(token)
        if user_data and "email" in user_data:
            if is_admin_email(user_data["email"]):
                return AdminAccess(email=user_data["email"], user_id=user_data.get("sub"))
            # Valid token but not admin/service → fall through to service-token check.
    except Exception as e:
        logger.debug(f"Token verification failed: {e}")

    # 2. Service-token path (constant-time compare; only if configured).
    service_token = settings.tinboker_write_token
    if service_token and secrets.compare_digest(token, service_token):
        return AdminAccess(email="translation-writer@service", user_id="service")

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin or translation-writer access required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_content_write_access(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AdminAccess:
    """
    Dependency for content-mutation endpoints (episode summary/patch/regenerate,
    knowledge-graph create/update/delete, news fetch).

    Accepts an admin JWT (the dev-portal editor) OR the TINBOKER_WRITE_TOKEN service
    token (the headless content pipeline / regen agent that writes back to the API).
    Without one of these, the request is rejected — these endpoints mutate production
    content and must never be reachable anonymously.
    """
    token = credentials.credentials

    try:
        from src.utils.auth import verify_jwt_token
        user_data = verify_jwt_token(token)
        if user_data and "email" in user_data:
            if is_admin_email(user_data["email"]):
                return AdminAccess(email=user_data["email"], user_id=user_data.get("sub"))
    except Exception as e:
        logger.debug(f"Token verification failed: {e}")

    service_token = settings.tinboker_write_token
    if service_token and secrets.compare_digest(token, service_token):
        return AdminAccess(email="content-writer@service", user_id="service")

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin or content-writer access required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_article_author_access(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AdminAccess:
    """
    Dependency for article write endpoints.

    Accepts an admin JWT OR the TINBOKER_ARTICLE_TOKEN service token.
    Scoped to article endpoints only — does not unlock other admin routes.
    """
    token = credentials.credentials

    try:
        from src.utils.auth import verify_jwt_token
        user_data = verify_jwt_token(token)
        if user_data and "email" in user_data:
            if is_admin_email(user_data["email"]):
                return AdminAccess(email=user_data["email"], user_id=user_data.get("sub"))
    except Exception as e:
        logger.debug(f"Token verification failed: {e}")

    service_token = settings.tinboker_article_token
    if service_token and secrets.compare_digest(token, service_token):
        return AdminAccess(email="article-author@service", user_id="article-service")

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin or article-author access required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_social_access(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AdminAccess:
    """
    Dependency for the Threads publish endpoint.

    Accepts an admin JWT OR the TINBOKER_SOCIAL_TOKEN service token, so the agents'
    podcast pipeline can trigger a publish run post-ingest without an admin login.
    Scoped to the social/publish endpoints only — does not unlock other admin routes.
    """
    token = credentials.credentials

    try:
        from src.utils.auth import verify_jwt_token
        user_data = verify_jwt_token(token)
        if user_data and "email" in user_data:
            if is_admin_email(user_data["email"]):
                return AdminAccess(email=user_data["email"], user_id=user_data.get("sub"))
    except Exception as e:
        logger.debug(f"Token verification failed: {e}")

    service_token = settings.tinboker_social_token
    if service_token and secrets.compare_digest(token, service_token):
        return AdminAccess(email="social-publisher@service", user_id="service")

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin or social-publisher access required.",
        headers={"WWW-Authenticate": "Bearer"},
    )
