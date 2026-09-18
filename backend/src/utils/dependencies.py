"""
FastAPI dependencies for authentication and authorization
"""
from fastapi import Depends, HTTPException, Header
from typing import Optional
from src.utils.auth import verify_jwt_token
from src.database.user_db import get_user_by_email
from src.models.user import UserResponse


def get_current_user(authorization: Optional[str] = Header(None)) -> UserResponse:
    """
    Get current authenticated user from JWT token
    
    Usage:
        @router.get("/protected")
        async def protected_route(user: UserResponse = Depends(get_current_user)):
            return {"user_id": user.id}
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


def get_optional_user(authorization: Optional[str] = Header(None)) -> Optional[UserResponse]:
    """Like get_current_user, but returns None instead of raising when no/invalid auth.

    For endpoints that are public but show extra data to a signed-in viewer.
    """
    if not authorization:
        return None
    try:
        return get_current_user(authorization)
    except HTTPException:
        return None


def require_member(user: UserResponse = Depends(get_current_user)) -> UserResponse:
    """Entitlement gate for member-only routes.

    Usage:
        @router.get("/protected")
        async def protected_route(user: UserResponse = Depends(require_member)):
            return {"user_id": user.id}

    401 (from get_current_user) if not signed in at all; 402 if signed in but not
    a paying member. Nothing is gated on this yet — this PR only adds the machinery.
    """
    if not user.is_member:
        raise HTTPException(status_code=402, detail="Active membership required")
    return user

