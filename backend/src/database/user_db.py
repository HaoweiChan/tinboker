"""
User database operations, backed by the ORM (Postgres in staging/prod, SQLite in dev).

Was Firestore ``users/{user_id}`` until P3 of the Firestore exit
(docs/firestore-contract.md § 11.5). The public function signatures are unchanged —
callers (routers/user.py, routers/auth.py, utils/dependencies.py) were not touched.
"""
import uuid
from typing import Dict, Optional
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from src.database.models import User
from src.database.postgres import session_scope
from src.models.user import UserCreate, UserResponse, NotificationPreferences

MERGED_SECTOR_TAG_SUBSCRIPTION_RENAMES = {
    "日本矽晶圓": "矽晶圓",
    "日本前段設備": "前段製程設備",
    "日本後段設備": "封裝製程機台",
    "日本被動元件": "被動元件 MLCC",
}

# The five list-valued subscription fields; `alerts` has no toggle endpoint yet.
ARRAY_FIELDS = (
    "watchlist",
    "podcast_subscriptions",
    "episode_bookmarks",
    "alerts",
    "tag_subscriptions",
)


def remap_merged_sector_tag_subscriptions(tag_subscriptions: list[str]) -> list[str]:
    """Map merged sector display-name follows to their canonical target names."""
    remapped: list[str] = []
    seen: set[str] = set()
    for tag in tag_subscriptions or []:
        # Legacy entries may carry a '#' prefix (SectorPage matches both forms) —
        # remap those too, preserving the prefix.
        prefix = "#" if isinstance(tag, str) and tag.startswith("#") else ""
        bare = tag[1:] if prefix else tag
        canonical = prefix + MERGED_SECTOR_TAG_SUBSCRIPTION_RENAMES.get(bare, bare)
        if canonical not in seen:
            remapped.append(canonical)
            seen.add(canonical)
    return remapped


def migrate_merged_sector_tag_subscriptions() -> int:
    """One-off idempotent migration for display-name keyed sector follows."""
    migrated = 0
    now = datetime.now(timezone.utc)
    with session_scope() as db:
        for row in db.query(User).all():
            current = row.tag_subscriptions
            if not isinstance(current, list):
                continue
            remapped = remap_merged_sector_tag_subscriptions(current)
            if remapped == current:
                continue
            row.tag_subscriptions = remapped
            row.updated_at = now
            migrated += 1
    return migrated


def _to_user_response(row: User) -> UserResponse:
    """Convert a User row to the API/response model."""
    prefs_data = row.notification_preferences or {}
    return UserResponse(
        id=row.id,
        google_id=row.google_id,
        email=row.email,
        name=row.name or "",
        avatar=row.avatar,
        email_verified=bool(row.email_verified),
        created_at=row.created_at,
        updated_at=row.updated_at,
        watchlist=row.watchlist or [],
        podcast_subscriptions=row.podcast_subscriptions or [],
        episode_bookmarks=row.episode_bookmarks or [],
        alerts=row.alerts or [],
        tag_subscriptions=row.tag_subscriptions or [],
        notification_preferences=NotificationPreferences(
            new_episodes=prefs_data.get("new_episodes", True),
            stock_mentions=prefs_data.get("stock_mentions", True),
            price_alerts=prefs_data.get("price_alerts", True),
            daily_digest=prefs_data.get("daily_digest", False),
        ),
    )


def _get_user(db: Session, user_id: str) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).one_or_none()


def get_user_by_google_id(google_id: str) -> Optional[UserResponse]:
    """Get user by Google ID"""
    try:
        with session_scope() as db:
            row = db.query(User).filter(User.google_id == google_id).one_or_none()
            return _to_user_response(row) if row else None
    except Exception as e:
        raise Exception(f"Failed to get user by Google ID: {e}") from e


def get_user_by_email(email: str) -> Optional[UserResponse]:
    """Get user by email"""
    try:
        with session_scope() as db:
            row = db.query(User).filter(User.email == email).first()
            return _to_user_response(row) if row else None
    except Exception as e:
        raise Exception(f"Failed to get user by email: {e}") from e


def create_user(user_data: UserCreate) -> UserResponse:
    """Create a new user"""
    try:
        now = datetime.now(timezone.utc)
        with session_scope() as db:
            row = User(
                id=str(uuid.uuid4()),
                google_id=user_data.google_id,
                email=user_data.email,
                name=user_data.name,
                avatar=user_data.avatar or "",
                email_verified=False,  # Will be set from Google token
                created_at=now,
                updated_at=now,
                watchlist=[],
                podcast_subscriptions=[],
                episode_bookmarks=[],
                alerts=[],
                tag_subscriptions=[],
                notification_preferences={},
            )
            db.add(row)
            db.flush()
            return _to_user_response(row)
    except Exception as e:
        raise Exception(f"Failed to create user: {e}") from e


