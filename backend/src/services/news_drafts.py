"""News handoff: one mandatory source image, an editable promo draft, and admin inbox notices."""
import ipaddress
import logging
import socket
import time
import uuid
from datetime import datetime, timezone
from http.client import HTTPSConnection
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, Field, HttpUrl
from sqlalchemy import func, text as sql_text
from sqlalchemy.orm import Session

from src.config import settings
from src.database.models import PromoDraft, User, UserNotification
from src.database.postgres import session_scope
from src.services.gcs_content import store_bytes

logger = logging.getLogger(__name__)
DAILY_CAP = 2
MAX_IMAGE_BYTES = 8 * 1024 * 1024
IMAGE_TIMEOUT = 15


class _ImageConnection(HTTPSConnection):
    """Pin the validated address while retaining hostname/SNI certificate checks."""

    def __init__(self, host: str, port: int, address: str) -> None:
        super().__init__(host, port, timeout=IMAGE_TIMEOUT)
        self.address = address

    def connect(self) -> None:
        sock = socket.create_connection((self.address, self.port), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


def _download_image(url: str) -> tuple[bytes, str]:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname
            or parsed.username is not None or parsed.password is not None):
        raise ValueError("invalid image URL")
    port = parsed.port or 443
    addresses = socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)
    resolved = [ipaddress.ip_address(item[4][0]) for item in addresses]
    if not resolved or any(
        not address.is_global or address.is_reserved or address.is_multicast
        for address in resolved
    ):
        raise ValueError("non-public image host")
    connection = _ImageConnection(parsed.hostname, port, addresses[0][4][0])
    deadline = time.monotonic() + IMAGE_TIMEOUT
    try:
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        connection.request("GET", path, headers={"Accept-Encoding": "identity"})
        response = connection.getresponse()
        # ponytail: redirects are rejected; support validated hops only if sources require them.
        if response.status != 200:
            raise ValueError("image HTTP error")
        content_type = (response.getheader("Content-Type") or "").split(";", 1)[0].strip().lower()
        extensions = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
        if content_type not in extensions:
            raise ValueError("unsupported image type")
        size = response.getheader("Content-Length")
        if size is not None and (int(size) < 0 or int(size) > MAX_IMAGE_BYTES):
            raise ValueError("image too large")
        image = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("image download timeout")
            if connection.sock is not None:
                connection.sock.settimeout(remaining)
            chunk = response.read1(min(64 * 1024, MAX_IMAGE_BYTES + 1 - len(image)))
            if not chunk:
                break
            image.extend(chunk)
            if len(image) > MAX_IMAGE_BYTES:
                raise ValueError("image too large")
        if size is not None and len(image) != int(size):
            raise ValueError("incomplete image response")
        # ponytail: signature validation only; full decoding waits for a need beyond lead images.
        valid = {
            "image/jpeg": image.startswith(b"\xff\xd8\xff"),
            "image/png": image.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/webp": image[:4] == b"RIFF" and image[8:12] == b"WEBP",
        }
        if not valid[content_type]:
            raise ValueError("image signature mismatch")
        return bytes(image), extensions[content_type]
    finally:
        connection.close()


class NewsDraftBody(BaseModel):
    article_id: str = Field(min_length=1, max_length=500)
    canonical_url: HttpUrl
    image_url: str = ""
    content_hash: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=100)
    published_at: AwareDatetime
    text: str = Field(min_length=1)
    comment: str = Field(min_length=1)


def _state(db: Session, now: datetime) -> dict:
    # ponytail: at most two rows/day; scan this small ledger until it needs an index.
    rows = db.query(PromoDraft).filter(PromoDraft.news_source.isnot(None)).all()
    rows = [r for r in rows if r.news_source]
    today = now.astimezone(ZoneInfo("Asia/Taipei")).date()
    count = sum(
        r.created_at.replace(tzinfo=timezone.utc).astimezone(ZoneInfo("Asia/Taipei")).date() == today
        for r in rows
    )
    return {
        "already_posted_ids": [r.news_source["article_id"] for r in rows],
        "already_posted_urls": [r.news_source["canonical_url"] for r in rows],
        "already_posted_hashes": [r.news_source["content_hash"] for r in rows],
        "remaining_today": max(0, DAILY_CAP - count),
    }


def draft_state() -> dict:
    with session_scope() as db:
        return _state(db, datetime.now(timezone.utc))


def save_news_draft(body: NewsDraftBody) -> dict:
    """All blocking work runs in the endpoint's worker thread. Never publishes."""
    now = datetime.now(timezone.utc)
    with session_scope() as db:
        if db.bind.dialect.name == "postgresql":
            # Shared across all API workers/environments; cap and dedup are one transaction.
            db.execute(sql_text("SET LOCAL lock_timeout = '5s'"))
            db.execute(sql_text("SELECT pg_advisory_xact_lock(746202610)"))
        state = _state(db, now)
        if (body.article_id in state["already_posted_ids"]
                or str(body.canonical_url) in state["already_posted_urls"]
                or body.content_hash in state["already_posted_hashes"]):
            return {"status": "already_drafted"}
        if not state["remaining_today"]:
            return {"status": "daily_cap"}
        admins = db.query(User).filter(func.lower(User.email).in_(
            [email.lower() for email in settings.admin_emails]
        )).all()
        if not admins:
            logger.warning("News draft skipped: no registered admin notification recipient")
            return {"status": "no_admin"}
        headline = next((line.strip() for line in body.text.splitlines() if line.strip()), "")
        try:
            image, extension = _download_image(body.image_url)
            filename = f"news-{uuid.uuid4().hex}.{extension}"
            url = store_bytes(settings.promo_media_bucket, f"promo-media/{filename}", image)
            if not url:
                raise ValueError("missing stored image URL")
        except Exception as exc:
            logger.warning("News draft skipped: source image download/storage failed (%s: %s)",
                           type(exc).__name__, exc)
            return {"status": "no_image"}
        row = PromoDraft(
            name=f"新聞草稿 · {body.source} · {headline}"[:200], text=body.text,
            media=[{"type": "image", "path": url, "filename": filename}],
            comments=[body.comment], platforms=["threads"], updated_by="news-pipeline@service",
            created_at=now.replace(tzinfo=None),
            news_source={"article_id": body.article_id, "canonical_url": str(body.canonical_url),
                         "content_hash": body.content_hash},
        )
        db.add(row)
        db.flush()
        for admin in admins:
            db.add(UserNotification(
                id=str(uuid.uuid4()), user_id=admin.id, type="news_draft",
                title="新聞 Threads 草稿待審閱", body=row.name,
                data={"draft_id": row.id}, is_read=False, created_at=now,
            ))
        return {"status": "created", "id": row.id}
