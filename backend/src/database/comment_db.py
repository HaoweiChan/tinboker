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
) -> dict:
    conn = get_connection()
    try:
        comment_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO comments
              (id, podcast_name, episode_id, user_id, user_name, user_avatar,
               content, created_at, parent_comment_id, depth)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (comment_id, podcast_name, episode_id, user_id, user_name, user_avatar,
             content, created_at, parent_comment_id, depth),
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
        }
    finally:
        conn.close()


def get_comments(podcast_name: str, episode_id: str) -> list[dict]:
    """Return all comments for an episode (flat, oldest-first) for client-side tree building."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT id, podcast_name, episode_id, user_id, user_name, user_avatar,
                   content, created_at, parent_comment_id, depth
            FROM comments
            WHERE podcast_name = ? AND episode_id = ?
            ORDER BY created_at ASC
            """,
            (podcast_name, episode_id),
        ).fetchall()
        return [dict(row) for row in rows]
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
