#!/usr/bin/env python3
"""One-time: copy `firestore_mirror.users` into the backend's own `users` table (P3).

The mirror table already holds every Firestore user document verbatim
(`doc jsonb`, written by pipelines' dump_firestore_to_postgres.py), and the backend
connects to that same database — so this reads Postgres only. No Firestore client,
no GCP egress.

ORDERING — RUN THIS IMMEDIATELY AFTER THE DEPLOY, BEFORE ANYONE SIGNS IN.
The deploy creates an EMPTY `users` table at boot. Any member who signs in during
the gap gets a brand-new row (fresh uuid, empty arrays) for their google_id, and
their watchlist / subscriptions / bookmarks / preferences are then only in the
mirror. So: deploy -> run this -> announce. Keep the window to minutes.

Adoption closes that race for anyone who slipped through: when a mirror document's
google_id already has a live row, the mirror's subscription arrays and preferences
are merged INTO that row for every field the live row left empty. Live values
always win — a non-empty live field is never overwritten — so this is safe to run
late, and safe to re-run. Adopted rows are reported separately.

Rows are matched on google_id, not document id, precisely because the racing
sign-in mints a different id for the same person.

NOT migrated: `users/{id}/notifications` — the subcollection was never mirrored
(dump_firestore_to_postgres.py copies top-level collections only), so members start
with an empty inbox. New notifications are produced within ~10 min by the poller.
Also not adopted: `created_at` (a raced row dates from the sign-in, which skews the
admin signup-growth chart only, and the mirror keeps the original indefinitely).

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

# The member-owned fields a racing sign-in would have left empty. Identity fields
# (name/email/avatar/email_verified) are deliberately excluded: the sign-in wrote
# fresher Google values than the mirror holds.
ADOPT_FIELDS = ARRAY_FIELDS + ("notification_preferences",)


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


def adoptable_fields(live: dict, mirror: dict) -> dict:
    """Mirror values for the fields a live row never populated. Pure; the tested part.

    A field is adoptable only when the live side is empty/absent AND the mirror has
    something to give — so a live edit is never overwritten and an empty-over-empty
    write is never issued.
    """
    return {
        field: mirror[field]
        for field in ADOPT_FIELDS
        if not live.get(field) and mirror.get(field)
    }


def migrate(dry_run: bool = False) -> tuple[int, int, int, list[str]]:
    """Returns (inserted, adopted, skipped_unchanged, [problem descriptions])."""
    inserted = adopted = skipped = 0
    problems: list[str] = []

    with session_scope() as db:
        rows = db.execute(text(f"SELECT id, doc FROM {MIRROR_TABLE}")).all()
        # ~40 rows — load the entities so adoption can write straight back.
        live = {row.google_id: row for row in db.query(User).all()}
        # Two mirror documents for one Google account is a data anomaly; report it the
        # same way on every run, whether the first one landed as an insert or an adopt.
        seen_google_ids: set[str] = set()

        for doc_id, doc in rows:
            try:
                # psycopg hands back jsonb as a dict; other drivers hand back text.
                fields = user_fields(doc_id, json.loads(doc) if isinstance(doc, str) else doc)
            except ValueError as e:
                problems.append(f"{doc_id}: {e}")
                continue

            google_id = fields["google_id"]
            if google_id in seen_google_ids:
                problems.append(f"{doc_id}: duplicate google_id, skipped")
                continue
            seen_google_ids.add(google_id)

            row = live.get(google_id)
            if row is not None:
                # Already present — either a plain re-run, or a member who signed in
                # before this script ran and got an empty row. Fill the gaps only.
                changes = adoptable_fields(
                    {f: getattr(row, f) for f in ADOPT_FIELDS}, fields
                )
                if not changes:
                    skipped += 1
                    continue
                if not dry_run:
                    for field, value in changes.items():
                        setattr(row, field, value)
                    row.updated_at = datetime.now(timezone.utc)
                adopted += 1
                continue

            if not dry_run:
                db.add(User(**fields))
            inserted += 1

    return inserted, adopted, skipped, problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    args = parser.parse_args()

    if not args.dry_run:
        create_all_tables()  # idempotent; makes sure users/user_notifications exist

    inserted, adopted, skipped, problems = migrate(dry_run=args.dry_run)

    print(f"{'[dry-run] ' if args.dry_run else ''}inserted {inserted}, "
          f"adopted {adopted}, unchanged {skipped}, problems {len(problems)}")
    if adopted:
        print(f"  {adopted} member(s) had signed in before this ran — their mirrored "
              f"subscriptions were merged into the row the sign-in created.")
    for p in problems:
        print(f"  ! {p}")
    print("note: notification history is not migrated — the mirror has no "
          "users/{id}/notifications; inboxes start empty.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
