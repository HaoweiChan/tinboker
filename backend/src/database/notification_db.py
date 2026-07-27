"""
Notification database operations using Firestore
"""
import uuid
from typing import Optional, List, Tuple
from datetime import datetime, timezone, timedelta
from src.services.firestore_service import FirestoreService
from src.models.notification import (
    NotificationType,
    NotificationCreate,
    NotificationResponse
)

# Initialize Firestore service (singleton pattern)
_firestore_service = None


def _get_firestore_service() -> FirestoreService:
    """Get or create FirestoreService instance"""
    global _firestore_service
    if _firestore_service is None:
        _firestore_service = FirestoreService()
    return _firestore_service


def _firestore_timestamp_to_datetime(timestamp) -> datetime:
    """Convert Firestore Timestamp to Python datetime"""
    if timestamp is None:
        return datetime.now(timezone.utc)
    if hasattr(timestamp, 'to_datetime'):
        return timestamp.to_datetime()
    if isinstance(timestamp, datetime):
        return timestamp
    if isinstance(timestamp, str):
        try:
            return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        except ValueError:
            return datetime.now(timezone.utc)
    try:
        return datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def _dict_to_notification_response(data: dict) -> NotificationResponse:
    """Convert Firestore document dictionary to NotificationResponse"""
    return NotificationResponse(
        id=data.get('id', ''),
        user_id=data.get('user_id', ''),
        type=data.get('type', NotificationType.NEW_EPISODE),
        title=data.get('title', ''),
        body=data.get('body', ''),
        data=data.get('data', {}),
        is_read=data.get('is_read', False),
        created_at=_firestore_timestamp_to_datetime(data.get('created_at'))
    )


def create_notification(notification: NotificationCreate) -> NotificationResponse:
    """Create a new notification"""
    firestore = _get_firestore_service()
    notification_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    notification_doc = {
        "id": notification_id,
        "user_id": notification.user_id,
        "type": notification.type.value,
        "title": notification.title,
        "body": notification.body,
        "data": notification.data,
        "is_read": False,
        "created_at": now
    }

    # Store in user's notifications subcollection
    collection_path = f"users/{notification.user_id}/notifications"
    firestore.set_document(collection_path, notification_id, notification_doc)

    return _dict_to_notification_response(notification_doc)


def get_user_notifications(
    user_id: str,
    limit: int = 50,
    offset: int = 0
) -> Tuple[List[NotificationResponse], int, bool]:
    """
    Get notifications for a user with pagination.
    Returns (notifications, total_count, has_more)
    """
    firestore = _get_firestore_service()
    collection_path = f"users/{user_id}/notifications"

    try:
        # Query notifications ordered by created_at descending
        # Note: Firestore doesn't have a built-in count, so we fetch all IDs first
        all_docs = firestore.db.collection("users").document(user_id) \
            .collection("notifications") \
            .order_by("created_at", direction="DESCENDING") \
            .stream()

        all_notifications = []
        for doc in all_docs:
            data = doc.to_dict()
            data['id'] = doc.id
            all_notifications.append(data)

        total = len(all_notifications)

        # Apply pagination
        paginated = all_notifications[offset:offset + limit]
        has_more = (offset + limit) < total

        return (
            [_dict_to_notification_response(doc) for doc in paginated],
            total,
            has_more
        )
    except Exception as e:
        print(f"Error fetching notifications: {e}")
        return [], 0, False


def get_notification_by_id(user_id: str, notification_id: str) -> Optional[NotificationResponse]:
    """Get a specific notification by ID"""
    firestore = _get_firestore_service()
    collection_path = f"users/{user_id}/notifications"

    try:
        doc = firestore.get_document(collection_path, notification_id)
        if doc:
            doc['id'] = notification_id
            return _dict_to_notification_response(doc)
        return None
    except Exception:
        return None


def mark_notification_as_read(user_id: str, notification_id: str) -> Optional[NotificationResponse]:
    """Mark a notification as read"""
    firestore = _get_firestore_service()
    collection_path = f"users/{user_id}/notifications"

    try:
        firestore.set_document(
            collection_path,
            notification_id,
            {"is_read": True},
            merge=True
        )

        # Return updated notification
        return get_notification_by_id(user_id, notification_id)
    except Exception as e:
        print(f"Error marking notification as read: {e}")
        return None


def mark_all_notifications_as_read(user_id: str) -> int:
    """Mark all notifications as read for a user. Returns count of updated notifications."""
    firestore = _get_firestore_service()

    try:
        # Get all unread notifications
        docs = firestore.db.collection("users").document(user_id) \
            .collection("notifications") \
            .where("is_read", "==", False) \
            .stream()

        count = 0
        for doc in docs:
            doc.reference.update({"is_read": True})
            count += 1

        return count
    except Exception as e:
        print(f"Error marking all notifications as read: {e}")
        return 0


def delete_notification(user_id: str, notification_id: str) -> bool:
    """Delete a notification"""
    firestore = _get_firestore_service()
    collection_path = f"users/{user_id}/notifications"

    try:
        firestore.db.collection("users").document(user_id) \
            .collection("notifications").document(notification_id).delete()
        return True
    except Exception as e:
        print(f"Error deleting notification: {e}")
        return False


def get_unread_count(user_id: str) -> int:
    """Get count of unread notifications for a user.

    Uses Firestore's server-side count() aggregation. Streaming the matching
    documents and counting them client-side costs one document transfer per
    unread notification, which is why this endpoint's tail reached 90s for
    users with a backlog while the median stayed under a second.
    """
    firestore = _get_firestore_service()

    try:
        query = firestore.db.collection("users").document(user_id) \
            .collection("notifications") \
            .where("is_read", "==", False)

        # count().get() returns [[AggregationResult]] — one result, one aggregation.
        return int(query.count().get()[0][0].value)
    except Exception as e:
        print(f"Error counting unread notifications: {e}")
        return 0


def cleanup_old_notifications(days: int = 30) -> int:
    """
    Delete notifications older than specified days.
    This should be called by a scheduled job.
    Returns count of deleted notifications.
    """
    firestore = _get_firestore_service()
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        # Get all users
        users_docs = firestore.db.collection("users").stream()

        total_deleted = 0
        for user_doc in users_docs:
            # Get old notifications for this user
            old_notifications = firestore.db.collection("users") \
                .document(user_doc.id) \
                .collection("notifications") \
                .where("created_at", "<", cutoff_date) \
                .stream()

            for notification_doc in old_notifications:
                notification_doc.reference.delete()
                total_deleted += 1

        return total_deleted
    except Exception as e:
        print(f"Error cleaning up old notifications: {e}")
        return 0
