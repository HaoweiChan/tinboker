"""Manual Threads promos are tracked without contacting Meta in tests."""

from datetime import datetime

from src.database.models import ScheduledSocialPost
from src.database.postgres import session_scope
from src.services import promo_publisher, social_ledger
from src.services.threads_publisher import list_posted
from src.services.threads_service import ThreadsError


class FakeThreadsService:
    is_configured = True

    async def publish(self, text):
        return "root-media-id"

    async def publish_single_media(self, text, item):
        return "root-media-id"

    async def publish_media_carousel(self, items, text):
        return "root-media-id"

    async def get_permalink(self, media_id):
        return "https://www.threads.net/@tinboker/post/abc"

    async def publish_reply(self, text, reply_to_id):
        if text == "second reply":
            raise ThreadsError("provider refused reply")
        return "reply-media-id"


async def test_manual_promo_persists_exact_content_and_partial_reply_state(temp_db, monkeypatch):
    monkeypatch.setattr(promo_publisher, "ThreadsService", FakeThreadsService)

    result = await promo_publisher.publish_promo(
        "  root copy  ",
        [{"type": "image", "url": "https://media.example/card.jpg", "filename": "card.jpg"}],
        ["threads"],
        comments=["first reply", "second reply"],
        dry_run=False,
    )

    published = result["platforms"]["threads"]
    assert published["posted"] is True
    assert published["posted_comments"] == 1
    assert published["comment_error"] == "publish_failed"
    rows = social_ledger.list_posted("threads")
    row = rows[0]
    assert row["origin"] == "manual"
    assert row["delivery"] == "direct"
    assert row["media_id"] == "root-media-id"
    assert row["permalink"] == "https://www.threads.net/@tinboker/post/abc"
    assert row["child_ids"] == ["reply-media-id"]
    assert row["tracking_error"] == "partial_reply:publish_failed"
    assert row["post_snapshot"] == {
        "text": "root copy",
        "media": [{"type": "image", "url": "https://media.example/card.jpg", "filename": "card.jpg"}],
        "requested_comments": ["first reply", "second reply"],
        "posted_reply_texts": ["first reply"],
    }


async def test_ledger_failure_after_root_does_not_report_post_as_failed(temp_db, monkeypatch):
    monkeypatch.setattr(promo_publisher, "ThreadsService", FakeThreadsService)

    def fail_record(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(promo_publisher.social_ledger, "record", fail_record)
    result = await promo_publisher.publish_promo("root", [], ["threads"], dry_run=False)
    published = result["platforms"]["threads"]
    assert published["posted"] is True
    assert published["media_id"] == "root-media-id"
    assert published["tracking_error"] == "ledger_write_failed"


def test_scheduled_history_projection_requires_confirmed_threads_result_and_dedupes(temp_db):
    with session_scope() as db:
        db.add_all([
            ScheduledSocialPost(
                post_type="promo", text="confirmed manual copy", media=[], comments=["reply"],
                platforms=["threads"], scheduled_for=datetime.utcnow(),
                status="posted", posted_at=datetime.utcnow(),
                published_results={"threads": {"posted": True, "media_id": "scheduled-media", "posted_comments": 1}},
            ),
            ScheduledSocialPost(
                post_type="promo", text="failed copy", media=[], comments=[],
                platforms=["threads"], scheduled_for=datetime.utcnow(),
                status="failed", published_results={"threads": {"posted": False, "media_id": "failed-media"}},
            ),
        ])

    rows = list_posted()
    scheduled = next(row for row in rows if row["media_id"] == "scheduled-media")
    assert scheduled["origin"] == "manual"
    assert scheduled["delivery"] == "scheduled"
    assert scheduled["post_snapshot"]["text"] == "confirmed manual copy"
    assert scheduled["post_snapshot"]["posted_reply_texts"] == ["reply"]
    assert all(row["media_id"] != "failed-media" for row in rows)

    social_ledger.record("threads", "manual:existing", "scheduled-media", "", origin="manual")
    assert len([row for row in list_posted() if row["media_id"] == "scheduled-media"]) == 1
