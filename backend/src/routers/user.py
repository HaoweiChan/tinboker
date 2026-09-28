"""
User-specific routes for subscriptions and preferences
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from src.models.user import UserResponse, NotificationPreferences, UpdateNotificationPreferencesRequest, UpdateProfileRequest
from src.utils.dependencies import get_current_user
from src.database.user_db import (
    get_user_subscriptions,
    toggle_watchlist,
    toggle_podcast_subscription,
    toggle_episode_bookmark,
    toggle_tag_subscription,
    toggle_dismissed_pick,
    update_notification_preferences,
    get_notification_preferences,
    update_user,
)

router = APIRouter(prefix="/api/user", tags=["user"])


class DismissPickRequest(BaseModel):
    """One pick to hide in 走勢, as "{episode_id}|{ticker}"."""
    pick_key: str = Field(min_length=1, max_length=200)


@router.patch("/me", response_model=UserResponse)
async def update_my_profile(
    req: UpdateProfileRequest,
    user: UserResponse = Depends(get_current_user),
):
    """Update the current user's display name and/or avatar. Both fields are optional;
    omitted fields are left unchanged. New comments pick up the new identity; existing
    comments keep the snapshot taken when they were posted."""
    name = req.name.strip() if req.name is not None else None
    if name is not None and not (1 <= len(name) <= 40):
        raise HTTPException(status_code=400, detail="名稱長度需為 1–40 字")

    avatar = req.avatar
    if avatar is not None:
        avatar = avatar.strip()
        # Only allow https URLs or inline image data URIs — never javascript:/other schemes.
        if avatar and not (avatar.startswith("https://") or avatar.startswith("data:image/")):
            raise HTTPException(status_code=400, detail="頭像格式不支援")
        # ~300KB cap on the data URI — the client resizes to a small square before sending.
        if len(avatar) > 400_000:
            raise HTTPException(status_code=400, detail="頭像檔案過大")

    if name is None and avatar is None:
        return user

    updated = update_user(user.google_id, name=name, avatar=avatar)
    if not updated:
        raise HTTPException(status_code=404, detail="User not found")
    return updated


@router.get("/watchlist")
async def get_watchlist(user: UserResponse = Depends(get_current_user)):
    """Get user's watchlist"""
    subscriptions = get_user_subscriptions(user.id)
    return {"watchlist": subscriptions.get("watchlist", [])}


@router.post("/watchlist/{ticker}/toggle")
async def toggle_watchlist_item(
    ticker: str,
    user: UserResponse = Depends(get_current_user)
):
    """Toggle watchlist item"""
    try:
        result = toggle_watchlist(user.id, ticker)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to toggle watchlist: {str(e)}"
        )


@router.get("/subscriptions/podcasts")
async def get_podcast_subscriptions(user: UserResponse = Depends(get_current_user)):
    """Get subscribed podcasters"""
    subscriptions = get_user_subscriptions(user.id)
    return {"podcasts": subscriptions.get("podcast_subscriptions", [])}


@router.post("/subscriptions/podcasts/{podcast_name}/toggle")
async def toggle_podcast_subscription_item(
    podcast_name: str,
    user: UserResponse = Depends(get_current_user)
):
    """Toggle podcast subscription"""
    try:
        # Decode URL-encoded podcast name
        from urllib.parse import unquote
        decoded_name = unquote(podcast_name)
        result = toggle_podcast_subscription(user.id, decoded_name)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to toggle podcast subscription: {str(e)}"
        )


@router.get("/subscriptions/episodes")
async def get_episode_bookmarks(user: UserResponse = Depends(get_current_user)):
    """Get bookmarked episodes"""
    subscriptions = get_user_subscriptions(user.id)
    return {"episodes": subscriptions.get("episode_bookmarks", [])}


@router.post("/subscriptions/episodes/toggle")
async def toggle_episode_bookmark_item(
    request: dict,
    user: UserResponse = Depends(get_current_user)
):
    """Toggle episode bookmark"""
    podcast_name = request.get("podcast_name")
    episode_id = request.get("episode_id")
    
    if not podcast_name or not episode_id:
        raise HTTPException(
            status_code=400,
            detail="podcast_name and episode_id are required"
        )
    
    try:
        # Format: "{podcast_name}_{episode_id}"
        formatted_id = f"{podcast_name}_{episode_id}"
        result = toggle_episode_bookmark(user.id, formatted_id)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to toggle episode bookmark: {str(e)}"
        )


@router.post("/dismissed-picks/toggle")
async def toggle_dismissed_pick_item(
    req: DismissPickRequest,
    user: UserResponse = Depends(get_current_user),
):
    """Hide (or restore) one pick in 走勢.

    The key is in the body, not the path: it carries an episode id and a ticker joined
    by "|", and episode ids are long enough that a path segment invites encoding bugs.
    """
    try:
        return toggle_dismissed_pick(user.id, req.pick_key)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to toggle dismissed pick: {str(e)}")


@router.get("/subscriptions/tags")
async def get_tag_subscriptions(user: UserResponse = Depends(get_current_user)):
    """Get subscribed tags"""
    subscriptions = get_user_subscriptions(user.id)
    return {"tags": subscriptions.get("tag_subscriptions", [])}


@router.post("/subscriptions/tags/{tag_name}/toggle")
async def toggle_tag_subscription_item(
    tag_name: str,
    user: UserResponse = Depends(get_current_user)
):
    """Toggle tag subscription"""
    try:
        # Decode URL-encoded tag name
        from urllib.parse import unquote
        decoded_name = unquote(tag_name)
        result = toggle_tag_subscription(user.id, decoded_name)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to toggle tag subscription: {str(e)}"
        )


@router.get("/notification-preferences", response_model=NotificationPreferences)
async def get_user_notification_preferences(
    user: UserResponse = Depends(get_current_user)
):
    """Get user's notification preferences"""
    try:
        return get_notification_preferences(user.id)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get notification preferences: {str(e)}"
        )


@router.put("/notification-preferences", response_model=NotificationPreferences)
async def update_user_notification_preferences(
    request: UpdateNotificationPreferencesRequest,
    user: UserResponse = Depends(get_current_user)
):
    """Update user's notification preferences"""
    try:
        return update_notification_preferences(
            user_id=user.id,
            new_episodes=request.new_episodes,
            stock_mentions=request.stock_mentions,
            price_alerts=request.price_alerts,
            daily_digest=request.daily_digest
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update notification preferences: {str(e)}"
        )

