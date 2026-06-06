"""Admin authentication module."""

from src.auth.admin_auth import (
    AdminAccess,
    get_admin_access,
    is_admin_email,
)

__all__ = [
    "AdminAccess",
    "get_admin_access",
    "is_admin_email",
]
