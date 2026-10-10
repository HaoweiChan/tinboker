"""Draft-only news handoff, using isolated SQLite and mocked rendering/media IO."""
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.database.models import PromoDraft, User, UserNotification
from src.database.postgres import session_scope
from src.services import news_drafts as service


@pytest.fixture
def lane(orm_db, monkeypatch):
    monkeypatch.setattr(service.settings, "admin_emails", ["owner@example.com"])
    with session_scope() as db:
        db.add(User(id="owner", google_id="owner", email="owner@example.com"))
    render = Mock(return_value=b"png")
    monkeypatch.setattr(service, "svg_to_png", render)
    monkeypatch.setattr(service, "title_card_svg", Mock(return_value="<svg/>"))
    monkeypatch.setattr(service, "store_bytes", Mock(return_value="https://media.example/card.png"))
    return render


def body(key="one"):
    return service.NewsDraftBody(
        article_id=key, canonical_url=f"https://example.com/{key}", content_hash=key,
        source="Reuters", published_at=datetime.now(timezone.utc),
        text="新聞標題\n這是一篇新聞草稿。", comment=f"來源：https://example.com/{key}",
    )


def test_no_image_no_draft(lane):
    lane.return_value = b""
    assert service.save_news_draft(body()) == {"status": "no_image"}
    with session_scope() as db:
        assert db.query(PromoDraft).count() == 0
        assert db.query(UserNotification).count() == 0


def test_saved_draft_notifies_admin(lane):
    result = service.save_news_draft(body())
    assert result["status"] == "created"
    with session_scope() as db:
        draft = db.get(PromoDraft, result["id"])
        assert draft.media[0]["type"] == "image"
        assert draft.platforms == ["threads"]
        assert draft.comments == [body().comment]
        notice = db.query(UserNotification).one()
        assert notice.user_id == "owner"
        assert notice.type == "news_draft"
        assert notice.data == {"draft_id": draft.id}


def test_already_drafted_skips_before_render(lane):
    service.save_news_draft(body())
    assert service.save_news_draft(body()) == {"status": "already_drafted"}
    assert lane.call_count == 1


def test_daily_cap(lane):
    service.save_news_draft(body("one"))
    service.save_news_draft(body("two"))
    assert service.save_news_draft(body("three")) == {"status": "daily_cap"}
    assert service.draft_state()["remaining_today"] == 0
    assert lane.call_count == 2


def test_deleted_draft_keeps_identity_and_cap(lane):
    from src.routers.social import delete_promo_draft, list_promo_drafts
    result = service.save_news_draft(body())
    with session_scope() as db:
        delete_promo_draft(result["id"], None, db)
        assert list_promo_drafts(None, db) == {"drafts": []}
    assert service.save_news_draft(body()) == {"status": "already_drafted"}
    assert service.draft_state()["remaining_today"] == 1


def test_no_admin_skips(lane, monkeypatch):
    monkeypatch.setattr(service.settings, "admin_emails", [])
    assert service.save_news_draft(body()) == {"status": "no_admin"}
    lane.assert_not_called()


def test_news_routes_require_auth(monkeypatch):
    from src.routers.social import promo_router
    monkeypatch.setattr(service.settings, "tinboker_social_token", "")
    app = FastAPI()
    app.include_router(promo_router)
    with TestClient(app) as client:
        assert client.get("/api/admin/promo/news-drafts/state").status_code in (401, 403)
        assert client.post("/api/admin/promo/news-drafts", json=body().model_dump(mode="json")).status_code in (401, 403)


@pytest.mark.parametrize("field", ["canonical_url", "content_hash"])
def test_source_alias_skips(lane, field):
    service.save_news_draft(body())
    alias = body("alias").model_copy(update={field: getattr(body(), field)})
    assert service.save_news_draft(alias) == {"status": "already_drafted"}
    assert lane.call_count == 1


