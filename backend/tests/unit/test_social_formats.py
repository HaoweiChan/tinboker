"""The post-shape rotation: which format a slot gets, and the cooldowns that stop the
same shape or the same subject going out again too soon."""
from datetime import datetime, timedelta

import pytest

from src.services import social_formats as sf
from src.services import social_ledger
from src.services.threads_service import THREADS_MAX_CHARS

NOW = datetime(2026, 9, 17, 3, 30)


def _row(fmt, subject=None, days_ago=0.0):
    return {"format": fmt, "subject": subject, "posted_at": (NOW - timedelta(days=days_ago)).isoformat()}


async def _quiet():
    return None


def _fmt(id_="weekly_movers", cooldown=6, subject_cooldown=6, select=_quiet):
    return sf.Format(id_, select, cooldown_days=cooldown, subject_cooldown_days=subject_cooldown)


# ── cooldowns (pure) ─────────────────────────────────────────────────────────

def test_same_format_inside_cooldown_is_blocked_outside_is_not():
    f = _fmt(cooldown=6)
    assert sf.format_off_cooldown(f, [_row("weekly_movers", days_ago=2)], NOW) is False
    assert sf.format_off_cooldown(f, [_row("weekly_movers", days_ago=7)], NOW) is True


def test_episode_rows_never_count_against_another_format():
    f = _fmt()
    assert sf.format_off_cooldown(f, [_row("episode_thread", days_ago=0.1)], NOW) is True


def test_same_subject_in_any_format_is_blocked():
    """欣興 five times in three days is what this guards — regardless of which shape said it."""
    f = _fmt("post_hoc_winner", subject_cooldown=7)
    recent = [_row("divergence", subject="3037", days_ago=3)]
    assert sf.subject_off_cooldown(f, "3037", recent, NOW) is False
    assert sf.subject_off_cooldown(f, "2330", recent, NOW) is True
    assert sf.subject_off_cooldown(f, None, recent, NOW) is True


# ── caption ──────────────────────────────────────────────────────────────────

def test_weekly_caption_lists_top_three_and_says_what_the_number_is():
    data = {"rows": [
        {"ticker": "3037", "name": "欣興", "n": 31, "prev": 4},
        {"ticker": "8299", "name": "群聯", "n": 18, "prev": 2},
        {"ticker": "2330", "name": "台積電", "n": 60, "prev": 45},
        {"ticker": "3006", "name": "晶豪科", "n": 9, "prev": 0},
    ]}
    text = sf.weekly_movers_text(data)
    assert "3037 欣興 31 次 上週 4" in text
    assert "3006" not in text
    assert "不是漲幅" in text
    assert "我" not in text and "#" not in text
    assert len(text) <= THREADS_MAX_CHARS


# ── the slot, end to end against the ledger ──────────────────────────────────

class _FakeThreads:
    is_configured = True

    def __init__(self):
        self.posts, self.replies = [], []

    async def publish(self, text, image_url=None):
        self.posts.append((text, image_url))
        return f"m{len(self.posts)}"

    async def publish_reply(self, text, reply_to_id, **_):
        self.replies.append((text, reply_to_id))
        return f"r{len(self.replies)}"


@pytest.mark.asyncio
async def test_slot_posts_the_first_format_with_material_then_cools_down(temp_db, monkeypatch):
    fake = _FakeThreads()
    monkeypatch.setattr(sf, "ThreadsService", lambda: fake)

    async def movers():
        return {"key": "weekly_movers:2026-09-07", "subject": "2026-09-07", "text": "本週",
                "image_url": "https://api.tinboker.com/api/og/weekly.png",
                "url": "https://tinboker.com/weekly/2026-W37"}
    monkeypatch.setattr(sf, "FORMATS", [_fmt("quiet_first", select=_quiet), _fmt("weekly_movers", select=movers)])

    res = await sf.publish_due_format(now=NOW)
    assert res["posted"] is True and res["format"] == "weekly_movers"
    assert fake.posts == [("本週", "https://api.tinboker.com/api/og/weekly.png")]
    assert fake.replies == [("▶ https://tinboker.com/weekly/2026-W37", "m1")]
    row = social_ledger.list_posted("threads")[0]
    assert (row["episode_id"], row["format"], row["subject"], row["child_ids"]) == \
        ("weekly_movers:2026-09-07", "weekly_movers", "2026-09-07", ["r1"])

    # Same slot tomorrow: the format is cooling down, nothing goes out.
    assert await sf.publish_due_format(now=datetime.utcnow()) is None
    assert len(fake.posts) == 1


@pytest.mark.asyncio
async def test_a_failed_publish_releases_the_key_for_the_next_slot(temp_db, monkeypatch):
    from src.services.threads_service import ThreadsError

    class Boom(_FakeThreads):
        async def publish(self, *_a, **_k):
            raise ThreadsError("500")
    monkeypatch.setattr(sf, "ThreadsService", lambda: Boom())

    async def movers():
        return {"key": "weekly_movers:2026-09-07", "subject": "2026-09-07", "text": "本週"}
    monkeypatch.setattr(sf, "FORMATS", [_fmt(select=movers)])

    res = await sf.publish_due_format(now=NOW)
    assert res["posted"] is False and res["reason"].startswith("publish_failed")
    assert social_ledger.already_posted("threads", "weekly_movers:2026-09-07") is False


@pytest.mark.asyncio
async def test_unconfigured_threads_means_dry_run(monkeypatch, temp_db):
    class Off(_FakeThreads):
        is_configured = False
    monkeypatch.setattr(sf, "ThreadsService", lambda: Off())

    async def movers():
        return {"key": "k", "subject": "s", "text": "t"}
    monkeypatch.setattr(sf, "FORMATS", [_fmt(select=movers)])
    res = await sf.publish_due_format(now=NOW)
    assert res == {"format": "weekly_movers", "key": "k", "subject": "s", "text": "t",
                   "posted": False, "dry_run": True}
