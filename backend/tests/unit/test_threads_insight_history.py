from datetime import datetime

import pytest

from src.database.models import SocialPostLedger, ThreadsInsightsSyncState, ThreadsPostInsightSnapshot
from src.database.postgres import session_scope
from src.services import social_ledger
from src.services.threads_insights_service import (
    ThreadsAPIError,
    ThreadsInsightsService,
    _parse_metrics,
    _save_metric_snapshot,
    history_sync_status,
    metric_snapshot_history,
)


def test_metrics_keep_missing_values_absent_and_explicit_zero(temp_db):
    assert _parse_metrics({"data": [
        {"name": "views"},
        {"name": "likes", "total_value": {"value": None}},
        {"name": "replies", "total_value": {"value": 0}},
    ]}) == {"replies": 0}


def test_daily_snapshot_keeps_first_success_and_empty_failure_does_not_reserve_day(temp_db):
    assert not _save_metric_snapshot("media-1", {})
    assert _save_metric_snapshot("media-1", {"views": 0, "likes": 2})
    assert not _save_metric_snapshot("media-1", {"views": 99})
    history = metric_snapshot_history(["media-1"])["media-1"]
    assert len(history) == 1
    assert history[0]["metrics"] == {"views": 0, "likes": 2}
    assert datetime.fromisoformat(history[0]["captured_at"]).tzinfo is not None


def test_provider_import_dedupes_by_media_id_and_preserves_publish_copy(temp_db):
    social_ledger.record(
        "threads", "episode:one", "media-1", "https://episode",
        ["reply-1"], origin="manual", post_snapshot={"text": "copy at publish"},
    )
    media = {
        "id": "media-1", "text": "copy after edit", "timestamp": "2025-01-02T03:04:05+0000",
        "permalink": "https://threads.net/t/abc", "media_type": "TEXT_POST",
        "owner": {"id": "account-1"},
    }
    replies = [
        {"id": "reply-1", "text": "first", "is_reply_owned_by_me": True},
        {"id": "reply-2", "text": "second", "is_reply_owned_by_me": True},
        {"id": "other", "text": "not ours", "is_reply_owned_by_me": False},
    ]
    episode_id, created = social_ledger.import_threads_post(media, replies)
    assert (episode_id, created) == ("episode:one", False)
    with session_scope() as db:
        rows = db.query(SocialPostLedger).filter_by(media_id="media-1").all()
        assert len(rows) == 1
        row = rows[0]
        assert row.origin == "manual"
        assert row.post_snapshot == {"text": "copy at publish"}
        assert row.child_ids == ["reply-1", "reply-2"]
        assert row.provider_snapshot["text"] == "copy after edit"
        assert row.provider_snapshot["source"] == "threads_api"
        assert row.provider_snapshot["owned_replies_loaded"] is True
    with pytest.raises(ValueError):
        social_ledger.import_threads_post({"id": "missing-time"})


@pytest.mark.asyncio
async def test_backfill_uses_next_link_not_cursor_and_resumes_idempotently(temp_db, monkeypatch):
    service = ThreadsInsightsService(access_token="token", user_id="account-1", api_base="https://graph.test")
    current_page = 0

    async def fake_get(_client, path, params):
        nonlocal current_page
        if path.endswith("/threads"):
            current_page += 1
            if current_page == 1:
                return {
                    "data": [{"id": "media-1", "text": "old copy", "timestamp": "2024-01-01T00:00:00+0000",
                              "media_type": "TEXT_POST", "owner": {"id": "account-1"}, "has_replies": False}],
                    "paging": {"next": "next-page", "cursors": {"after": "cursor-1"}},
                }
            return {
                "data": [{"id": "media-2", "text": "new copy", "timestamp": "2025-01-01T00:00:00+0000",
                          "media_type": "TEXT_POST", "owner": {"id": "account-1"}, "has_replies": False}],
                # Graph often leaves the final page's after cursor populated.
                "paging": {"cursors": {"after": "cursor-2"}},
            }
        if path.endswith("/insights"):
            return {"data": [{"name": "views", "total_value": {"value": 0}}]}
        raise AssertionError(path)

    monkeypatch.setattr(service, "_get", fake_get)
    first = await service.backfill_page(page_size=5)
    assert first["more_pages"] is True and first["complete"] is False
    with session_scope() as db:
        state = db.get(ThreadsInsightsSyncState, "account")
        assert state.backfill_cursor == "cursor-1"
    second = await service.backfill_page(page_size=5)
    assert second["more_pages"] is False and second["complete"] is True
    assert second["imported"] == 1
    with session_scope() as db:
        assert db.get(ThreadsInsightsSyncState, "account").backfill_complete is True
        row = db.query(SocialPostLedger).filter_by(media_id="media-1").one()
        assert row.posted_at.year == 2024
        samples = db.query(ThreadsPostInsightSnapshot).filter_by(media_id="media-1").all()
        assert len(samples) == 1 and samples[0].metrics == {"views": 0}
    before = current_page
    done = await service.backfill_page()
    assert done["complete"] is True and current_page == before


