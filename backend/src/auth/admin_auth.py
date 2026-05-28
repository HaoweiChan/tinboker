"""
Admin authentication via Google OAuth + ADMIN_EMAILS whitelist.
Access is granted to any signed-in user whose email appears in ADMIN_EMAILS (GSM).
"""

import logging
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
    """
    try:
        from src.utils.auth import verify_jwt_token
        user_data = verify_jwt_token(credentials.credentials)
        if user_data and "email" in user_data:
            email = user_data["email"]
            if is_admin_email(email):
                return AdminAccess(email=email, user_id=user_data.get("user_id"))
    except Exception as e:
        logger.debug(f"Token verification failed: {e}")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin access required. Sign in with a whitelisted Google account.",
        headers={"WWW-Authenticate": "Bearer"},
    )
