"""
Notification routes for user notifications
"""
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Depends, Query
from src.models.user import UserResponse
from src.models.notification import (
    NotificationListResponse,
    MarkReadResponse,
    BulkMarkReadResponse
)
from src.utils.dependencies import get_current_user
from src.auth.admin_auth import get_admin_access, AdminAccess
from src.database.notification_db import (
    get_user_notifications,
    get_notification_by_id,
    mark_notification_as_read,
    mark_all_notifications_as_read,
    delete_notification,
    get_unread_count
)
from src.services.notification_service import (
    notify_new_episode,
    notify_stock_mention
)


class TriggerNewEpisodeRequest(BaseModel):
    """Request to trigger notifications for a new episode"""
    podcast_name: str
    episode_id: str
    episode_title: str


class TriggerStockMentionRequest(BaseModel):
    """Request to trigger notifications for stock mentions in an episode"""
    ticker: str
    stock_name: str
    episode_id: str
    podcast_name: str


class TriggerNotificationResponse(BaseModel):
    """Response for trigger endpoints"""
    notifications_created: int
    message: str

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: UserResponse = Depends(get_current_user)
):
    """
    Get user's notifications with pagination.

    - **limit**: Maximum number of notifications to return (1-100)
    - **offset**: Number of notifications to skip for pagination
    """
    notifications, total, has_more = get_user_notifications(user.id, limit, offset)
    return NotificationListResponse(
        notifications=notifications,
        total=total,
        has_more=has_more
    )


@router.get("/unread-count")
async def get_unread_notification_count(
    user: UserResponse = Depends(get_current_user)
):
    """Get count of unread notifications"""
    count = get_unread_count(user.id)
    return {"unread_count": count}


@router.post("/{notification_id}/read", response_model=MarkReadResponse)
async def mark_as_read(
    notification_id: str,
    user: UserResponse = Depends(get_current_user)
):
    """Mark a specific notification as read"""
    notification = mark_notification_as_read(user.id, notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    return MarkReadResponse(id=notification.id, is_read=notification.is_read)


@router.post("/read-all", response_model=BulkMarkReadResponse)
async def mark_all_as_read(
    user: UserResponse = Depends(get_current_user)
):
    """Mark all notifications as read"""
    count = mark_all_notifications_as_read(user.id)
    return BulkMarkReadResponse(updated_count=count)


@router.delete("/{notification_id}")
async def remove_notification(
    notification_id: str,
    user: UserResponse = Depends(get_current_user)
):
    """Delete a notification"""
    # First check if notification exists and belongs to user
    notification = get_notification_by_id(user.id, notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    success = delete_notification(user.id, notification_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete notification")
    return {"message": "Notification deleted", "id": notification_id}


# Admin endpoints for triggering notifications (used by ingestion scripts)
@router.post("/trigger/new-episode", response_model=TriggerNotificationResponse)
async def trigger_new_episode_notifications(
    request: TriggerNewEpisodeRequest,
    admin: AdminAccess = Depends(get_admin_access)
):
    """
    Trigger notifications for all users subscribed to a podcast when a new episode is released.
    This endpoint is called by the podcast ingestion script after uploading a new episode.
    Requires admin authentication.
    """
    notifications = notify_new_episode(
        podcast_name=request.podcast_name,
        episode_id=request.episode_id,
        episode_title=request.episode_title
    )
    return TriggerNotificationResponse(
        notifications_created=len(notifications),
        message=f"Created {len(notifications)} notifications for new episode"
    )


@router.post("/trigger/stock-mention", response_model=TriggerNotificationResponse)
async def trigger_stock_mention_notifications(
    request: TriggerStockMentionRequest,
    admin: AdminAccess = Depends(get_admin_access)
):
    """
    Trigger notifications for users who have a stock in their watchlist
    when it's mentioned in a podcast episode.
    Requires admin authentication.
    """
    notifications = notify_stock_mention(
        ticker=request.ticker,
        stock_name=request.stock_name,
        episode_id=request.episode_id,
        podcast_name=request.podcast_name
    )
    return TriggerNotificationResponse(
        notifications_created=len(notifications),
        message=f"Created {len(notifications)} notifications for stock mention"
    )
