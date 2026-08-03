"""
Notification service for creating and managing notifications
"""
import json
from typing import List, Optional

from sqlalchemy import text

from src.models.notification import (
    NotificationType,
    NotificationCreate,
    NotificationResponse
)
from src.database.models import User
from src.database.notification_db import create_notification
from src.database.postgres import session_scope


def _subscribers(field: str, value: str, pref_key: Optional[str] = None) -> List[str]:
    """IDs of users whose ``field`` array contains ``value`` and who opted in.

    ``field`` is one of the JSON subscription arrays on ``users`` (fixed set below —
    never caller-supplied SQL). Postgres does the containment test in the database
    (JSONB ``@>``); SQLite has no such operator, so dev filters the (tiny) table in
    Python. ``pref_key`` is the notification_preferences toggle, default on; pass
    None for categories where subscribing IS the opt-in (tag follows).
    """
    # Not an assert: this guards an f-string interpolated into SQL below, and
    # asserts are stripped under `python -O`.
    if field not in ("watchlist", "podcast_subscriptions", "tag_subscriptions"):
        raise ValueError(f"Invalid subscription field: {field}")

    with session_scope() as db:
        query = db.query(User.id, getattr(User, field), User.notification_preferences)
        if db.bind.dialect.name == "postgresql":
            query = query.filter(
                text(f"users.{field} @> CAST(:needle AS jsonb)")
            ).params(needle=json.dumps([value]))
        rows = query.all()

    return [
        user_id
        for user_id, subscribed, prefs in rows
        if value in (subscribed or [])
        and (pref_key is None or (prefs or {}).get(pref_key, True))
    ]


def create_user_notification(
    user_id: str,
    notification_type: NotificationType,
    title: str,
    body: str,
    data: dict = None
) -> NotificationResponse:
    """
    Create a notification for a specific user.

    Args:
        user_id: The user's ID
        notification_type: Type of notification
        title: Notification title
        body: Notification body/description
        data: Additional data (e.g., episode_id, ticker, etc.)

    Returns:
        Created NotificationResponse
    """
    notification = NotificationCreate(
        user_id=user_id,
        type=notification_type,
        title=title,
        body=body,
        data=data or {}
    )
    return create_notification(notification)


def notify_new_episode(
    podcast_name: str,
    episode_id: str,
    episode_title: str
) -> List[NotificationResponse]:
    """
    Create notifications for all users subscribed to a podcast when a new episode is released.

    Args:
        podcast_name: Name of the podcast
        episode_id: ID of the new episode
        episode_title: Title of the new episode

    Returns:
        List of created notifications
    """
    created_notifications = []

    try:
        # Find all users subscribed to this podcast
        for user_id in _subscribers("podcast_subscriptions", podcast_name, "new_episodes"):
            notification = create_user_notification(
                user_id=user_id,
                notification_type=NotificationType.NEW_EPISODE,
                title=f"{podcast_name} 發布新集數",
                body=episode_title,
                data={
                    "podcast_name": podcast_name,
                    "episode_id": episode_id
                }
            )
            created_notifications.append(notification)
            print(f"[NotificationService] Created new episode notification for user {user_id}")

    except Exception as e:
        print(f"[NotificationService] Error creating new episode notifications: {e}")

    return created_notifications


def notify_stock_mention(
    ticker: str,
    stock_name: str,
    episode_id: str,
    podcast_name: str
) -> List[NotificationResponse]:
    """
    Create notifications for users who have a stock in their watchlist when it's mentioned in a new episode.

    Args:
        ticker: Stock ticker symbol
        stock_name: Name of the stock
        episode_id: ID of the episode mentioning the stock
        podcast_name: Name of the podcast

    Returns:
        List of created notifications
    """
    created_notifications = []

    try:
        # Avoid an ugly "2330 (2330)" when no display name is known (producer passes ticker).
        label = f"{stock_name} ({ticker})" if stock_name and stock_name != ticker else ticker
        # Find all users with this ticker in their watchlist
        for user_id in _subscribers("watchlist", ticker, "stock_mentions"):
            notification = create_user_notification(
                user_id=user_id,
                notification_type=NotificationType.STOCK_MENTION,
                title=f"{label} 被 Podcast 提及",
                body=f"{podcast_name} 在最新一集中分析了此標的",
                data={
                    "ticker": ticker,
                    "episode_id": episode_id,
                    "podcast_name": podcast_name
                }
            )
            created_notifications.append(notification)
            print(f"[NotificationService] Created stock mention notification for user {user_id}")

    except Exception as e:
        print(f"[NotificationService] Error creating stock mention notifications: {e}")

    return created_notifications


def notify_topic_mention(
    tag: str,
    episode_id: str,
    podcast_name: str,
    episode_title: str
) -> List[NotificationResponse]:
    """
    Create notifications for users who follow a tag/topic when it appears in a new episode.

    Subscribing to the tag is itself the opt-in, so there is no separate preference toggle.

    Returns:
        List of created notifications
    """
    created_notifications = []

    try:
        for user_id in _subscribers("tag_subscriptions", tag):
            notification = create_user_notification(
                user_id=user_id,
                notification_type=NotificationType.TOPIC_MENTION,
                title=f"關注主題「{tag}」有新內容",
                body=f"{podcast_name}：{episode_title}",
                data={
                    "tag": tag,
                    "episode_id": episode_id,
                    "podcast_name": podcast_name
                }
            )
            created_notifications.append(notification)

    except Exception as e:
        print(f"[NotificationService] Error creating topic mention notifications: {e}")

    return created_notifications


def notify_price_alert(
    user_id: str,
    ticker: str,
    stock_name: str,
    alert_type: str,  # e.g., "price_up", "price_down", "target_reached"
    current_price: float,
    threshold: Optional[float] = None
) -> NotificationResponse:
    """
    Create a price alert notification for a specific user.

    Args:
        user_id: User's ID
        ticker: Stock ticker
        stock_name: Name of the stock
        alert_type: Type of price alert
        current_price: Current stock price
        threshold: Price threshold that triggered the alert (optional)

    Returns:
        Created NotificationResponse
    """
    alert_messages = {
        "price_up": "漲幅超過警示閾值",
        "price_down": "跌幅超過警示閾值",
        "target_reached": f"達到目標價位 {threshold}" if threshold else "達到目標價位"
    }

    body = alert_messages.get(alert_type, "價格變動提醒")

    return create_user_notification(
        user_id=user_id,
        notification_type=NotificationType.PRICE_ALERT,
        title=f"{stock_name} ({ticker}) 價格警示",
        body=f"{body} - 目前價格 {current_price}",
        data={
            "ticker": ticker,
            "alert_type": alert_type,
            "current_price": current_price,
            "threshold": threshold
        }
    )
