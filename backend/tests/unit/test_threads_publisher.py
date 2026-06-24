"""Unit tests for the Threads publisher: post composition, idempotency, recency,
and the dry-run guarantee. No network or real Threads credentials are touched —
ThreadsService is unconfigured in tests, which forces dry-run.
"""
from datetime import datetime, timedelta

import pytest

from src.config import settings
from src.models.podcast import Episode
from src.services import threads_publisher
from src.services.threads_service import THREADS_MAX_CHARS


def _now_ms() -> int:
    return int(datetime.utcnow().timestamp() * 1000)


def _ep(ep_id: str, *, title="本集重點", insights=None, tickers=None, released_ms=None) -> Episode:
    return Episode(
        id=ep_id,
        podcast_name="股癌",
        episode_title=title,
        key_insights=insights or [],
        related_tickers=tickers or [],
        created_time=released_ms or _now_ms(),
        released_at_ms=released_ms or _now_ms(),
        summary_image_public_url=f"https://cdn.tinboker.com/{ep_id}.png",
    )


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point the SQLite store at a throwaway file so the ledger tests are isolated."""
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "test.db"))
    yield


# ── compose_post ─────────────────────────────────────────────────────

def test_compose_post_includes_link_and_insights_no_hashtags():
    ep = _ep("EP200", insights=["台積電法說會優於預期", "AI 需求續強"], tickers=["2330", "NVDA"])
    draft = threads_publisher.compose_post(ep)

    assert draft["episode_id"] == "EP200"
    # Standalone single-post path keeps the link in the body (no comment channel).
    assert "tinboker.com/episode/EP200" in draft["text"]
    assert "台積電法說會優於預期" in draft["text"]
    # No auto hashtags anywhere.
    assert "#" not in draft["text"]
    assert draft["image_url"] == "https://cdn.tinboker.com/EP200.png"


def test_compose_post_respects_500_char_limit():
    long_insights = ["這是一段很長的重點內容用來測試字數上限" * 10 for _ in range(8)]
    ep = _ep("EP201", insights=long_insights, tickers=["2330", "2317", "2454", "NVDA", "AAPL"])
    draft = threads_publisher.compose_post(ep)
    assert len(draft["text"]) <= THREADS_MAX_CHARS
    # Even when trimmed, the permalink must survive (it's the SEO/referral payload).
    assert "tinboker.com/episode/EP201" in draft["text"]


def test_compose_post_with_no_insights_falls_back_to_header():
    ep = _ep("EP202", title="只有標題", insights=[])
    draft = threads_publisher.compose_post(ep)
    assert "只有標題" in draft["text"]
    assert "tinboker.com/episode/EP202" in draft["text"]


# ── idempotency ledger ───────────────────────────────────────────────

def test_ledger_record_and_list(temp_db):
    assert threads_publisher.already_posted("EP300") is False
    threads_publisher._ensure_table()
    threads_publisher._record("EP300", "media_123", "https://tinboker.com/episode/EP300")
    assert threads_publisher.already_posted("EP300") is True
    posts = threads_publisher.list_posted()
    assert posts[0]["episode_id"] == "EP300"
    assert posts[0]["media_id"] == "media_123"


# ── publish_recent orchestration ─────────────────────────────────────

async def _fake_recent(episodes):
    async def _inner(*args, **kwargs):
        return episodes
    return _inner


@pytest.mark.asyncio
async def test_publish_recent_dry_run_when_unconfigured(temp_db, monkeypatch):
    eps = [_ep("EP400", insights=["重點一"]), _ep("EP401", insights=["重點二"])]
    monkeypatch.setattr(
        threads_publisher.podcast_service, "get_recent_episodes", await _fake_recent(eps)
    )
    # Credentials unset -> forced dry-run, nothing published or recorded.
    monkeypatch.setattr(settings, "threads_access_token", None)
    monkeypatch.setattr(settings, "threads_user_id", None)

    result = await threads_publisher.publish_recent(limit=10, dry_run=False)
    assert result["configured"] is False
    assert result["dry_run"] is True
    assert result["posted_count"] == 0
    assert {p["episode_id"] for p in result["posted"]} == {"EP400", "EP401"}
    assert threads_publisher.already_posted("EP400") is False  # dry-run never records


@pytest.mark.asyncio
async def test_publish_recent_skips_already_posted_and_old(temp_db, monkeypatch):
    old_ms = int((datetime.utcnow() - timedelta(days=30)).timestamp() * 1000)
    eps = [
        _ep("EP500", insights=["新"]),                       # fresh -> candidate
        _ep("EP501", insights=["舊"], released_ms=old_ms),   # too old -> skipped
        _ep("EP502", insights=[], title=""),                 # nothing to post -> skipped
    ]
    monkeypatch.setattr(
        threads_publisher.podcast_service, "get_recent_episodes", await _fake_recent(eps)
    )
    threads_publisher._ensure_table()
    threads_publisher._record("EP500", "m", "u")  # pretend already posted

    result = await threads_publisher.publish_recent(limit=10, dry_run=True, max_age_days=4)
    reasons = {s["episode_id"]: s["reason"] for s in result["skipped"]}
    assert reasons["EP500"] == "already_posted"
    assert reasons["EP501"] == "outside_recency_window"
    assert reasons["EP502"] == "no_postable_content"
    assert result["posted"] == []


# ── thread (carousel + reply chain) ──────────────────────────────────

def _cards():
    return [
        {"kind": "cover", "title": "股癌", "bullets": ["要點"], "image_url": "https://c/0.png"},
        {"kind": "theme", "title": "主題A", "bullets": ["重點1 [01:07]", "重點2"], "image_url": "https://c/1.png"},
        {"kind": "theme", "title": "主題B", "bullets": ["重點3 [02:00]"], "image_url": "https://c/2.png"},
    ]


def _ep_cards(ep_id, cards, **kw) -> Episode:
    return Episode(
        id=ep_id, podcast_name="股癌", episode_title="本集重點",
        key_insights=["洞見"], social_cards=cards,
        created_time=_now_ms(), released_at_ms=kw.get("released_ms", _now_ms()),
    )


class _FakeThreads:
    def __init__(self):
        self.is_configured = True
        self.calls = []
        self._n = 0

    def _id(self, prefix):
        self._n += 1
        return f"{prefix}{self._n}"

    async def publish_carousel(self, image_urls, text, **k):
        self.calls.append(("carousel", tuple(image_urls)))
        return self._id("root")

    async def publish(self, text, image_url=None, **k):
        self.calls.append(("single", image_url))
        return self._id("root")

    async def publish_reply(self, text, reply_to_id, **k):
        self.calls.append(("reply", reply_to_id, text))
        return self._id("reply")


def test_compose_thread_carousel_images_and_replies():
    draft = threads_publisher.compose_thread(_ep_cards("EP600", _cards()))
    assert draft["image_urls"] == ["https://c/0.png", "https://c/1.png", "https://c/2.png"]
    assert "2 個重點整理" in draft["main_text"]
    # Link is no longer in the post body — it's the first comment.
    assert "tinboker.com/episode/EP600" not in draft["main_text"]
    assert "#" not in draft["main_text"]
    assert draft["replies"][0]["text"] == "▶ 完整重點：" + threads_publisher.episode_url("EP600")
    assert [r["text"].splitlines()[0] for r in draft["replies"][1:]] == ["【主題A】", "【主題B】"]
    assert "重點1 [01:07]" in draft["replies"][1]["text"]
    assert all(len(r["text"]) <= THREADS_MAX_CHARS for r in draft["replies"])


def test_compose_reply_clamps_and_keeps_whole_bullets():
    long = ["超長重點" * 60, "第二點 [09:99]"]
    text = threads_publisher._compose_reply("標題", long)
    assert len(text) <= THREADS_MAX_CHARS
    assert text.startswith("【標題】")


def test_compose_thread_prefers_human_social_thread():
    ep = _ep_cards("EP610", _cards(), )
    ep.related_tickers = ["2330"]
    ep.social_thread = {
        "post": "這集聊台積電跟離散元件，重點都在下面 👇",
        "comments": [
            {"heading": "主題A", "text": "題材輪動很快，籌碼要顧好。"},
            {"heading": "主題B", "text": "離散元件的缺口慢慢養出來。"},
        ],
    }
    draft = threads_publisher.compose_thread(ep)
    # Human post is the body — no link, no hashtags (link goes in the first comment).
    assert draft["main_text"].startswith("這集聊台積電跟離散元件")
    assert "tinboker.com/episode/EP610" not in draft["main_text"]
    assert "#" not in draft["main_text"]
    # First comment is the permalink; then the human comments verbatim (no scaffolding).
    assert draft["replies"][0]["text"] == "▶ 完整重點：" + threads_publisher.episode_url("EP610")
    assert [r["text"] for r in draft["replies"][1:]] == [
        "題材輪動很快，籌碼要顧好。",
        "離散元件的缺口慢慢養出來。",
    ]
    assert "【" not in draft["replies"][1]["text"]
    # Images still come from the cards.
    assert draft["image_urls"] == ["https://c/0.png", "https://c/1.png", "https://c/2.png"]


def test_compose_thread_falls_back_when_social_thread_empty():
    ep = _ep_cards("EP611", _cards())
    ep.social_thread = {"post": "", "comments": []}
    draft = threads_publisher.compose_thread(ep)
    # Empty thread → link comment first, then mechanical 【title】 + bullets compose.
    assert draft["replies"][0]["text"].startswith("▶ 完整重點：")
    assert [r["text"].splitlines()[0] for r in draft["replies"][1:]] == ["【主題A】", "【主題B】"]


@pytest.mark.asyncio
async def test_publish_thread_carousel_then_reply_chain():
    fake = _FakeThreads()
    draft = threads_publisher.compose_thread(_ep_cards("EP601", _cards()))
    res = await threads_publisher.publish_thread(fake, draft)

    assert res["root_media_id"] == "root1"
    # 3 replies now: the link comment + the 2 theme cards.
    assert res["reply_count"] == 3 and res["image_count"] == 3
    # carousel first, then replies threaded to the previous post id.
    assert fake.calls[0] == ("carousel", ("https://c/0.png", "https://c/1.png", "https://c/2.png"))
    assert fake.calls[1][:2] == ("reply", "root1")     # link comment → carousel root
    assert fake.calls[2][:2] == ("reply", "reply2")    # theme A → link comment
    assert fake.calls[3][:2] == ("reply", "reply3")    # theme B → theme A


@pytest.mark.asyncio
async def test_publish_thread_single_image_when_cover_only():
    fake = _FakeThreads()
    draft = threads_publisher.compose_thread(_ep_cards("EP602", [_cards()[0]]))  # cover only
    res = await threads_publisher.publish_thread(fake, draft)
    assert fake.calls[0][0] == "single"   # 1 image → not a carousel
    # No theme cards, but the link comment is still posted.
    assert res["reply_count"] == 1
    assert fake.calls[1][:2] == ("reply", "root1")
    assert fake.calls[1][2].startswith("▶ 完整重點：")


@pytest.mark.asyncio
async def test_publish_recent_thread_path_records_root_and_replies(temp_db, monkeypatch):
    fake = _FakeThreads()
    monkeypatch.setattr(threads_publisher, "ThreadsService", lambda *a, **k: fake)
    monkeypatch.setattr(settings, "threads_access_token", "tok")
    monkeypatch.setattr(settings, "threads_user_id", "123")
    eps = [_ep_cards("EP700", _cards())]
    monkeypatch.setattr(threads_publisher.podcast_service, "get_recent_episodes", await _fake_recent(eps))

    result = await threads_publisher.publish_recent(limit=5, dry_run=False)
    assert result["posted_count"] == 1
    assert result["posted"][0]["root_media_id"] == "root1"
    assert result["posted"][0]["reply_count"] == 3  # link comment + 2 theme cards
    row = threads_publisher.list_posted()[0]
    assert row["episode_id"] == "EP700" and row["media_id"] == "root1"
    assert row["reply_ids"] == ["reply2", "reply3", "reply4"]

    # Idempotent: a second run skips the already-posted episode.
    again = await threads_publisher.publish_recent(limit=5, dry_run=False)
    assert again["posted_count"] == 0
    assert again["skipped"][0]["reason"] == "already_posted"


# ── publish_episode (single explicit episode — the admin 發佈 button) ──────────


@pytest.mark.asyncio
async def test_publish_episode_dry_run_when_unconfigured(temp_db, monkeypatch):
    # Even with dry_run=False, unconfigured creds force a no-post preview.
    monkeypatch.setattr(settings, "threads_access_token", None)
    monkeypatch.setattr(settings, "threads_user_id", None)
    res = await threads_publisher.publish_episode(_ep_cards("EP800", _cards()), dry_run=False)
    assert res["configured"] is False
    assert res["dry_run"] is True
    assert res["posted"] is False
    assert res["reason"] == "dry_run"
    assert threads_publisher.already_posted("EP800") is False  # dry-run never records


@pytest.mark.asyncio
async def test_publish_episode_publishes_and_is_idempotent(temp_db, monkeypatch):
    fake = _FakeThreads()
    monkeypatch.setattr(threads_publisher, "ThreadsService", lambda *a, **k: fake)
    monkeypatch.setattr(settings, "threads_access_token", "tok")
    monkeypatch.setattr(settings, "threads_user_id", "123")

    res = await threads_publisher.publish_episode(_ep_cards("EP801", _cards()), dry_run=False)
    assert res["posted"] is True
    assert res["root_media_id"] == "root1"
    assert res["reply_count"] == 3  # link comment + 2 theme cards
    assert threads_publisher.already_posted("EP801") is True

    # Second publish of the same episode is a no-op skip (idempotent).
    again = await threads_publisher.publish_episode(_ep_cards("EP801", _cards()), dry_run=False)
    assert again["posted"] is False
    assert again["reason"] == "already_posted"


@pytest.mark.asyncio
async def test_publish_episode_skips_when_no_content(temp_db):
    ep = Episode(id="EP802", podcast_name="股癌", episode_title="", key_insights=[],
                 created_time=_now_ms(), released_at_ms=_now_ms())
    res = await threads_publisher.publish_episode(ep, dry_run=False)
    assert res["posted"] is False
    assert res["reason"] == "no_postable_content"
