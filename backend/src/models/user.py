"""
User models for authentication
"""
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime


class UserBase(BaseModel):
    """Base user model"""
    email: EmailStr
    name: str
    avatar: Optional[str] = None


class UserCreate(UserBase):
    """User creation model"""
    google_id: str  # Google UID


class NotificationPreferences(BaseModel):
    """Notification preferences model"""
    new_episodes: bool = True  # Notify when subscribed podcasts release new episodes
    stock_mentions: bool = True  # Notify when watchlist stocks are mentioned
    price_alerts: bool = True  # Notify on price alerts
    daily_digest: bool = False  # Daily market summary (future feature)


class UserResponse(UserBase):
    """User response model"""
    id: str
    google_id: str
    email_verified: bool
    created_at: datetime
    updated_at: datetime
    # Subscription fields (default to empty lists)
    watchlist: List[str] = []  # Stock tickers
    podcast_subscriptions: List[str] = []  # Podcaster names
    episode_bookmarks: List[str] = []  # Episode IDs
    alerts: List[str] = []  # Stock tickers for alerts
    tag_subscriptions: List[str] = []  # Tag names
    # Notification preferences
    notification_preferences: NotificationPreferences = NotificationPreferences()

    class Config:
        from_attributes = True


class UpdateNotificationPreferencesRequest(BaseModel):
    """Request to update notification preferences"""
    new_episodes: Optional[bool] = None
    stock_mentions: Optional[bool] = None
    price_alerts: Optional[bool] = None
    daily_digest: Optional[bool] = None


class AuthResponse(BaseModel):
    """Authentication response model"""
    user: UserResponse
    token: str  # JWT access token
    refresh_token: Optional[str] = None  # Long-lived JWT for silent re-auth

