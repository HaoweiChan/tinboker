"""
User database operations using Firestore
"""
import uuid
from typing import Dict, Optional
from datetime import datetime, timezone
from src.services.firestore_service import FirestoreService
from src.models.user import UserCreate, UserResponse, NotificationPreferences

# Import Firestore for array operations
try:
    from firebase_admin import firestore
    FIRESTORE_AVAILABLE = True
except ImportError:
    firestore = None
    FIRESTORE_AVAILABLE = False

# Initialize Firestore service (singleton pattern)
_firestore_service = None

MERGED_SECTOR_TAG_SUBSCRIPTION_RENAMES = {
    "日本矽晶圓": "矽晶圓",
    "日本前段設備": "前段製程設備",
    "日本後段設備": "封裝製程機台",
    "日本被動元件": "被動元件 MLCC",
}

def _get_firestore_service() -> FirestoreService:
    """Get or create FirestoreService instance"""
    global _firestore_service
    if _firestore_service is None:
        _firestore_service = FirestoreService()
    return _firestore_service


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
    firestore_service = _get_firestore_service()
    migrated = 0
    now = datetime.now(timezone.utc)
    for user_doc in firestore_service.get_all_documents("users"):
        user_id = user_doc.get("id")
        current = user_doc.get("tag_subscriptions", [])
        if not user_id or not isinstance(current, list):
            continue
        remapped = remap_merged_sector_tag_subscriptions(current)
        if remapped == current:
            continue
        firestore_service.set_document(
            "users",
            user_id,
            {"tag_subscriptions": remapped, "updated_at": now},
            merge=True,
        )
        migrated += 1
    return migrated


def _firestore_timestamp_to_datetime(timestamp) -> datetime:
    """Convert Firestore Timestamp to Python datetime"""
    if timestamp is None:
        return None
    
    # Firestore Timestamp object
    if hasattr(timestamp, 'to_datetime'):
        return timestamp.to_datetime()
    
    # Already a datetime
    if isinstance(timestamp, datetime):
        return timestamp
    
    # String format
    if isinstance(timestamp, str):
        try:
            return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        except ValueError:
            # Try parsing as timestamp
            try:
                return datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
            except (ValueError, TypeError):
                return datetime.now(timezone.utc)
    
    # Numeric timestamp
    try:
        return datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def _dict_to_user_response(data: dict) -> UserResponse:
    """Convert Firestore document dictionary to UserResponse"""
    # Parse notification preferences
    prefs_data = data.get('notification_preferences', {})
    notification_prefs = NotificationPreferences(
        new_episodes=prefs_data.get('new_episodes', True),
        stock_mentions=prefs_data.get('stock_mentions', True),
        price_alerts=prefs_data.get('price_alerts', True),
        daily_digest=prefs_data.get('daily_digest', False)
    )
    return UserResponse(
        id=data.get('id', ''),
        google_id=data.get('google_id', ''),
        email=data.get('email', ''),
        name=data.get('name', ''),
        avatar=data.get('avatar'),
        email_verified=data.get('email_verified', False),
        created_at=_firestore_timestamp_to_datetime(data.get('created_at')),
        updated_at=_firestore_timestamp_to_datetime(data.get('updated_at')),
        # Subscription fields (default to empty lists if not present)
        watchlist=data.get('watchlist', []),
        podcast_subscriptions=data.get('podcast_subscriptions', []),
        episode_bookmarks=data.get('episode_bookmarks', []),
        alerts=data.get('alerts', []),
        tag_subscriptions=data.get('tag_subscriptions', []),
        # Notification preferences
        notification_preferences=notification_prefs
    )


def get_user_by_google_id(google_id: str) -> Optional[UserResponse]:
    """Get user by Google ID"""
    firestore = _get_firestore_service()
    
    try:
        users = firestore.query_collection(
            "users",
            filters=[("google_id", "==", google_id)],
            limit=1
        )
        
        if users:
            return _dict_to_user_response(users[0])
        return None
    except Exception as e:
        raise Exception(f"Failed to get user by Google ID: {e}") from e


