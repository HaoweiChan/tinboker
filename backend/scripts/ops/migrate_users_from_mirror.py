#!/usr/bin/env python3
"""One-time: copy `firestore_mirror.users` into the backend's own `users` table (P3).

The mirror table already holds every Firestore user document verbatim
(`doc jsonb`, written by pipelines' dump_firestore_to_postgres.py), and the backend
connects to that same database — so this reads Postgres only. No Firestore client,
no GCP egress.

Insert-only and re-runnable: rows that already exist in `users` are left alone, so a
second run after the cutover cannot clobber live edits.

NOT migrated: `users/{id}/notifications` — the subcollection was never mirrored
(dump_firestore_to_postgres.py copies top-level collections only), so members start
with an empty inbox. New notifications are produced within ~10 min by the poller.

Usage (on the VPS, inside the backend container or with POSTGRES_* set):
    python scripts/ops/migrate_users_from_mirror.py --dry-run   # preview
    python scripts/ops/migrate_users_from_mirror.py             # apply
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# scripts/ops/ -> backend/
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text  # noqa: E402

from src.database.models import User  # noqa: E402
from src.database.postgres import create_all_tables, session_scope  # noqa: E402

MIRROR_TABLE = "firestore_mirror.users"

ARRAY_FIELDS = (
    "watchlist",
    "podcast_subscriptions",
    "episode_bookmarks",
    "alerts",
    "tag_subscriptions",
)


def _parse_dt(value) -> datetime | None:
    """Mirror docs store Firestore timestamps as ISO strings (see _jsonable)."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    return None


def user_fields(doc_id: str, doc: dict) -> dict:
    """Mirror document -> `users` column values. Pure; this is the tested part.

    Raises ValueError when the document can't back a usable account — both lookups
    the auth path makes (by google_id at login, by email on every request) need
    their key present.
    """
    doc = doc or {}
    google_id = doc.get("google_id")
    email = doc.get("email")
    if not google_id:
        raise ValueError("missing google_id")
    if not email:
        raise ValueError("missing email")

    now = datetime.now(timezone.utc)
    fields = {
        "id": doc.get("id") or doc_id,
        "google_id": str(google_id),
        "email": str(email),
        "name": doc.get("name") or "",
        "avatar": doc.get("avatar") or "",
        "email_verified": bool(doc.get("email_verified", False)),
        "created_at": _parse_dt(doc.get("created_at")) or now,
        "updated_at": _parse_dt(doc.get("updated_at")) or now,
        "notification_preferences": doc.get("notification_preferences") or {},
    }
    for field in ARRAY_FIELDS:
        value = doc.get(field)
        fields[field] = [v for v in value if isinstance(v, str)] if isinstance(value, list) else []
    return fields


def migrate(dry_run: bool = False) -> tuple[int, int, list[str]]:
    """Returns (inserted, skipped_existing, [problem descriptions])."""
    inserted = skipped = 0
    problems: list[str] = []

    with session_scope() as db:
        rows = db.execute(text(f"SELECT id, doc FROM {MIRROR_TABLE}")).all()
        present = db.query(User.id, User.google_id).all()
        existing = {row[0] for row in present}
        # google_id is unique — track the ones already stored too, or a re-run would
        # try to insert a second row for a user whose doc id changed.
        seen_google_ids = {row[1] for row in present}

        for doc_id, doc in rows:
            try:
                # psycopg hands back jsonb as a dict; other drivers hand back text.
                fields = user_fields(doc_id, json.loads(doc) if isinstance(doc, str) else doc)
            except ValueError as e:
                problems.append(f"{doc_id}: {e}")
                continue
            if fields["id"] in existing:
                skipped += 1
                continue
            if fields["google_id"] in seen_google_ids:
                problems.append(f"{doc_id}: duplicate google_id, skipped")
                continue
            seen_google_ids.add(fields["google_id"])
            if not dry_run:
                db.add(User(**fields))
            inserted += 1

    return inserted, skipped, problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    args = parser.parse_args()

    if not args.dry_run:
        create_all_tables()  # idempotent; makes sure users/user_notifications exist

    inserted, skipped, problems = migrate(dry_run=args.dry_run)

    print(f"{'[dry-run] ' if args.dry_run else ''}inserted {inserted}, "
          f"already present {skipped}, problems {len(problems)}")
    for p in problems:
        print(f"  ! {p}")
    print("note: notification history is not migrated — the mirror has no "
          "users/{id}/notifications; inboxes start empty.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
