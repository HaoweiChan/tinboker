"""The shared publishing ledger + the TW posting slots.

Both guard against re-posting: the ledger stops the same episode going out twice
(the Aug 2026 bug: 24 of 63 Threads posts were duplicates), the slots decide when a
scan runs at all.
"""
from datetime import datetime, timedelta, timezone

import pytest

from src.config import settings
from src.services import social_ledger
from src.services import scheduled_social_worker as worker

TW = timezone(timedelta(hours=8))


# ── ledger ───────────────────────────────────────────────────────────

def test_claim_is_exclusive(temp_db):
    """The second claim loses — this is what stops two overlapping triggers double-posting."""
    assert social_ledger.claim("threads", "EP900") is True
    assert social_ledger.claim("threads", "EP900") is False
    assert social_ledger.already_posted("threads", "EP900") is True


def test_claim_is_per_platform(temp_db):
    assert social_ledger.claim("threads", "EP901") is True
    assert social_ledger.claim("facebook", "EP901") is True
    assert social_ledger.already_posted("facebook", "EP901") is True


def test_release_lets_a_failed_publish_retry(temp_db):
    assert social_ledger.claim("threads", "EP902") is True
    social_ledger.release("threads", "EP902")
    assert social_ledger.already_posted("threads", "EP902") is False
    assert social_ledger.claim("threads", "EP902") is True


def test_record_fills_in_the_claimed_row(temp_db):
    social_ledger.claim("threads", "EP903")
    social_ledger.record("threads", "EP903", "media_1", "https://tinboker.com/episode/EP903", ["r1", "r2"])
    rows = social_ledger.list_posted("threads")
    assert rows[0]["episode_id"] == "EP903"
    assert rows[0]["media_id"] == "media_1"
    assert rows[0]["child_ids"] == ["r1", "r2"]


def test_record_without_a_claim_still_writes(temp_db):
    """The admin publish path records directly; it must not need a prior claim."""
    social_ledger.record("facebook", "EP904", "post_1", "https://tinboker.com/episode/EP904")
    assert social_ledger.already_posted("facebook", "EP904") is True


# ── posting slots ────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clear_slots():
    worker._fired_slots.clear()
    yield
    worker._fired_slots.clear()


def test_no_slots_configured_means_never_post(monkeypatch):
    monkeypatch.setattr(settings, "social_publish_slots", "")
    assert worker._due_slots(datetime(2026, 8, 26, 23, 0, tzinfo=TW)) == []


def test_only_slots_already_reached_today_are_due(monkeypatch):
    monkeypatch.setattr(settings, "social_publish_slots", "11:30,15:30,20:30")
    due = worker._due_slots(datetime(2026, 8, 26, 16, 0, tzinfo=TW))
    assert due == ["2026-08-26 11:30", "2026-08-26 15:30"]


def test_a_slot_fires_once_per_day(monkeypatch):
    monkeypatch.setattr(settings, "social_publish_slots", "11:30")
    now = datetime(2026, 8, 26, 12, 0, tzinfo=TW)
    worker._fired_slots.update(worker._due_slots(now))
    assert worker._due_slots(now) == []
    # …and comes due again tomorrow.
    assert worker._due_slots(now + timedelta(days=1)) == ["2026-08-27 11:30"]


def test_malformed_slots_are_ignored(monkeypatch):
    monkeypatch.setattr(settings, "social_publish_slots", "11:30, ,25:00,nonsense,20:30")
    assert worker._parse_slots(settings.social_publish_slots) == ["11:30", "20:30"]
