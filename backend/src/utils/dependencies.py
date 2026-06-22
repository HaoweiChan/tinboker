"""
FastAPI dependencies for authentication and authorization
"""
from fastapi import HTTPException, Header
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

