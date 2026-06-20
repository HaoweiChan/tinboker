"""Unit tests for the Facebook publisher: post composition (album/photo/text +
comment chain), idempotency, recency, and the dry-run guarantee. No network or
real Facebook credentials are touched — FacebookService is unconfigured in tests,
which forces dry-run."""
from datetime import datetime

import pytest

from src.config import settings
from src.models.podcast import Episode
from src.services import facebook_publisher as fbp


def _now_ms() -> int:
    return int(datetime.utcnow().timestamp() * 1000)


def _cards():
    return [
        {"kind": "cover", "title": "股癌", "bullets": ["要點"], "image_url": "https://c/0.png"},
        {"kind": "theme", "title": "主題A", "bullets": ["重點1 [01:07]"], "image_url": "https://c/1.png"},
        {"kind": "theme", "title": "主題B", "bullets": ["重點2 [02:00]"], "image_url": "https://c/2.png"},
    ]


def _ep(ep_id, cards=None, **kw) -> Episode:
    return Episode(
        id=ep_id, podcast_name="股癌", episode_title="本集重點",
        key_insights=["洞見"], social_cards=cards if cards is not None else _cards(),
        related_tickers=["2330"], created_time=_now_ms(),
        released_at_ms=kw.get("released_ms", _now_ms()),
    )


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_path", str(tmp_path / "test.db"))
    yield


class _FakeFB:
    def __init__(self, configured=True):
        self.is_configured = configured
        self.calls = []
        self._n = 0

    def _id(self, p):
        self._n += 1
        return f"{p}{self._n}"

    async def publish_album(self, message, image_urls):
        self.calls.append(("album", tuple(image_urls)))
        return self._id("post")

    async def publish_photo(self, message, image_url):
        self.calls.append(("photo", image_url))
        return self._id("post")

    async def publish_text(self, message):
        self.calls.append(("text", None))
        return self._id("post")

    async def comment(self, post_id, message, image_url=None):
        self.calls.append(("comment", post_id, message))
        return self._id("cmt")


# ── compose mapping → album + comment chain ──────────────────────────

@pytest.mark.asyncio
async def test_publish_thread_album_then_comments():
    fake = _FakeFB()
    draft = facebook_thread()
    res = await fbp.publish_thread(fake, draft)
    assert res["root_post_id"] == "post1"
    assert res["image_count"] == 3 and res["comment_count"] == 2
    # An album for the carousel images, then one comment per theme card.
    assert fake.calls[0] == ("album", ("https://c/0.png", "https://c/1.png", "https://c/2.png"))
    assert [c[0] for c in fake.calls[1:]] == ["comment", "comment"]
    # Comments hang off the root post (FB is flat, unlike the Threads reply chain).
    assert all(c[1] == "post1" for c in fake.calls[1:])


@pytest.mark.asyncio
async def test_publish_thread_single_photo_when_one_image():
    fake = _FakeFB()
    draft = {"episode_id": "E", "main_text": "hi", "image_urls": ["https://c/0.png"], "replies": []}
    res = await fbp.publish_thread(fake, draft)
    assert fake.calls[0][0] == "photo"
    assert res["comment_count"] == 0


@pytest.mark.asyncio
async def test_publish_thread_text_when_no_images():
    fake = _FakeFB()
    draft = {"episode_id": "E", "main_text": "hi", "image_urls": [], "replies": [{"text": "a"}]}
    await fbp.publish_thread(fake, draft)
    assert fake.calls[0][0] == "text"


def facebook_thread() -> dict:
    from src.services.threads_publisher import compose_thread
    return compose_thread(_ep("EP700"))


# ── publish_recent: dry-run + idempotency ────────────────────────────

@pytest.mark.asyncio
async def test_publish_recent_dry_run_when_unconfigured(temp_db, monkeypatch):
    monkeypatch.setattr(fbp, "FacebookService", lambda: _FakeFB(configured=False))
    monkeypatch.setattr(fbp.podcast_service, "get_recent_episodes",
                        _aret([_ep("EP701")]))
    out = await fbp.publish_recent(dry_run=False)  # forced to dry-run (unconfigured)
    assert out["platform"] == "facebook"
    assert out["dry_run"] is True and out["posted_count"] == 0
    assert out["posted"] and out["posted"][0]["dry_run"] is True


@pytest.mark.asyncio
async def test_publish_recent_records_and_is_idempotent(temp_db, monkeypatch):
    fake = _FakeFB()
    monkeypatch.setattr(fbp, "FacebookService", lambda: fake)
    monkeypatch.setattr(fbp.podcast_service, "get_recent_episodes", _aret([_ep("EP702")]))
    out = await fbp.publish_recent(dry_run=False)
    assert out["posted_count"] == 1
    assert fbp.already_posted("EP702")
    # Second run skips the already-posted episode.
    out2 = await fbp.publish_recent(dry_run=False)
    assert out2["posted_count"] == 0
    assert any(s["reason"] == "already_posted" for s in out2["skipped"])


def _aret(value):
    async def _f(*a, **k):
        return value
    return _f


# ── publish_episode (single explicit episode — the admin 發佈 button) ──────────


@pytest.mark.asyncio
async def test_publish_episode_dry_run_when_unconfigured(temp_db, monkeypatch):
    monkeypatch.setattr(fbp, "FacebookService", lambda: _FakeFB(configured=False))
    res = await fbp.publish_episode(_ep("EP800"), dry_run=False)
    assert res["configured"] is False
    assert res["dry_run"] is True
    assert res["posted"] is False
    assert res["reason"] == "dry_run"
    assert fbp.already_posted("EP800") is False  # dry-run never records


@pytest.mark.asyncio
async def test_publish_episode_publishes_and_is_idempotent(temp_db, monkeypatch):
    fake = _FakeFB()
    monkeypatch.setattr(fbp, "FacebookService", lambda: fake)

    res = await fbp.publish_episode(_ep("EP801"), dry_run=False)
    assert res["posted"] is True
    assert res["comment_count"] == 2
    assert fake.calls[0][0] == "album"
    assert fbp.already_posted("EP801") is True

    again = await fbp.publish_episode(_ep("EP801"), dry_run=False)
    assert again["posted"] is False
    assert again["reason"] == "already_posted"


@pytest.mark.asyncio
async def test_publish_episode_skips_when_no_content(temp_db):
    ep = Episode(id="EP802", podcast_name="股癌", episode_title="", key_insights=[],
                 created_time=_now_ms(), released_at_ms=_now_ms())
    res = await fbp.publish_episode(ep, dry_run=False)
    assert res["posted"] is False
    assert res["reason"] == "no_postable_content"