def test_storage_failure_skips(lane, monkeypatch):
    monkeypatch.setattr(service, "store_bytes", Mock(side_effect=OSError("disk full")))
    assert service.save_news_draft(body()) == {"status": "no_image"}
    with session_scope() as db:
        assert db.query(PromoDraft).count() == 0


def test_notification_failure_rolls_back_draft(lane, monkeypatch):
    from sqlalchemy.orm import Session
    original = Session.add

    def fail_notice(self, obj, *args, **kwargs):
        if isinstance(obj, UserNotification):
            raise RuntimeError("notification failure")
        return original(self, obj, *args, **kwargs)

    monkeypatch.setattr(Session, "add", fail_notice)
    with pytest.raises(RuntimeError, match="notification failure"):
        service.save_news_draft(body())
    with session_scope() as db:
        assert db.query(PromoDraft).count() == 0


def test_service_token_can_save_but_invalid_token_cannot(lane, monkeypatch):
    from src.routers.social import promo_router
    monkeypatch.setattr(service.settings, "tinboker_social_token", "unit-test-only")
    app = FastAPI()
    app.include_router(promo_router)
    with TestClient(app) as client:
        path = "/api/admin/promo/news-drafts"
        assert client.get(path + "/state", headers={"Authorization": "Bearer invalid"}).status_code == 403
        headers = {"Authorization": "Bearer unit-test-only"}
        state = client.get(path + "/state", headers=headers)
        assert state.status_code == 200
        assert state.headers["cache-control"] == "private, no-store"
        result = client.post(path, headers=headers, json=body().model_dump(mode="json"))
        assert result.status_code == 200
        assert result.json()["status"] == "created"


def test_scheduled_posts_list_is_unchanged(orm_db):
    from src.database.models import ScheduledSocialPost
    from src.routers.social import list_scheduled_posts
    with session_scope() as db:
        row = ScheduledSocialPost(
            post_type="promo", text="Scheduled promo", media=[], comments=[],
            platforms=["threads"], scheduled_for=datetime.now(timezone.utc),
            status="pending", created_by="owner@example.com",
        )
        db.add(row)
        db.flush()
        result = list_scheduled_posts(status=None, limit=50, _=None, db=db)
        assert [post["id"] for post in result["posts"]] == [row.id]


def test_long_writer_text_is_preserved(lane):
    payload = body().model_dump()
    payload["text"] = "新聞標題\n" + "新聞重點。" * 120
    request = service.NewsDraftBody(**payload)
    result = service.save_news_draft(request)
    assert result["status"] == "created"
    with session_scope() as db:
        assert db.get(PromoDraft, result["id"]).text == payload["text"]


def test_overlong_headline_skips_without_truncating_claim(lane, monkeypatch):
    from src.services.title_card import title_card_svg
    monkeypatch.setattr(service, "title_card_svg", title_card_svg)
    request = body().model_copy(update={"text": "新" * 81 + "\n新聞內容"})
    assert service.save_news_draft(request) == {"status": "no_image"}
    lane.assert_not_called()
    with session_scope() as db:
        assert db.query(PromoDraft).count() == 0
        assert db.query(UserNotification).count() == 0


def test_eighty_character_headline_cannot_lose_final_qualifier(lane, monkeypatch):
    from src.services.title_card import title_card_svg
    monkeypatch.setattr(service, "title_card_svg", title_card_svg)
    request = body().model_copy(update={"text": "新" * 76 + "尚未核准"})
    assert service.save_news_draft(request) == {"status": "no_image"}
    lane.assert_not_called()
    with session_scope() as db:
        assert db.query(PromoDraft).count() == 0
        assert db.query(UserNotification).count() == 0


def test_strict_renderer_rejects_overflow_and_default_stays_compatible():
    from src.services.title_card import title_card_svg
    headline = "新" * 76 + "尚未核准"
    with pytest.raises(ValueError, match="line ceiling"):
        title_card_svg(headline, strict=True)
    assert title_card_svg(headline).startswith("<svg")
