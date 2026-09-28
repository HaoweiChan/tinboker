"""Public counts reflect current unique platform followers."""
from unittest.mock import AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from src.database import user_db
from src.database.models import User
from src.database.postgres import session_scope
from src.models.podcast import Podcast
from src.routers import podcast as podcast_router


def test_unique_current_counts_and_one_query(orm_db):
    with session_scope() as db:
        for i, follows in enumerate([
            ["股癌", "股癌", "財報狗", "deleted", None, {}],
            ["股癌"], [], None, {"股癌": True},
        ]):
            db.add(User(id=str(i), google_id=str(i), email=f"{i}@example.com",
                        podcast_subscriptions=follows))
    statements = []
    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(orm_db, "before_cursor_execute", record)
    assert user_db.get_podcast_subscriber_counts(["股癌", "財報狗", "none", "股癌"]) == {
        "股癌": 2, "財報狗": 1, "none": 0,
    }
    assert len(statements) == 1
    assert "users.email" not in statements[0]
    user_db.remove_podcast_subscription("1", "股癌")
    assert user_db.get_podcast_subscriber_counts(["股癌"]) == {"股癌": 1}
    statements.clear()
    assert user_db.get_podcast_subscriber_counts([]) == {}
    assert not statements


def test_public_response_and_unavailable(monkeypatch, orm_db):
    with session_scope() as db:
        db.add(User(id="1", google_id="1", email="private@example.com",
                    podcast_subscriptions=["股癌"]))
    show = Podcast(id="股癌", name="股癌", popularity_rank=5)
    monkeypatch.setattr(podcast_router.podcast_service, "get_all_podcasts",
                        AsyncMock(return_value=[show, Podcast(id="none", name="none")]))
    monkeypatch.setattr(podcast_router.podcast_service, "get_podcast_by_name",
                        AsyncMock(return_value=show))
    app = FastAPI()
    app.include_router(podcast_router.router)
    with TestClient(app) as client:
        response = client.get("/api/podcast")
        assert response.status_code == 200
        assert [item["subscriber_count"] for item in response.json()] == [1, 0]
        assert response.json()[0]["popularity_rank"] == 5
        assert "private@example.com" not in response.text
        assert client.get("/api/podcast/股癌").json()["subscriber_count"] == 1
        def unavailable(names):
            raise RuntimeError("database unavailable")
        monkeypatch.setattr(podcast_router, "get_podcast_subscriber_counts", unavailable)
        assert client.get("/api/podcast").json()[0]["subscriber_count"] is None
        assert show.subscriber_count is None
