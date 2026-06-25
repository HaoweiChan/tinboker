"""
Notification models for user notifications
"""
from enum import Enum
from typing import Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field


class NotificationType(str, Enum):
    """Types of notifications"""
    NEW_EPISODE = "new_episode"
    STOCK_MENTION = "stock_mention"
    TOPIC_MENTION = "topic_mention"
    PRICE_ALERT = "price_alert"


class NotificationBase(BaseModel):
    """Base notification model"""
    type: NotificationType
    title: str
    body: str
    data: Dict[str, Any] = Field(default_factory=dict)


class NotificationCreate(NotificationBase):
    """Create notification model"""
    user_id: str


class NotificationResponse(NotificationBase):
    """Notification response model"""
    id: str
    user_id: str
    is_read: bool = False
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    """Paginated notification list response"""
    notifications: List[NotificationResponse]
    total: int
    has_more: bool


class MarkReadResponse(BaseModel):
    """Response for mark as read operations"""
    id: str
    is_read: bool


class BulkMarkReadResponse(BaseModel):
    """Response for bulk mark as read"""
    updated_count: int