def get_user_by_email(email: str) -> Optional[UserResponse]:
    """Get user by email"""
    firestore = _get_firestore_service()
    
    try:
        users = firestore.query_collection(
            "users",
            filters=[("email", "==", email)],
            limit=1
        )
        
        if users:
            return _dict_to_user_response(users[0])
        return None
    except Exception as e:
        raise Exception(f"Failed to get user by email: {e}") from e


def create_user(user_data: UserCreate) -> UserResponse:
    """Create a new user"""
    firestore = _get_firestore_service()
    
    try:
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        user_doc = {
            "id": user_id,
            "google_id": user_data.google_id,
            "email": user_data.email,
            "name": user_data.name,
            "avatar": user_data.avatar or "",
            "email_verified": False,  # Will be set from Google token
            "created_at": now,
            "updated_at": now
        }
        
        # Use user_id as document ID
        firestore.set_document("users", user_id, user_doc)
        
        # Return the created user
        return get_user_by_google_id(user_data.google_id)
    except Exception as e:
        raise Exception(f"Failed to create user: {e}") from e


def update_user(google_id: str, name: Optional[str] = None, avatar: Optional[str] = None, email_verified: Optional[bool] = None) -> Optional[UserResponse]:
    """Update user information"""
    # First, get the user to find their document ID
    user = get_user_by_google_id(google_id)
    if not user:
        return None
    
    firestore = _get_firestore_service()
    
    try:
        updates = {}
        
        if name is not None:
            updates["name"] = name
        
        if avatar is not None:
            updates["avatar"] = avatar
        
        if email_verified is not None:
            updates["email_verified"] = email_verified
        
        if not updates:
            return user
        
        updates["updated_at"] = datetime.now(timezone.utc)
        
        # Update using user.id as document ID
        firestore.set_document("users", user.id, updates, merge=True)
        
        # Return updated user
        return get_user_by_google_id(google_id)
    except Exception as e:
        raise Exception(f"Failed to update user: {e}") from e


def get_or_create_user(google_id: str, email: str, name: str, avatar: Optional[str] = None, email_verified: bool = False) -> UserResponse:
    """Get existing user or create new one"""
    user = get_user_by_google_id(google_id)
    
    if user:
        # Update user info if changed
        updated_user = update_user(
            google_id,
            name=name if name != user.name else None,
            avatar=avatar if avatar != user.avatar else None,
            email_verified=email_verified if email_verified != user.email_verified else None
        )
        return updated_user or user
    
    # Create new user
    user_data = UserCreate(
        google_id=google_id,
        email=email,
        name=name,
        avatar=avatar
    )
    created_user = create_user(user_data)
    
    # Update email_verified if needed
    if email_verified:
        return update_user(google_id, email_verified=email_verified) or created_user
    
    return created_user


def get_user_subscriptions(user_id: str) -> Dict[str, list]:
    """Get all subscriptions for a user"""
    firestore_service = _get_firestore_service()
    
    try:
        user_doc = firestore_service.get_document("users", user_id)
        if not user_doc:
            return {
                "watchlist": [],
                "podcast_subscriptions": [],
                "episode_bookmarks": [],
                "alerts": [],
                "tag_subscriptions": []
            }
        
        return {
            "watchlist": user_doc.get("watchlist", []),
            "podcast_subscriptions": user_doc.get("podcast_subscriptions", []),
            "episode_bookmarks": user_doc.get("episode_bookmarks", []),
            "alerts": user_doc.get("alerts", []),
            "tag_subscriptions": user_doc.get("tag_subscriptions", [])
        }
    except Exception as e:
        raise Exception(f"Failed to get user subscriptions: {e}") from e


