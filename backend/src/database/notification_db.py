"""
Notification database operations, backed by the ORM (Postgres in staging/prod,
SQLite in dev).

Was the Firestore ``users/{user_id}/notifications`` subcollection until P3 of the
Firestore exit (docs/firestore-contract.md § 11.5). Public signatures unchanged.
"""
import uuid
from typing import Optional, List, Tuple
from datetime import datetime, timezone, timedelta

from sqlalchemy import func

from src.database.models import UserNotification
from src.database.postgres import session_scope
from src.models.notification import (
    NotificationType,
    NotificationCreate,
    NotificationResponse,
)


def _to_notification_response(row: UserNotification) -> NotificationResponse:
    """Convert a UserNotification row to the API/response model."""
    return NotificationResponse(
        id=row.id,
        user_id=row.user_id,
        type=row.type or NotificationType.NEW_EPISODE,
        title=row.title or "",
        body=row.body or "",
        data=row.data or {},
        is_read=bool(row.is_read),
        created_at=row.created_at or datetime.now(timezone.utc),
    )


def create_notification(notification: NotificationCreate) -> NotificationResponse:
    """Create a new notification"""
    with session_scope() as db:
        row = UserNotification(
            id=str(uuid.uuid4()),
            user_id=notification.user_id,
            type=notification.type.value,
            title=notification.title,
            body=notification.body,
            data=notification.data,
            is_read=False,
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.flush()
        return _to_notification_response(row)


def get_user_notifications(
    user_id: str,
    limit: int = 50,
    offset: int = 0
) -> Tuple[List[NotificationResponse], int, bool]:
    """
    Get notifications for a user with pagination.
    Returns (notifications, total_count, has_more)
    """
    try:
        with session_scope() as db:
            base = db.query(UserNotification).filter(UserNotification.user_id == user_id)
            total = base.with_entities(func.count()).scalar() or 0
            rows = (
                base.order_by(UserNotification.created_at.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return (
                [_to_notification_response(row) for row in rows],
                total,
                (offset + limit) < total,
            )
    except Exception as e:
        print(f"Error fetching notifications: {e}")
        return [], 0, False


def get_notification_by_id(user_id: str, notification_id: str) -> Optional[NotificationResponse]:
    """Get a specific notification by ID"""
    try:
        with session_scope() as db:
            row = (
                db.query(UserNotification)
                .filter(
                    UserNotification.id == notification_id,
                    UserNotification.user_id == user_id,
                )
                .one_or_none()
            )
            return _to_notification_response(row) if row else None
    except Exception:
        return None


def mark_notification_as_read(user_id: str, notification_id: str) -> Optional[NotificationResponse]:
    """Mark a notification as read"""
    try:
        with session_scope() as db:
            row = (
                db.query(UserNotification)
                .filter(
                    UserNotification.id == notification_id,
                    UserNotification.user_id == user_id,
                )
                .one_or_none()
            )
            if not row:
                return None
            row.is_read = True
            return _to_notification_response(row)
    except Exception as e:
        print(f"Error marking notification as read: {e}")
        return None


def mark_all_notifications_as_read(user_id: str) -> int:
    """Mark all notifications as read for a user. Returns count of updated notifications."""
    try:
        with session_scope() as db:
            return (
                db.query(UserNotification)
                .filter(
                    UserNotification.user_id == user_id,
                    UserNotification.is_read.is_(False),
                )
                .update({UserNotification.is_read: True}, synchronize_session=False)
            )
    except Exception as e:
        print(f"Error marking all notifications as read: {e}")
        return 0


def delete_notification(user_id: str, notification_id: str) -> bool:
    """Delete a notification"""
    try:
        with session_scope() as db:
            db.query(UserNotification).filter(
                UserNotification.id == notification_id,
                UserNotification.user_id == user_id,
            ).delete(synchronize_session=False)
            return True
    except Exception as e:
        print(f"Error deleting notification: {e}")
        return False


def get_unread_count(user_id: str) -> int:
    """Get count of unread notifications for a user.

    Counted server-side (SELECT count(*)). Loading the matching rows and counting
    them in Python cost one row transfer per unread notification, which is why this
    endpoint's tail reached 90s for users with a backlog on the Firestore version.
    """
    try:
        with session_scope() as db:
            return int(
                db.query(func.count(UserNotification.id))
                .filter(
                    UserNotification.user_id == user_id,
                    UserNotification.is_read.is_(False),
                )
                .scalar()
                or 0
            )
    except Exception as e:
        print(f"Error counting unread notifications: {e}")
        return 0


def cleanup_old_notifications(days: int = 30) -> int:
    """
    Delete notifications older than specified days.
    This should be called by a scheduled job.
    Returns count of deleted notifications.
    """
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        with session_scope() as db:
            return (
                db.query(UserNotification)
                .filter(UserNotification.created_at < cutoff_date)
                .delete(synchronize_session=False)
            )
    except Exception as e:
        print(f"Error cleaning up old notifications: {e}")
        return 0