@pytest.mark.asyncio
async def test_retryable_page_failure_does_not_advance_cursor(temp_db, monkeypatch):
    service = ThreadsInsightsService(access_token="token", user_id="account-1", api_base="https://graph.test")

    async def fail_after_import(_client, path, _params):
        if path.endswith("/threads"):
            return {
                "data": [{"id": "media-1", "text": "copy", "timestamp": "2025-01-01T00:00:00+0000",
                          "owner": {"id": "account-1"}, "has_replies": False}],
                "paging": {"next": "next-page", "cursors": {"after": "cursor-1"}},
            }
        raise ThreadsAPIError("temporary provider error", 503)

    monkeypatch.setattr(service, "_get", fail_after_import)
    with pytest.raises(ThreadsAPIError):
        await service.backfill_page()
    with session_scope() as db:
        assert db.get(ThreadsInsightsSyncState, "account") is None
        assert db.query(SocialPostLedger).filter_by(media_id="media-1").count() == 1


@pytest.mark.asyncio
async def test_backfill_dry_run_reads_sample_but_does_not_write(temp_db, monkeypatch):
    service = ThreadsInsightsService(access_token="token", user_id="account-1", api_base="https://graph.test")

    async def fake_get(_client, path, _params):
        if path.endswith("/threads"):
            return {"data": [{"id": "media-1", "is_reply": False}],
                    "paging": {"cursors": {"after": "cursor-1"}}}
        if path.endswith("/insights"):
            return {"data": [{"name": "views", "total_value": {"value": 2}}]}
        raise AssertionError(path)

    monkeypatch.setattr(service, "_get", fake_get)
    result = await service.backfill_page(dry_run=True)
    assert result["dry_run"] and result["would_import"] == 1
    assert result["insight_metrics"] == ["views"]
    with session_scope() as db:
        assert db.query(SocialPostLedger).count() == 0
        assert db.query(ThreadsPostInsightSnapshot).count() == 0
        assert db.get(ThreadsInsightsSyncState, "account") is None


@pytest.mark.asyncio
async def test_daily_sync_skips_replies_and_resumes_provider_cursor(temp_db, monkeypatch):
    service = ThreadsInsightsService(access_token="token", user_id="account-1", api_base="https://graph.test")
    pages = [
        {"data": [
            {"id": "root-1", "timestamp": "2026-09-28T00:00:00+0000", "owner": {"id": "account-1"}},
            {"id": "reply-1", "is_reply": True, "timestamp": "2026-09-28T00:01:00+0000",
             "owner": {"id": "account-1"}},
        ], "paging": {"next": "next-page", "cursors": {"after": "daily-cursor"}}},
        {"data": [{"id": "root-2", "timestamp": "2026-09-28T00:02:00+0000",
                    "owner": {"id": "account-1"}}], "paging": {"cursors": {"after": "final-cursor"}}},
    ]
    request_params = []

    async def fake_get(_client, path, params):
        if path.endswith("/threads"):
            request_params.append(dict(params))
            return pages.pop(0)
        if path.endswith("/insights"):
            return {"data": [{"name": "views", "total_value": {"value": 1}}]}
        raise AssertionError(path)

    monkeypatch.setattr(service, "_get", fake_get)
    first = await service.sync_recent_posts(limit=5)
    second = await service.sync_recent_posts(limit=5)
    assert first["more_pages"] is True and first["skipped_replies"] == 1
    assert second["more_pages"] is False
    assert request_params[1]["after"] == "daily-cursor"
    with session_scope() as db:
        assert db.query(SocialPostLedger).filter_by(media_id="reply-1").count() == 0
        assert db.query(SocialPostLedger).filter(SocialPostLedger.media_id.in_(["root-1", "root-2"])).count() == 2
        assert db.query(ThreadsPostInsightSnapshot).count() == 2
        state = db.get(ThreadsInsightsSyncState, "account")
        assert state.daily_cursor is None and state.daily_window_since is None
    assert history_sync_status()["metric_snapshots"] == 2
