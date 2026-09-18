"""The shared publishing ledger + the TW posting slots.

Both guard against re-posting: the ledger stops the same episode going out twice
(the Aug 2026 bug: 24 of 63 Threads posts were duplicates), the slots decide when a
scan runs at all.
"""
from datetime import datetime, timedelta, timezone


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


def test_record_stores_the_post_format(temp_db):
    """The format is what the engagement report groups by; a row without one is 'unknown'."""
    social_ledger.record("threads", "EP905", "m1", "https://tinboker.com/episode/EP905", fmt="episode_thread")
    social_ledger.record("threads", "EP906", "m2", "https://tinboker.com/episode/EP906")
    by_id = {r["episode_id"]: r["format"] for r in social_ledger.list_posted("threads")}
    assert by_id == {"EP905": "episode_thread", "EP906": None}


def test_record_stores_the_subject_for_the_rotation_cooldown(temp_db):
    social_ledger.record("threads", "weekly_movers:2026-09-07", "m1", "", fmt="weekly_movers", subject="2026-09-07")
    row = social_ledger.list_posted("threads")[0]
    assert (row["format"], row["subject"]) == ("weekly_movers", "2026-09-07")


def test_list_posted_window_excludes_older_rows(temp_db):
    social_ledger.record("threads", "EP907", "m1", "https://tinboker.com/episode/EP907")
    assert [r["episode_id"] for r in social_ledger.list_posted("threads", days=1)] == ["EP907"]
    # Nothing was posted more than a day before "now" on a fresh DB, so a zero-wide
    # window past the row's timestamp must be empty.
    from datetime import datetime as _dt
    from src.database.models import SocialPostLedger
    from src.database.postgres import session_scope
    with session_scope() as db:
        db.get(SocialPostLedger, ("threads", "EP907")).posted_at = _dt(2020, 1, 1)
    assert social_ledger.list_posted("threads", days=1) == []


def test_record_without_a_claim_still_writes(temp_db):
    """The admin publish path records directly; it must not need a prior claim."""
    social_ledger.record("facebook", "EP904", "post_1", "https://tinboker.com/episode/EP904")
    assert social_ledger.already_posted("facebook", "EP904") is True


# ── posting slots ────────────────────────────────────────────────────

def test_no_slots_configured_means_never_post(monkeypatch):
    monkeypatch.setattr(settings, "social_publish_slots", "")
    assert worker._due_slots(datetime(2026, 8, 26, 23, 0, tzinfo=TW)) == []


def test_only_slots_already_reached_today_are_due(monkeypatch):
    monkeypatch.setattr(settings, "social_publish_slots", "11:30,15:30,20:30")
    due = worker._due_slots(datetime(2026, 8, 26, 16, 0, tzinfo=TW))
    assert due == ["2026-08-26 11:30", "2026-08-26 15:30"]


def test_a_slot_is_claimed_once_ever_even_across_a_restart(temp_db, monkeypatch):
    """The 2026-09-17 22:23 post: a deploy wiped the in-memory set and the 20:30 slot
    re-fired. The claim now lives in the ledger, so a fresh process sees it as taken."""
    monkeypatch.setattr(settings, "social_publish_slots", "11:30")
    now = datetime(2026, 8, 26, 12, 0, tzinfo=TW)
    due = worker._due_slots(now)
    assert due == ["2026-08-26 11:30"]
    assert worker._claim_slots(due) == ["2026-08-26 11:30"]
    assert worker._claim_slots(worker._due_slots(now)) == []                # same process, later tick
    assert worker._claim_slots(worker._due_slots(now)) == []                # "after a restart": still taken
    # …and tomorrow's slot is a new key.
    assert worker._claim_slots(worker._due_slots(now + timedelta(days=1))) == ["2026-08-27 11:30"]


def test_malformed_slots_are_ignored(monkeypatch):
    monkeypatch.setattr(settings, "social_publish_slots", "11:30, ,25:00,nonsense,20:30")
    assert worker._parse_slots(settings.social_publish_slots) == ["11:30", "20:30"]
