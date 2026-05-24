"""
Comment endpoints for podcast episodes.
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, field_validator
from src.utils.dependencies import get_current_user
from src.models.user import UserResponse
from src.database.comment_db import create_comment, get_comments, get_comment_by_id, delete_comment

logger = logging.getLogger(__name__)

MAX_DEPTH = 5

router = APIRouter(prefix="/api/episodes", tags=["comments"])


class CommentCreate(BaseModel):
    content: str
    parent_comment_id: Optional[str] = None

    @field_validator("content")
    @classmethod
    def validate_content(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Comment cannot be empty")
        if len(v) > 500:
            raise ValueError("Comment cannot exceed 500 characters")
        return v


@router.get("/{podcast_name}/{episode_id}/comments")
async def list_comments(podcast_name: str, episode_id: str):
    """List all comments for an episode as a flat list (public)."""
    try:
        comments = get_comments(podcast_name, episode_id)
        return {"comments": comments, "total": len(comments)}
    except Exception as e:
        logger.error(f"Failed to fetch comments for {podcast_name}/{episode_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch comments")


@router.post("/{podcast_name}/{episode_id}/comments", status_code=201)
async def post_comment(
    podcast_name: str,
    episode_id: str,
    body: CommentCreate,
    user: UserResponse = Depends(get_current_user),
):
    """Post a comment or reply on an episode (requires authentication)."""
    depth = 0
    if body.parent_comment_id:
        parent = get_comment_by_id(body.parent_comment_id)
        if not parent:
            raise HTTPException(status_code=404, detail="Parent comment not found")
        if parent["depth"] >= MAX_DEPTH:
            raise HTTPException(status_code=400, detail="Maximum reply depth reached")
        depth = parent["depth"] + 1

    try:
        comment = create_comment(
            podcast_name=podcast_name,
            episode_id=episode_id,
            user_id=user.id,
            user_name=user.name,
            user_avatar=user.avatar,
            content=body.content,
            parent_comment_id=body.parent_comment_id,
            depth=depth,
        )
        return comment
    except Exception as e:
        logger.error(f"Failed to create comment for {podcast_name}/{episode_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to create comment")


# Separate router for comment-level operations (delete by ID)
comments_router = APIRouter(prefix="/api/comments", tags=["comments"])


@comments_router.delete("/{comment_id}", status_code=204)
async def delete_comment_endpoint(
    comment_id: str,
    user: UserResponse = Depends(get_current_user),
):
    """Delete a comment (only the comment owner can delete their own comment)."""
    comment = get_comment_by_id(comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment["user_id"] != user.id:
        raise HTTPException(status_code=403, detail="You can only delete your own comments")
    deleted = delete_comment(comment_id)
    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete comment")
