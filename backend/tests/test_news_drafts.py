"""Draft-only news handoff, using isolated SQLite and mocked HTTP/media IO."""
from datetime import datetime, timezone
import base64
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
    store = Mock(return_value="https://media.example/image.png")
    monkeypatch.setattr(service, "store_bytes", store)
    return store


PNG = b"\x89PNG\r\n\x1a\nscreenshot"


def body(key="one"):
    return service.NewsDraftBody(
        article_id=key, canonical_url=f"https://example.com/{key}", content_hash=key,
        image_png_base64=base64.b64encode(PNG).decode(), source="Reuters", published_at=datetime.now(timezone.utc),
        text="新聞標題\n這是一篇新聞草稿。", comment=f"來源：https://example.com/{key}",
    )


@pytest.mark.parametrize("payload", [
    base64.b64encode(b"<html>not an image</html>").decode(),   # wrong bytes
    base64.b64encode(b"\xff\xd8\xffjpeg").decode(),             # not a PNG
    "not base64 !!",
])
def test_no_image_no_draft(lane, payload):
    request = body().model_copy(update={"image_png_base64": payload})
    assert service.save_news_draft(request) == {"status": "no_image"}
    lane.assert_not_called()
    with session_scope() as db:
        assert db.query(PromoDraft).count() == 0
        assert db.query(UserNotification).count() == 0


def test_oversized_screenshot_is_refused(lane, monkeypatch):
    monkeypatch.setattr(service, "MAX_IMAGE_BYTES", 16)
    assert service.save_news_draft(body()) == {"status": "no_image"}
    lane.assert_not_called()


def test_screenshot_bytes_are_stored_as_png(lane):
    assert service.save_news_draft(body())["status"] == "created"
    bucket, path, data = lane.call_args.args
    assert path.startswith("promo-media/news-") and path.endswith(".png") and data == PNG


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


def test_already_drafted_skips_before_download(lane):
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



@pytest.mark.parametrize("headline", ["新" * 81, "新" * 76 + "尚未核准"])
def test_long_headline_is_no_longer_a_reason_to_skip(lane, headline):
    request = body().model_copy(update={"text": headline + "\n新聞內容"})
    result = service.save_news_draft(request)
    assert result["status"] == "created"
    with session_scope() as db:
        assert db.get(PromoDraft, result["id"]).text == request.text


def test_stock_chart_is_second_durable_image_and_retries_do_not_duplicate(lane):
    request = body().model_copy(update={"chart_ticker": "ORCL", "stock_chart_png_base64": base64.b64encode(PNG + b"chart").decode()})
    lane.side_effect = ["https://media.example/screenshot.png", "https://media.example/chart.png"]
    result = service.save_news_draft(request)
    assert result["status"] == "created"
    with session_scope() as db:
        draft = db.get(PromoDraft, result["id"])
        assert [m["path"] for m in draft.media] == ["https://media.example/screenshot.png", "https://media.example/chart.png"]
        assert draft.media[1]["filename"].startswith("news-stock-ORCL-")
        assert draft.text == request.text
    assert service.save_news_draft(request) == {"status": "already_drafted"}
    assert lane.call_count == 2


@pytest.mark.parametrize("chart,failure", [("invalid base64", None), (base64.b64encode(PNG).decode(), OSError("full")), (base64.b64encode(PNG).decode(), None)])
def test_optional_chart_failure_preserves_screenshot_draft(lane, chart, failure):
    lane.side_effect = ["https://media.example/screenshot.png", failure]
    request = body().model_copy(update={"chart_ticker": "ORCL", "stock_chart_png_base64": chart})
    result = service.save_news_draft(request)
    assert result["status"] == "created"
    with session_scope() as db:
        draft = db.get(PromoDraft, result["id"])
        assert len(draft.media) == 1
        assert draft.media[0]["path"] == "https://media.example/screenshot.png"
        assert db.query(UserNotification).count() == 1