def update_user(
    google_id: str,
    name: Optional[str] = None,
    avatar: Optional[str] = None,
    email_verified: Optional[bool] = None,
) -> Optional[UserResponse]:
    """Update user information"""
    try:
        with session_scope() as db:
            row = db.query(User).filter(User.google_id == google_id).one_or_none()
            if not row:
                return None

            updated = False
            for field, value in (
                ("name", name),
                ("avatar", avatar),
                ("email_verified", email_verified),
            ):
                if value is not None:
                    setattr(row, field, value)
                    updated = True

            if updated:
                row.updated_at = datetime.now(timezone.utc)
            return _to_user_response(row)
    except Exception as e:
        raise Exception(f"Failed to update user: {e}") from e


def get_or_create_user(
    google_id: str,
    email: str,
    name: str,
    avatar: Optional[str] = None,
    email_verified: bool = False,
) -> UserResponse:
    """Get existing user or create new one"""
    user = get_user_by_google_id(google_id)

    if user:
        # Update user info if changed
        updated_user = update_user(
            google_id,
            name=name if name != user.name else None,
            avatar=avatar if avatar != user.avatar else None,
            email_verified=email_verified if email_verified != user.email_verified else None,
        )
        return updated_user or user

    # Create new user
    created_user = create_user(
        UserCreate(google_id=google_id, email=email, name=name, avatar=avatar)
    )

    # Update email_verified if needed
    if email_verified:
        return update_user(google_id, email_verified=email_verified) or created_user

    return created_user


def get_user_subscriptions(user_id: str) -> Dict[str, list]:
    """Get all subscriptions for a user"""
    try:
        with session_scope() as db:
            row = _get_user(db, user_id)
            return {
                field: (getattr(row, field) or []) if row else []
                for field in ARRAY_FIELDS
            }
    except Exception as e:
        raise Exception(f"Failed to get user subscriptions: {e}") from e


def _update_array_field(user_id: str, field_name: str, value: str, operation: str) -> bool:
    """Update an array field in the user row (add or remove item).

    ``with_for_update`` makes the read-modify-write on the JSON column atomic under
    Postgres — Firestore's ArrayUnion/ArrayRemove used to provide that. SQLAlchemy's
    SQLite dialect ignores the row lock, which is fine for the single-user dev DB.
    """
    if operation not in ("add", "remove"):
        raise ValueError(f"Invalid operation: {operation}")
    if field_name not in ARRAY_FIELDS:
        raise ValueError(f"Invalid array field: {field_name}")

    try:
        with session_scope() as db:
            row = (
                db.query(User)
                .filter(User.id == user_id)
                .with_for_update()
                .one_or_none()
            )
            if not row:
                raise Exception(f"User {user_id} not found")

            current = list(getattr(row, field_name) or [])
            if operation == "add":
                if value in current:
                    return True  # ArrayUnion semantics: adding twice is a no-op
                current.append(value)
            else:
                if value not in current:
                    return True
                current = [item for item in current if item != value]

            setattr(row, field_name, current)
            row.updated_at = datetime.now(timezone.utc)
            return True
    except Exception as e:
        raise Exception(f"Failed to update array field {field_name}: {e}") from e


def add_to_watchlist(user_id: str, ticker: str) -> bool:
    """Add stock ticker to watchlist"""
    return _update_array_field(user_id, "watchlist", ticker, "add")


def remove_from_watchlist(user_id: str, ticker: str) -> bool:
    """Remove stock ticker from watchlist"""
    return _update_array_field(user_id, "watchlist", ticker, "remove")


def toggle_watchlist(user_id: str, ticker: str) -> Dict[str, any]:
    """Toggle watchlist item, returns {ticker, is_in_watchlist}"""
    subscriptions = get_user_subscriptions(user_id)
    if ticker in subscriptions.get("watchlist", []):
        remove_from_watchlist(user_id, ticker)
        return {"ticker": ticker, "is_in_watchlist": False}
    add_to_watchlist(user_id, ticker)
    return {"ticker": ticker, "is_in_watchlist": True}


