"""News handoff: one mandatory article screenshot, an editable promo draft, and admin inbox notices."""
import base64
import logging
import uuid
from datetime import datetime, timezone
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
MAX_IMAGE_BYTES = 4 * 1024 * 1024


def _decode_screenshot(encoded: str) -> bytes:
    """The pipeline's article screenshot. A PNG, bounded, or nothing."""
    image = base64.b64decode(encoded, validate=True)
    if not image.startswith(b"\x89PNG\r\n\x1a\n") or len(image) > MAX_IMAGE_BYTES:
        raise ValueError("not a PNG within the size limit")
    return image


class NewsDraftBody(BaseModel):
    article_id: str = Field(min_length=1, max_length=500)
    canonical_url: HttpUrl
    image_png_base64: str = Field(min_length=1, max_length=MAX_IMAGE_BYTES * 4 // 3 + 4)
    stock_chart_png_base64: str | None = Field(default=None, max_length=MAX_IMAGE_BYTES * 4 // 3 + 4)
    chart_ticker: str | None = Field(default=None, pattern=r"^[A-Z0-9.\-]{1,20}$")
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
            image = _decode_screenshot(body.image_png_base64)
            filename = f"news-{uuid.uuid4().hex}.png"
            url = store_bytes(settings.promo_media_bucket, f"promo-media/{filename}", image)
            if not url:
                raise ValueError("missing stored image URL")
        except Exception as exc:
            logger.warning("News draft skipped: screenshot decode/storage failed (%s: %s)",
                           type(exc).__name__, exc)
            return {"status": "no_image"}
        media = [{"type": "image", "path": url, "filename": filename}]
        if body.stock_chart_png_base64 and body.chart_ticker:
            try:
                chart = _decode_screenshot(body.stock_chart_png_base64)
                chart_filename = f"news-stock-{body.chart_ticker}-{uuid.uuid4().hex}.png"
                chart_url = store_bytes(settings.promo_media_bucket, f"promo-media/{chart_filename}", chart)
                if chart_url:
                    media.append({"type": "image", "path": chart_url, "filename": chart_filename})
            except Exception as exc:
                logger.warning("News chart omitted: decode/storage failed (%s)", type(exc).__name__)
        row = PromoDraft(
            name=f"新聞草稿 · {body.source} · {headline}"[:200], text=body.text,
            media=media,
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
