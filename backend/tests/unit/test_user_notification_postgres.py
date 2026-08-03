"""P3: users + notifications live in Postgres/SQLite tables, not Firestore.

Exercises the real SQL through the ``orm_db`` fixture (in-memory SQLite), so a
regression in the ORM data layer fails here rather than in production.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event

from src.database import notification_db as ndb
from src.database import user_db
from src.models.notification import NotificationCreate, NotificationType
from src.models.user import UserCreate
from scripts.ops.migrate_users_from_mirror import migrate, user_fields


def _make_user(email="a@example.com", google_id="g-1", name="Aki"):
    return user_db.create_user(UserCreate(google_id=google_id, email=email, name=name))


# --------------------------------------------------------------------------- users


def test_create_and_lookup_by_google_id_and_email(orm_db):
    created = _make_user()
    assert created.id and created.watchlist == [] and created.email_verified is False
    assert created.notification_preferences.new_episodes is True

    assert user_db.get_user_by_google_id("g-1").id == created.id
    assert user_db.get_user_by_email("a@example.com").id == created.id
    assert user_db.get_user_by_google_id("nope") is None
    assert user_db.get_user_by_email("nope@example.com") is None


def test_get_or_create_user_is_idempotent_and_updates_changed_fields(orm_db):
    first = user_db.get_or_create_user("g-1", "a@example.com", "Aki", email_verified=True)
    assert first.email_verified is True

    again = user_db.get_or_create_user(
        "g-1", "a@example.com", "Aki Renamed", avatar="https://x/y.png", email_verified=True
    )
    assert again.id == first.id  # no duplicate row
    assert again.name == "Aki Renamed"
    assert again.avatar == "https://x/y.png"
    assert again.email_verified is True

    # Pre-existing semantics kept from the Firestore version: the flag tracks whatever
    # the current Google token says, so a sign-in without it downgrades the row.
    assert user_db.get_or_create_user("g-1", "a@example.com", "Aki Renamed").email_verified is False


def test_update_user_returns_none_for_unknown_google_id(orm_db):
    assert user_db.update_user("ghost", name="x") is None


def test_get_user_subscriptions_of_unknown_user_is_all_empty(orm_db):
    assert user_db.get_user_subscriptions("ghost") == {
        "watchlist": [],
        "podcast_subscriptions": [],
        "episode_bookmarks": [],
        "alerts": [],
        "tag_subscriptions": [],
    }


@pytest.mark.parametrize(
    "toggle,field,value,on_key",
    [
        (user_db.toggle_watchlist, "watchlist", "2330", "is_in_watchlist"),
        (user_db.toggle_podcast_subscription, "podcast_subscriptions", "股癌", "is_subscribed"),
        (user_db.toggle_episode_bookmark, "episode_bookmarks", "股癌_EP677", "is_bookmarked"),
        (user_db.toggle_tag_subscription, "tag_subscriptions", "AI", "is_subscribed"),
    ],
)
def test_array_toggles_round_trip(orm_db, toggle, field, value, on_key):
    user = _make_user()

    assert toggle(user.id, value)[on_key] is True
    assert user_db.get_user_subscriptions(user.id)[field] == [value]

    assert toggle(user.id, value)[on_key] is False
    assert user_db.get_user_subscriptions(user.id)[field] == []


def test_array_add_is_deduped_and_remove_of_absent_is_a_noop(orm_db):
    """ArrayUnion/ArrayRemove semantics the Firestore version provided."""
    user = _make_user()
    user_db.add_to_watchlist(user.id, "2330")
    user_db.add_to_watchlist(user.id, "2330")
    assert user_db.get_user_subscriptions(user.id)["watchlist"] == ["2330"]

    assert user_db.remove_from_watchlist(user.id, "NVDA") is True
    assert user_db.get_user_subscriptions(user.id)["watchlist"] == ["2330"]


def test_array_field_and_operation_are_validated(orm_db):
    user = _make_user()
    with pytest.raises(Exception, match="Invalid array field"):
        user_db._update_array_field(user.id, "email", "x", "add")
    with pytest.raises(Exception, match="Invalid operation"):
        user_db._update_array_field(user.id, "watchlist", "x", "sideways")


def test_notification_preferences_partial_update(orm_db):
    user = _make_user()
    assert user_db.get_notification_preferences(user.id).daily_digest is False

    prefs = user_db.update_notification_preferences(user.id, stock_mentions=False)
    assert prefs.stock_mentions is False and prefs.new_episodes is True

    prefs = user_db.update_notification_preferences(user.id, daily_digest=True)
    assert prefs.daily_digest is True
    assert prefs.stock_mentions is False  # earlier write survives
    assert user_db.get_notification_preferences("ghost").new_episodes is True


def test_merged_sector_tag_migration_runs_against_the_table(orm_db):
    user = _make_user()
    user_db.add_tag_subscription(user.id, "日本前段設備")
    user_db.add_tag_subscription(user.id, "前段製程設備")
    user_db.add_tag_subscription(user.id, "其他")

    assert user_db.migrate_merged_sector_tag_subscriptions() == 1
    assert user_db.get_user_subscriptions(user.id)["tag_subscriptions"] == ["前段製程設備", "其他"]
    # Idempotent: a second run finds nothing to change.
    assert user_db.migrate_merged_sector_tag_subscriptions() == 0


# ------------------------------------------------------------------- notifications


def _notify(user_id, title="t", ntype=NotificationType.NEW_EPISODE):
    return ndb.create_notification(
        NotificationCreate(user_id=user_id, type=ntype, title=title, body="b", data={"k": "v"})
    )


def test_notification_lifecycle(orm_db):
    user = _make_user()
    first = _notify(user.id, "one")
    second = _notify(user.id, "two")

    assert first.is_read is False and first.data == {"k": "v"}
    assert ndb.get_unread_count(user.id) == 2

    items, total, has_more = ndb.get_user_notifications(user.id, limit=50)
    assert total == 2 and has_more is False
    assert {n.id for n in items} == {first.id, second.id}

    assert ndb.mark_notification_as_read(user.id, first.id).is_read is True
    assert ndb.get_unread_count(user.id) == 1
    assert ndb.mark_all_notifications_as_read(user.id) == 1
    assert ndb.get_unread_count(user.id) == 0

    assert ndb.delete_notification(user.id, second.id) is True
    assert ndb.get_notification_by_id(user.id, second.id) is None
    assert ndb.get_user_notifications(user.id)[1] == 1


def test_notifications_are_scoped_to_their_owner(orm_db):
    mine = _make_user(email="a@example.com", google_id="g-1")
    other = _make_user(email="b@example.com", google_id="g-2")
    n = _notify(mine.id)

    assert ndb.get_notification_by_id(other.id, n.id) is None
    assert ndb.mark_notification_as_read(other.id, n.id) is None
    assert ndb.get_unread_count(other.id) == 0
    ndb.delete_notification(other.id, n.id)
    assert ndb.get_notification_by_id(mine.id, n.id) is not None


def test_pagination_reports_has_more_and_newest_first(orm_db):
    user = _make_user()
    for i in range(3):
        _notify(user.id, f"n{i}")

    page, total, has_more = ndb.get_user_notifications(user.id, limit=2, offset=0)
    assert total == 3 and has_more is True and len(page) == 2
    assert page[0].created_at >= page[1].created_at

    page, total, has_more = ndb.get_user_notifications(user.id, limit=2, offset=2)
    assert has_more is False and len(page) == 1


def test_unread_count_is_counted_in_sql_not_by_loading_rows(orm_db):
    """Regression guard: streaming every unread row is what made this endpoint 90s."""
    user = _make_user()
    for _ in range(3):
        _notify(user.id)

    statements: list[str] = []

    def _record(conn, cursor, statement, *rest):
        statements.append(statement)

    event.listen(orm_db, "before_cursor_execute", _record)
    try:
        assert ndb.get_unread_count(user.id) == 3
    finally:
        event.remove(orm_db, "before_cursor_execute", _record)

    assert any("count(" in s.lower() for s in statements), statements
    assert not any("select user_notifications.id, user_notifications.user_id" in s.lower()
                   for s in statements), statements


def test_cleanup_old_notifications_respects_the_cutoff(orm_db):
    from src.database.models import UserNotification
    from src.database.postgres import session_scope

    user = _make_user()
    fresh = _notify(user.id, "fresh")
    stale = _notify(user.id, "stale")
    with session_scope() as db:
        db.query(UserNotification).filter(UserNotification.id == stale.id).update(
            {"created_at": datetime.now(timezone.utc) - timedelta(days=90)}
        )

    assert ndb.cleanup_old_notifications(days=30) == 1
    assert ndb.get_notification_by_id(user.id, fresh.id) is not None
    assert ndb.get_notification_by_id(user.id, stale.id) is None


# ------------------------------------------------------------------------- fan-out


def test_fanout_matches_subscribers_and_honours_preference_toggles(orm_db):
    from src.services import notification_service as svc

    watcher = _make_user(email="w@example.com", google_id="g-w")
    opted_out = _make_user(email="o@example.com", google_id="g-o")
    stranger = _make_user(email="s@example.com", google_id="g-s")

    for user in (watcher, opted_out):
        user_db.add_to_watchlist(user.id, "2330")
        user_db.add_podcast_subscription(user.id, "股癌")
        user_db.add_tag_subscription(user.id, "AI")
    user_db.add_to_watchlist(stranger.id, "NVDA")
    user_db.update_notification_preferences(
        opted_out.id, stock_mentions=False, new_episodes=False
    )

    created = svc.notify_stock_mention("2330", "台積電", "EP1", "股癌")
    assert [n.user_id for n in created] == [watcher.id]
    assert created[0].title.startswith("台積電 (2330)")

    created = svc.notify_new_episode("股癌", "EP1", "標題")
    assert [n.user_id for n in created] == [watcher.id]

    # Tag follows have no toggle — subscribing IS the opt-in, so both are notified.
    created = svc.notify_topic_mention("AI", "EP1", "股癌", "標題")
    assert sorted(n.user_id for n in created) == sorted([watcher.id, opted_out.id])

    # Nobody follows this one.
    assert svc.notify_topic_mention("量子運算", "EP1", "股癌", "標題") == []


def test_fanout_field_whitelist_rejects_anything_else(orm_db):
    from src.services import notification_service as svc

    with pytest.raises(AssertionError):
        svc._subscribers("email", "a@example.com")


# ----------------------------------------------------------------- migration script


def test_user_fields_maps_a_mirror_document():
    doc = {
        "id": "u-1",
        "google_id": "g-1",
        "email": "a@example.com",
        "name": "Aki",
        "avatar": "https://x/y.png",
        "email_verified": True,
        "created_at": "2025-01-02T03:04:05+00:00",
        "updated_at": "2025-06-07T08:09:10Z",
        "watchlist": ["2330", 42, "NVDA"],  # non-strings are dropped
        "tag_subscriptions": ["AI"],
        "notification_preferences": {"daily_digest": True},
    }
    fields = user_fields("doc-id-ignored-when-doc-has-id", doc)

    assert fields["id"] == "u-1"
    assert fields["email_verified"] is True
    assert fields["created_at"] == datetime(2025, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    assert fields["updated_at"].year == 2025  # 'Z' suffix parsed
    assert fields["watchlist"] == ["2330", "NVDA"]
    assert fields["podcast_subscriptions"] == []  # missing array -> []
    assert fields["alerts"] == []
    assert fields["notification_preferences"] == {"daily_digest": True}


def test_user_fields_falls_back_to_the_document_id_and_defaults():
    fields = user_fields("u-2", {"google_id": "g-2", "email": "b@example.com"})
    assert fields["id"] == "u-2"
    assert fields["name"] == "" and fields["avatar"] == ""
    assert fields["created_at"].tzinfo is not None
    assert fields["watchlist"] == []


@pytest.mark.parametrize("doc", [{}, {"google_id": "g"}, {"email": "e@x.com"}, None])
def test_user_fields_rejects_documents_that_cannot_back_an_account(doc):
    with pytest.raises(ValueError):
        user_fields("u-3", doc)


def _seed_mirror(engine, docs: list[tuple[str, dict]]) -> None:
    """Stand in for firestore_mirror.users (a Postgres schema) via an ATTACHed SQLite db."""
    import json as _json

    with engine.begin() as conn:
        conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS firestore_mirror")
        conn.exec_driver_sql(
            "CREATE TABLE firestore_mirror.users (id text PRIMARY KEY, doc text NOT NULL)"
        )
        for doc_id, doc in docs:
            conn.exec_driver_sql(
                "INSERT INTO firestore_mirror.users (id, doc) VALUES (?, ?)",
                (doc_id, _json.dumps(doc)),
            )


def test_migrate_inserts_missing_users_skips_existing_and_reports_problems(orm_db):
    _seed_mirror(orm_db, [
        ("u-1", {"google_id": "g-1", "email": "a@example.com", "name": "Aki",
                 "watchlist": ["2330"]}),
        ("u-2", {"google_id": "g-2", "email": "b@example.com"}),
        ("u-broken", {"email": "c@example.com"}),           # no google_id
        ("u-dupe", {"google_id": "g-2", "email": "d@example.com"}),  # google_id collision
    ])

    inserted, skipped, problems = migrate(dry_run=True)
    assert (inserted, skipped) == (2, 0)
    assert len(problems) == 2
    assert user_db.get_user_by_google_id("g-1") is None  # dry run wrote nothing

    assert migrate()[:2] == (2, 0)
    migrated = user_db.get_user_by_google_id("g-1")
    assert migrated.id == "u-1" and migrated.watchlist == ["2330"]

    # Re-runnable: the second pass inserts nothing and leaves live edits alone.
    user_db.add_to_watchlist("u-1", "NVDA")
    assert migrate()[:2] == (0, 2)
    assert user_db.get_user_subscriptions("u-1")["watchlist"] == ["2330", "NVDA"]