def add_podcast_subscription(user_id: str, podcast_name: str) -> bool:
    """Subscribe to a podcaster"""
    return _update_array_field(user_id, "podcast_subscriptions", podcast_name, "add")


def remove_podcast_subscription(user_id: str, podcast_name: str) -> bool:
    """Unsubscribe from a podcaster"""
    return _update_array_field(user_id, "podcast_subscriptions", podcast_name, "remove")


def toggle_podcast_subscription(user_id: str, podcast_name: str) -> Dict[str, any]:
    """Toggle podcast subscription, returns {podcast_name, is_subscribed}"""
    subscriptions = get_user_subscriptions(user_id)
    if podcast_name in subscriptions.get("podcast_subscriptions", []):
        remove_podcast_subscription(user_id, podcast_name)
        return {"podcast_name": podcast_name, "is_subscribed": False}
    add_podcast_subscription(user_id, podcast_name)
    return {"podcast_name": podcast_name, "is_subscribed": True}


def add_episode_bookmark(user_id: str, episode_id: str) -> bool:
    """Bookmark a podcast episode"""
    # Format: "{podcast_name}_{episode_id}" should be passed in
    return _update_array_field(user_id, "episode_bookmarks", episode_id, "add")


def remove_episode_bookmark(user_id: str, episode_id: str) -> bool:
    """Remove episode bookmark"""
    return _update_array_field(user_id, "episode_bookmarks", episode_id, "remove")


def toggle_episode_bookmark(user_id: str, episode_id: str) -> Dict[str, any]:
    """Toggle episode bookmark, returns {episode_id, is_bookmarked}"""
    subscriptions = get_user_subscriptions(user_id)
    if episode_id in subscriptions.get("episode_bookmarks", []):
        remove_episode_bookmark(user_id, episode_id)
        return {"episode_id": episode_id, "is_bookmarked": False}
    add_episode_bookmark(user_id, episode_id)
    return {"episode_id": episode_id, "is_bookmarked": True}


def add_tag_subscription(user_id: str, tag_name: str) -> bool:
    """Subscribe to a tag"""
    return _update_array_field(user_id, "tag_subscriptions", tag_name, "add")


def remove_tag_subscription(user_id: str, tag_name: str) -> bool:
    """Unsubscribe from a tag"""
    return _update_array_field(user_id, "tag_subscriptions", tag_name, "remove")


def toggle_tag_subscription(user_id: str, tag_name: str) -> Dict[str, any]:
    """Toggle tag subscription, returns {tag_name, is_subscribed}"""
    subscriptions = get_user_subscriptions(user_id)
    if tag_name in subscriptions.get("tag_subscriptions", []):
        remove_tag_subscription(user_id, tag_name)
        return {"tag_name": tag_name, "is_subscribed": False}
    add_tag_subscription(user_id, tag_name)
    return {"tag_name": tag_name, "is_subscribed": True}


def _to_preferences(prefs: dict) -> NotificationPreferences:
    return NotificationPreferences(
        new_episodes=prefs.get("new_episodes", True),
        stock_mentions=prefs.get("stock_mentions", True),
        price_alerts=prefs.get("price_alerts", True),
        daily_digest=prefs.get("daily_digest", False),
    )


def update_notification_preferences(
    user_id: str,
    new_episodes: Optional[bool] = None,
    stock_mentions: Optional[bool] = None,
    price_alerts: Optional[bool] = None,
    daily_digest: Optional[bool] = None,
) -> NotificationPreferences:
    """Update notification preferences for a user"""
    try:
        with session_scope() as db:
            row = _get_user(db, user_id)
            if not row:
                raise Exception(f"User {user_id} not found")

            prefs = dict(row.notification_preferences or {})
            for key, value in (
                ("new_episodes", new_episodes),
                ("stock_mentions", stock_mentions),
                ("price_alerts", price_alerts),
                ("daily_digest", daily_digest),
            ):
                if value is not None:
                    prefs[key] = value

            row.notification_preferences = prefs
            row.updated_at = datetime.now(timezone.utc)
            return _to_preferences(prefs)
    except Exception as e:
        raise Exception(f"Failed to update notification preferences: {e}") from e


def get_notification_preferences(user_id: str) -> NotificationPreferences:
    """Get notification preferences for a user"""
    try:
        with session_scope() as db:
            row = _get_user(db, user_id)
            if not row:
                return NotificationPreferences()
            return _to_preferences(row.notification_preferences or {})
    except Exception as e:
        raise Exception(f"Failed to get notification preferences: {e}") from e