def _update_array_field(user_id: str, field_name: str, value: str, operation: str) -> bool:
    """Update an array field in user document (add or remove item)"""
    if not FIRESTORE_AVAILABLE:
        raise ImportError("firebase-admin is required for array operations")
    
    firestore_service = _get_firestore_service()
    
    try:
        doc_ref = firestore_service.db.collection("users").document(user_id)
        
        if operation == "add":
            doc_ref.update({
                field_name: firestore.ArrayUnion([value]),
                "updated_at": datetime.now(timezone.utc)
            })
        elif operation == "remove":
            doc_ref.update({
                field_name: firestore.ArrayRemove([value]),
                "updated_at": datetime.now(timezone.utc)
            })
        else:
            raise ValueError(f"Invalid operation: {operation}")
        
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
    watchlist = subscriptions.get("watchlist", [])
    is_in_watchlist = ticker in watchlist
    
    if is_in_watchlist:
        remove_from_watchlist(user_id, ticker)
        return {"ticker": ticker, "is_in_watchlist": False}
    else:
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
    podcast_subscriptions = subscriptions.get("podcast_subscriptions", [])
    is_subscribed = podcast_name in podcast_subscriptions
    
    if is_subscribed:
        remove_podcast_subscription(user_id, podcast_name)
        return {"podcast_name": podcast_name, "is_subscribed": False}
    else:
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
    episode_bookmarks = subscriptions.get("episode_bookmarks", [])
    is_bookmarked = episode_id in episode_bookmarks
    
    if is_bookmarked:
        remove_episode_bookmark(user_id, episode_id)
        return {"episode_id": episode_id, "is_bookmarked": False}
    else:
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
    tag_subscriptions = subscriptions.get("tag_subscriptions", [])
    is_subscribed = tag_name in tag_subscriptions
    if is_subscribed:
        remove_tag_subscription(user_id, tag_name)
        return {"tag_name": tag_name, "is_subscribed": False}
    else:
        add_tag_subscription(user_id, tag_name)
        return {"tag_name": tag_name, "is_subscribed": True}


def update_notification_preferences(
    user_id: str,
    new_episodes: Optional[bool] = None,
    stock_mentions: Optional[bool] = None,
    price_alerts: Optional[bool] = None,
    daily_digest: Optional[bool] = None
) -> NotificationPreferences:
    """Update notification preferences for a user"""
    firestore_service = _get_firestore_service()
    try:
        # Get current preferences
        user_doc = firestore_service.get_document("users", user_id)
        if not user_doc:
            raise Exception(f"User {user_id} not found")
        current_prefs = user_doc.get("notification_preferences", {})
        # Update only provided fields
        if new_episodes is not None:
            current_prefs["new_episodes"] = new_episodes
        if stock_mentions is not None:
            current_prefs["stock_mentions"] = stock_mentions
        if price_alerts is not None:
            current_prefs["price_alerts"] = price_alerts
        if daily_digest is not None:
            current_prefs["daily_digest"] = daily_digest
        # Save to Firestore
        firestore_service.set_document("users", user_id, {
            "notification_preferences": current_prefs,
            "updated_at": datetime.now(timezone.utc)
        }, merge=True)
        return NotificationPreferences(
            new_episodes=current_prefs.get("new_episodes", True),
            stock_mentions=current_prefs.get("stock_mentions", True),
            price_alerts=current_prefs.get("price_alerts", True),
            daily_digest=current_prefs.get("daily_digest", False)
        )
    except Exception as e:
        raise Exception(f"Failed to update notification preferences: {e}") from e


def get_notification_preferences(user_id: str) -> NotificationPreferences:
    """Get notification preferences for a user"""
    firestore_service = _get_firestore_service()
    try:
        user_doc = firestore_service.get_document("users", user_id)
        if not user_doc:
            return NotificationPreferences()
        prefs_data = user_doc.get("notification_preferences", {})
        return NotificationPreferences(
            new_episodes=prefs_data.get("new_episodes", True),
            stock_mentions=prefs_data.get("stock_mentions", True),
            price_alerts=prefs_data.get("price_alerts", True),
            daily_digest=prefs_data.get("daily_digest", False)
        )
    except Exception as e:
        raise Exception(f"Failed to get notification preferences: {e}") from e
