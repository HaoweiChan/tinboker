"""
Comment database operations using SQLite/PostgreSQL.
"""
import uuid
from typing import Optional
from datetime import datetime, timezone
from src.database.db import get_connection


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
    conn = get_connection()
    try:
        comment_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO comments
              (id, podcast_name, episode_id, user_id, user_name, user_avatar,
               content, created_at, parent_comment_id, depth, is_public)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (comment_id, podcast_name, episode_id, user_id, user_name, user_avatar,
             content, created_at, parent_comment_id, depth, int(is_public)),
        )
        conn.commit()
        return {
            "id": comment_id,
            "podcast_name": podcast_name,
            "episode_id": episode_id,
            "user_id": user_id,
            "user_name": user_name,
            "user_avatar": user_avatar,
            "content": content,
            "created_at": created_at,
            "parent_comment_id": parent_comment_id,
            "depth": depth,
            "is_public": is_public,
        }
    finally:
        conn.close()


def get_comments(
    podcast_name: str,
    episode_id: str,
    viewer_id: Optional[str] = None,
    is_admin: bool = False,
) -> list[dict]:
    """Return comments for an episode (flat, oldest-first) for client-side tree building.

    Private comments (is_public=0) are only returned to their author or an admin.
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, podcast_name, episode_id, user_id, user_name, user_avatar,
                   content, created_at, parent_comment_id, depth, is_public
            FROM comments
            WHERE podcast_name = ? AND episode_id = ?
            ORDER BY created_at ASC
            """,
            (podcast_name, episode_id),
        ).fetchall()
        out = []
        for row in rows:
            c = dict(row)
            c["is_public"] = bool(c["is_public"])
            if c["is_public"] or is_admin or c["user_id"] == viewer_id:
                out.append(c)
        return out
    finally:
        conn.close()


def get_comment_by_id(comment_id: str) -> Optional[dict]:
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT id, podcast_name, episode_id, user_id, user_name, user_avatar,
                   content, created_at, parent_comment_id, depth
            FROM comments WHERE id = ?
            """,
            (comment_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_comment(comment_id: str) -> bool:
    conn = get_connection()
    try:
        cursor = conn.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()
