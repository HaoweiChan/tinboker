"""Self-check for get_unread_count: it must count server-side, never stream the docs.

Streaming cost one document transfer per unread notification, so users with a
backlog saw this endpoint take up to 90s while the median stayed under a second.
The fake below raises if .stream() is touched, so a regression to the old
sum(1 for _ in docs) form fails here rather than in production.
"""
from types import SimpleNamespace

# The real result type — if the library ever changes its shape, this test notices.
from google.cloud.firestore_v1.base_aggregation import AggregationResult

import src.database.notification_db as ndb


class _Streamed(AssertionError):
    """Raised if the implementation falls back to streaming documents."""


def _fake_firestore(count):
    """Minimal .collection().document().collection().where() chain."""
    query = SimpleNamespace()
    query.stream = lambda: (_ for _ in ()).throw(
        _Streamed("streamed documents instead of using count() aggregation")
    )
    query.count = lambda: SimpleNamespace(
        get=lambda: [[AggregationResult(alias="field_1", value=count)]]
    )

    notifications = SimpleNamespace(where=lambda *a, **k: query)
    user_doc = SimpleNamespace(collection=lambda name: notifications)
    users = SimpleNamespace(document=lambda uid: user_doc)
    return SimpleNamespace(db=SimpleNamespace(collection=lambda name: users))


def test_counts_via_aggregation_without_streaming(monkeypatch):
    monkeypatch.setattr(ndb, "_get_firestore_service", lambda: _fake_firestore(42))
    assert ndb.get_unread_count("user-1") == 42


def test_zero_is_reported_as_zero(monkeypatch):
    """Guards the int() conversion — the aggregation returns a float-typed value."""
    monkeypatch.setattr(ndb, "_get_firestore_service", lambda: _fake_firestore(0.0))
    result = ndb.get_unread_count("user-1")
    assert result == 0
    assert isinstance(result, int)


def test_query_failure_degrades_to_zero(monkeypatch):
    """Pre-existing contract: a failing query must not 500 the endpoint.

    Only covers failures raised by the query itself (unavailable backend, missing
    index) — building the service happens outside the try block, same as before.
    """
    fs = _fake_firestore(1)
    fs.db.collection("users").document("u").collection("notifications").where().count = (
        lambda: SimpleNamespace(get=lambda: (_ for _ in ()).throw(RuntimeError("unavailable")))
    )
    monkeypatch.setattr(ndb, "_get_firestore_service", lambda: fs)
    assert ndb.get_unread_count("user-1") == 0
