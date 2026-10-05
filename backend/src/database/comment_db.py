"""
Episode comment storage (ORM — Postgres when deployed, SQLite for a local checkout).
"""
import uuid
from typing import Optional
from datetime import datetime, timezone
from src.database.models import EpisodeComment
from src.database.postgres import session_scope


def _to_dict(row: EpisodeComment) -> dict:
    return {
        "id": row.id,
        "podcast_name": row.podcast_name,
        "episode_id": row.episode_id,
        "user_id": row.user_id,
        "user_name": row.user_name,
        "user_avatar": row.user_avatar,
        "content": row.content,
        "created_at": row.created_at,
        "parent_comment_id": row.parent_comment_id,
        "depth": row.depth,
        "is_public": bool(row.is_public),
    }


def create_comment(
    podcast_name: str,
    episode_id: str,
    user_id: str,
    user_name: str,
    user_avatar: Optional[str],
    content: str,
    parent_comment_id: Optional[str] = None,
    depth: int = 0,
    is_public: bool = True,
) -> dict:
    row = EpisodeComment(
        id=str(uuid.uuid4()),
        podcast_name=podcast_name,
        episode_id=episode_id,
        user_id=user_id,
        user_name=user_name,
        user_avatar=user_avatar,
        content=content,
        created_at=datetime.now(timezone.utc).isoformat(),
        parent_comment_id=parent_comment_id,
        depth=depth,
        is_public=is_public,
    )
    out = _to_dict(row)
    with session_scope() as db:
        db.add(row)
    return out


def get_comments(
    podcast_name: str,
    episode_id: str,
    viewer_id: Optional[str] = None,
    is_admin: bool = False,
) -> list[dict]:
    """Return comments for an episode (flat, oldest-first) for client-side tree building.

    Private comments are only returned to their author or an admin.
    """
    with session_scope() as db:
        rows = (
            db.query(EpisodeComment)
            .filter(EpisodeComment.podcast_name == podcast_name,
                    EpisodeComment.episode_id == episode_id)
            .order_by(EpisodeComment.created_at.asc())
            .all()
        )
        return [
            _to_dict(r) for r in rows
            if r.is_public or is_admin or r.user_id == viewer_id
        ]


def get_comment_by_id(comment_id: str) -> Optional[dict]:
    with session_scope() as db:
        row = db.get(EpisodeComment, comment_id)
        return _to_dict(row) if row else None


def delete_comment(comment_id: str) -> bool:
    with session_scope() as db:
        return db.query(EpisodeComment).filter(EpisodeComment.id == comment_id).delete() > 0
