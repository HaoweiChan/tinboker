"""Draft-only news handoff, using isolated SQLite and mocked HTTP/media IO."""
from datetime import datetime, timezone
from io import BytesIO
import socket
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
    response = Mock(status=200)
    response.getheader.side_effect = lambda name: {"Content-Type": "image/png"}.get(name)
    default = {"read1": BytesIO(b"\x89PNG\r\n\x1a\nimage").read1}
    response.read1.side_effect = default["read1"]
    connection = Mock()
    connection.getresponse.return_value = response

    def connect(*_args):
        # A fresh body per download (one shared stream is empty by the second draft),
        # unless a test installed its own body.
        if response.read1.side_effect is default["read1"]:
            default["read1"] = response.read1.side_effect = BytesIO(b"\x89PNG\r\n\x1a\nimage").read1
        return connection

    http = Mock(side_effect=connect, return_value=connection)
    http.response = response
    monkeypatch.setattr(service, "_ImageConnection", http)
    monkeypatch.setattr(service.socket, "getaddrinfo", Mock(return_value=[
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
    ]))
    monkeypatch.setattr(service, "store_bytes", Mock(return_value="https://media.example/image.png"))
    return http



def body(key="one"):
    return service.NewsDraftBody(
        article_id=key, canonical_url=f"https://example.com/{key}", content_hash=key,
        image_url="https://example.com/lead.png", source="Reuters", published_at=datetime.now(timezone.utc),
        text="新聞標題\n這是一篇新聞草稿。", comment=f"來源：https://example.com/{key}",
    )


def test_no_image_no_draft(lane):
    lane.response.read1.side_effect = BytesIO(b"").read1
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
def test_long_headline_uses_source_image(lane, headline):
    request = body().model_copy(update={"text": headline + "\n新聞內容"})
    result = service.save_news_draft(request)
    assert result["status"] == "created"
    with session_scope() as db:
        assert db.get(PromoDraft, result["id"]).text == request.text


def assert_no_image(request):
    assert service.save_news_draft(request) == {"status": "no_image"}
    service.store_bytes.assert_not_called()
    with session_scope() as db:
        assert db.query(PromoDraft).count() == 0
        assert db.query(UserNotification).count() == 0


@pytest.mark.parametrize("url", ["", "http://example.com/image.png", "https://user:pass@example.com/image.png"])
def test_invalid_image_url(lane, url):
    assert_no_image(body().model_copy(update={"image_url": url}))
    lane.assert_not_called()


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "240.0.0.1", "224.0.0.1", "::1", "fc00::1", "ff02::1"])
def test_non_public_image_host(lane, monkeypatch, address):
    monkeypatch.setattr(service.socket, "getaddrinfo", Mock(return_value=[
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)),
    ]))
    assert_no_image(body())
    lane.assert_not_called()


def test_wrong_content_type(lane):
    lane.response.getheader.side_effect = lambda name: "text/html" if name == "Content-Type" else None
    assert_no_image(body())


@pytest.mark.parametrize("declared", [False, True])
def test_oversized_image(lane, monkeypatch, declared):
    monkeypatch.setattr(service, "MAX_IMAGE_BYTES", 16)
    lane.response.getheader.side_effect = lambda name: {
        "Content-Type": "image/png", "Content-Length": "17" if declared else None,
    }.get(name)
    lane.response.read1.side_effect = BytesIO(b"\x89PNG\r\n\x1a\n" + b"x" * 9).read1
    assert_no_image(body())


def test_non_image_bytes(lane):
    lane.response.read1.side_effect = BytesIO(b"<html>not an image</html>").read1
    assert_no_image(body())


@pytest.mark.parametrize("status", [302, 404, 500])
def test_http_error_or_redirect(lane, status):
    lane.response.status = status
    assert_no_image(body())
    lane.return_value.request.assert_called_once()


def test_download_timeout(lane):
    lane.response.read1.side_effect = TimeoutError("timeout")
    assert_no_image(body())
    lane.return_value.close.assert_called_once()


@pytest.mark.parametrize("content_type, data, extension", [
    ("image/jpeg", b"\xff\xd8\xffjpeg", "jpg"),
    ("image/png", b"\x89PNG\r\n\x1a\npng", "png"),
    ("image/webp", b"RIFF1234WEBPdata", "webp"),
])
def test_image_bytes_and_extension_match(lane, content_type, data, extension):
    lane.response.getheader.side_effect = lambda name: content_type if name == "Content-Type" else None
    lane.response.read1.side_effect = BytesIO(data).read1
    result = service.save_news_draft(body())
    assert result["status"] == "created"
    bucket, path, stored = service.store_bytes.call_args.args
    assert bucket == service.settings.promo_media_bucket
    assert path.startswith("promo-media/news-") and path.endswith("." + extension)
    assert stored == data
    with session_scope() as db:
        assert db.get(PromoDraft, result["id"]).media[0]["filename"] == path.split("/")[-1]
    lane.assert_called_once_with("example.com", 443, "93.184.216.34")


def test_pinned_connection_keeps_tls_hostname(monkeypatch):
    raw_socket = Mock()
    connect = Mock(return_value=raw_socket)
    monkeypatch.setattr(service.socket, "create_connection", connect)
    connection = service._ImageConnection("example.com", 443, "93.184.216.34")
    context = Mock()
    connection._context = context
    connection.connect()
    connect.assert_called_once_with(("93.184.216.34", 443), service.IMAGE_TIMEOUT)
    context.wrap_socket.assert_called_once_with(raw_socket, server_hostname="example.com")


def test_truncated_image_response(lane):
    lane.response.getheader.side_effect = lambda name: {
        "Content-Type": "image/png", "Content-Length": "100",
    }.get(name)
    assert_no_image(body())


def test_mixed_public_private_dns_rejected(lane, monkeypatch):
    monkeypatch.setattr(service.socket, "getaddrinfo", Mock(return_value=[
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
    ]))
    assert_no_image(body())
    lane.assert_not_called()
