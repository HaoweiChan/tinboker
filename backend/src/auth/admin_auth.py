"""
Admin authentication utilities using JWT tokens.
Password and JWT secret are loaded from Google Secret Manager via settings.

Admin access can be granted via:
1. Admin password login (generates admin JWT)
2. Whitelisted Google accounts (uses regular user JWT, checks email against ADMIN_EMAILS)
"""

import logging
import secrets
from typing import Optional
from datetime import datetime, timedelta
from jose import JWTError, jwt
from pydantic import BaseModel
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from src.config import settings

logger = logging.getLogger(__name__)

# JWT configuration
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

# HTTP Bearer scheme for token extraction
security = HTTPBearer()

# Cached fallback secret for dev (generated once per process, not per call)
_fallback_jwt_secret: Optional[str] = None


class AdminTokenData(BaseModel):
    """Data stored in admin JWT token."""
    sub: str = "admin"
    exp: datetime


class LoginRequest(BaseModel):
    """Request schema for admin login."""
    password: str


class LoginResponse(BaseModel):
    """Response schema for admin login."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


def _get_jwt_secret() -> str:
    """
    Get JWT secret from settings (which loads from GSM).
    Falls back to a per-process random secret in development — cached so
    tokens issued and verified in the same process lifetime remain valid.
    """
    global _fallback_jwt_secret
    if settings.admin_jwt_secret:
        return settings.admin_jwt_secret
    if settings.is_development:
        if _fallback_jwt_secret is None:
            _fallback_jwt_secret = secrets.token_hex(32)
            logger.warning(
                "ADMIN_JWT_SECRET not configured, generated a per-process secret. "
                "Tokens will be invalidated on every container restart. "
                "Set ADMIN_JWT_SECRET in Google Secret Manager for dev."
            )
        return _fallback_jwt_secret
    raise ValueError(
        "ADMIN_JWT_SECRET must be configured in production. "
        "Add it to Google Secret Manager."
    )


def _get_admin_password() -> str:
    """
    Get admin password from settings (which loads from GSM).
    """
    if settings.admin_password:
        return settings.admin_password
    raise ValueError(
        "ADMIN_PASSWORD must be configured. "
        "Add it to Google Secret Manager."
    )


def verify_admin_password(password: str) -> bool:
    """
    Verify the provided password against the configured admin password.
    Uses constant-time comparison to prevent timing attacks.
    """
    try:
        stored_password = _get_admin_password()
        return secrets.compare_digest(password, stored_password)
    except ValueError:
        return False


def create_admin_token() -> LoginResponse:
    """
    Create a new JWT token for admin access.
    """
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    token_data = {
        "sub": "admin",
        "exp": expire,
        "iat": datetime.utcnow(),
    }
    access_token = jwt.encode(token_data, _get_jwt_secret(), algorithm=ALGORITHM)
    return LoginResponse(
        access_token=access_token,
        expires_in=ACCESS_TOKEN_EXPIRE_HOURS * 3600  # seconds
    )


def verify_admin_token(token: str) -> Optional[AdminTokenData]:
    """
    Verify and decode a JWT token.
    Returns None if token is invalid or expired.
    """
    try:
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=[ALGORITHM])
        sub = payload.get("sub")
        exp = payload.get("exp")
        if sub != "admin":
            return None
        return AdminTokenData(sub=sub, exp=datetime.fromtimestamp(exp))
    except JWTError as e:
        logger.debug(f"JWT verification failed: {e}")
        return None


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> AdminTokenData:
    """
    FastAPI dependency to verify admin authentication.
    Raises HTTPException if not authenticated.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    token_data = verify_admin_token(credentials.credentials)
    if token_data is None:
        raise credentials_exception
    return token_data


def is_admin_email(email: str) -> bool:
    """
    Check if an email is in the admin whitelist.
    Comparison is case-insensitive.
    """
    if not email or not settings.admin_emails:
        return False
    return email.lower() in settings.admin_emails


class AdminAccess(BaseModel):
    """Unified admin access data (from admin token or whitelisted user)"""
    is_admin_token: bool = False  # True if authenticated via admin JWT
    is_whitelisted_user: bool = False  # True if authenticated via user JWT with whitelisted email
    email: Optional[str] = None  # User email (if whitelisted user)
    user_id: Optional[str] = None  # User ID (if whitelisted user)


async def get_admin_access(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> AdminAccess:
    """
    FastAPI dependency that allows admin access via:
    1. Admin JWT token (from password login)
    2. Regular user JWT token if user's email is in ADMIN_EMAILS whitelist

    This allows whitelisted Google accounts to access admin features
    without needing to know the admin password.
    """
    token = credentials.credentials
    # First, try admin token
    admin_data = verify_admin_token(token)
    if admin_data is not None:
        return AdminAccess(is_admin_token=True)
    # If not admin token, try to verify as user token
    try:
        from src.utils.auth import verify_jwt_token
        user_data = verify_jwt_token(token)
        if user_data and "email" in user_data:
            email = user_data["email"]
            if is_admin_email(email):
                return AdminAccess(
                    is_whitelisted_user=True,
                    email=email,
                    user_id=user_data.get("user_id")
                )
    except Exception as e:
        logger.debug(f"User token verification failed: {e}")
    # Neither admin token nor whitelisted user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin access required. Either use admin login or sign in with a whitelisted account.",
        headers={"WWW-Authenticate": "Bearer"},
    )
