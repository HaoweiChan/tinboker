"""Unit tests for the Threads publisher: post composition, idempotency, recency,
and the dry-run guarantee. No network or real Threads credentials are touched —
ThreadsService is unconfigured in tests, which forces dry-run.
"""
import urllib.parse
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


def test_compose_post_drops_svg_image():
    # Meta can't ingest SVG — the draft must degrade to text-only, not carry the SVG.
    ep = _ep("EP210", insights=["重點"])
    ep.summary_image_public_url = "https://x/EP210.svg"
    draft = threads_publisher.compose_post(ep)
    assert draft["image_url"] is None


# ── idempotency ledger ───────────────────────────────────────────────

def test_ledger_record_and_list(temp_db):
    assert threads_publisher.already_posted("EP300") is False
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
    threads_publisher._record("EP500", "m", "u")  # pretend already posted

    result = await threads_publisher.publish_recent(limit=10, dry_run=True, max_age_days=4)
    reasons = {s["episode_id"]: s["reason"] for s in result["skipped"]}
    assert reasons["EP500"] == "already_posted"
    assert reasons["EP501"] == "outside_recency_window"
    assert reasons["EP502"] == "no_postable_content"
    assert result["posted"] == []


@pytest.mark.asyncio
async def test_publish_recent_posts_at_most_max_posts_per_call(temp_db, monkeypatch):
    """One carousel per slot: the newest goes out, the rest stay unrecorded so the
    next slot picks them up — not lost, not posted back to back."""
    eps = [_ep("EP600", insights=["一"]), _ep("EP601", insights=["二"]), _ep("EP602", insights=["三"])]
    monkeypatch.setattr(threads_publisher.podcast_service, "get_recent_episodes", await _fake_recent(eps))
    monkeypatch.setattr(settings, "threads_access_token", None)
    monkeypatch.setattr(settings, "threads_user_id", None)

    result = await threads_publisher.publish_recent(limit=10, dry_run=True, max_posts=1)
    assert [p["episode_id"] for p in result["posted"]] == ["EP600"]
    assert {s["episode_id"]: s["reason"] for s in result["skipped"]} == {"EP601": "slot_full", "EP602": "slot_full"}
    assert threads_publisher.already_posted("EP601") is False

    # No cap (the admin endpoint) behaves as before.
    assert len((await threads_publisher.publish_recent(limit=10, dry_run=True))["posted"]) == 3


def test_posted_links_carry_the_format_as_a_utm_campaign_and_the_ledger_url_stays_bare():
    assert threads_publisher.link_comment("EP1", "episode_text") == (
        "▶ 完整重點：https://tinboker.com/episode/EP1?utm_source=threads&utm_medium=social&utm_campaign=episode_text")
    assert threads_publisher.social_link("https://tinboker.com/x?a=1", "post_hoc_up").endswith("?a=1&utm_source=threads&utm_medium=social&utm_campaign=post_hoc_up")
    assert "utm_" not in threads_publisher.episode_url("EP1")


def test_link_reply_says_what_is_behind_it_and_lands_on_the_section():
    text = threads_publisher.link_comment("EP1", "episode_thread", hook="他點名的三檔封測和理由", focus_ms=1028093)
    assert text == ("▶ 他點名的三檔封測和理由\n"
                    "https://tinboker.com/episode/EP1?t=1028093&utm_source=threads&utm_medium=social&utm_campaign=episode_thread")
    # No hook → the old line; an ordinal-sized or missing offset → no ?t=.
    assert threads_publisher.link_comment("EP1", "episode_text", focus_ms=3).startswith("▶ 完整重點：https://tinboker.com/episode/EP1?utm_source")

    ep = _ep("EP2", insights=["x"], tickers=["2330", "NVDA", "3324"])
    ep.social_thread = {"post": "p", "comments": [], "link_hook": "12個票委各自的說法", "focus_ms": 45000}
    assert threads_publisher.episode_link_comment(ep, "episode_thread").startswith("▶ 12個票委各自的說法\nhttps://tinboker.com/episode/EP2?t=45000&utm_")
    assert threads_publisher.compose_thread(ep)["replies"][0]["text"].startswith("▶ 12個票委各自的說法\n")


# ── zero-ticker one-liner ─────────────────────────────────────────────

def test_pick_insight_prefers_a_number_then_a_screen_sized_line():
    assert threads_publisher.pick_insight(["實質利率才是金價天敵 非美元或名目利率", "金價今年重挫 30% 但央行買盤一噸未少"]) \
        == "金價今年重挫 30% 但央行買盤一噸未少"
    # No number anywhere: the first screen-sized line wins.
    assert threads_publisher.pick_insight(["實質利率才是金價天敵", "央行買盤一噸未少"]) == "實質利率才是金價天敵"
    long = "聯準會升息一碼至3.75%-4.0%，點陣圖暗示年底前可能再升一碼，且市場對此反應平淡，顯示已充分定價"
    assert threads_publisher.pick_insight([long, "8月零售銷售控制組躍增1.4%"]) == "8月零售銷售控制組躍增1.4%"
    assert threads_publisher.pick_insight(["", "  ", None]) == ""


def test_compose_text_post_is_the_written_post_and_the_link_goes_in_the_reply():
    ep = _ep("EP700", insights=["實質利率才是金價天敵"], tickers=[])
    ep.social_thread = {"post": "加州柴油一加侖衝到快 10 美元\n這數字比原油破百嚴重得多", "comments": [{"heading": "a", "text": "x"}]}
    draft = threads_publisher.compose_text_post(ep)
    assert draft["text"] == "加州柴油一加侖衝到快 10 美元\n這數字比原油破百嚴重得多"   # no count line, no comments
    assert "tinboker.com" not in draft["text"] and draft["url"].endswith("/episode/EP700")


def _claims():
    return [
        {"indicator_id": "US_CPI", "claim": "通膨黏著", "level_quoted": None, "confidence": 0.95},
        {"indicator_id": "US10Y", "claim": "財政部擴大回購長債，殖利率反而衝到4.94%", "level_quoted": "4.94%", "confidence": 0.9},
        {"indicator_id": "BEEF", "claim": "牛肉漲七成", "level_quoted": "七成", "confidence": 0.99},   # no series → no card
    ]


def test_pick_macro_claim_wants_a_series_and_a_quoted_number_before_confidence():
    assert threads_publisher.pick_macro_claim(_claims())["indicator_id"] == "US10Y"
    assert threads_publisher.pick_macro_claim([{"indicator_id": "BEEF", "claim": "x"}]) is None
    assert threads_publisher.pick_macro_claim([]) is None


def test_compose_text_post_carries_the_macro_card_marked_on_the_air_date(monkeypatch):
    monkeypatch.setattr(settings, "public_api_url", "https://api.tinboker.com")
    from datetime import timezone
    aired = datetime(2026, 9, 14, 8, 40, tzinfo=timezone(timedelta(hours=8)))       # a TW morning show
    ep = _ep("EP704", insights=["x"], tickers=[], released_ms=int(aired.timestamp() * 1000))
    ep.podcast_name = "游庭皓的財經皓角"
    ep.social_thread = {"post": "加州柴油一加侖衝到快10美元", "comments": []}
    ep.macro_claims = _claims()
    draft = threads_publisher.compose_text_post(ep)
    assert draft["image_url"].startswith("https://api.tinboker.com/api/og/macro/US10Y.png?")
    q = dict(urllib.parse.parse_qsl(draft["image_url"].split("?", 1)[1]))
    assert q == {"event": "2026-09-14", "label": "皓哥 9/14", "claim": "財政部擴大回購長債，殖利率反而衝到4.94%"}
    assert draft["text"] == "加州柴油一加侖衝到快10美元"
    ep.macro_claims = []
    assert threads_publisher.compose_text_post(ep)["image_url"] is None


def test_compose_text_post_falls_back_to_speaker_plus_one_insight():
    ep = _ep("EP703", insights=["實質利率才是金價天敵", "央行買盤一噸未少"], tickers=[])
    ep.podcast_name = "財經一路發"
    assert threads_publisher.compose_text_post(ep)["text"] == "一路發這集\n實質利率才是金價天敵"


@pytest.mark.asyncio
async def test_publish_recent_posts_a_zero_ticker_episode_as_text(temp_db, monkeypatch):
    from src.services import social_ledger

    class _Svc:
        is_configured = True

        def __init__(self, *a, **k):
            pass

        calls: list = []

        async def publish(self, text, image_url=None):
            self.calls.append(("post", text, image_url))
            return f"m{len(self.calls)}"

        async def publish_reply(self, text, reply_to_id, **_):
            self.calls.append(("reply", text, reply_to_id))
            return "r_link"
    monkeypatch.setattr(threads_publisher, "ThreadsService", _Svc)
    eps = [_ep("EP701", insights=["AI 監管會讓算力需求再多 15%"], tickers=[]),
           _ep("EP702", insights=["有標的的照舊"], tickers=["2330", "NVDA", "3324"])]
    eps[0].social_thread = {"post": "孟恭這集\n講的是算力", "comments": []}
    eps[0].macro_claims = [{"indicator_id": "FED_FUNDS", "claim": "升息機率八成", "level_quoted": "80%", "confidence": 0.9}]
    monkeypatch.setattr(threads_publisher.podcast_service, "get_recent_episodes", await _fake_recent(eps))

    result = await threads_publisher.publish_recent(limit=10, dry_run=False)
    kinds = {p["episode_id"]: p.get("kind") for p in result["posted"]}
    assert kinds["EP701"] == "text" and kinds["EP702"] is None
    one = [c for c in _Svc.calls if c[0] == "post" and c[1].startswith("孟恭這集\n")]
    assert len(one) == 1 and "/api/og/macro/FED_FUNDS.png?" in one[0][2]   # the macro card rides along
    assert any(c[0] == "reply" and "tinboker.com/episode/EP701" in c[1] for c in _Svc.calls)
    row = next(r for r in social_ledger.list_posted("threads") if r["episode_id"] == "EP701")
    assert (row["format"], row["child_ids"]) == ("episode_macro_card", ["r_link"])


# ── 1–2 tickers: the story of the call on its marked chart ───────────────

def test_is_low_ticker_means_one_or_two():
    assert not threads_publisher.is_low_ticker(_ep("a", tickers=[]))
    assert threads_publisher.is_low_ticker(_ep("b", tickers=["2330"]))
    assert threads_publisher.is_low_ticker(_ep("c", tickers=["2330", "NVDA"]))
    assert not threads_publisher.is_low_ticker(_ep("d", tickers=["2330", "NVDA", "3324"]))


def test_compose_ticker_story_frames_the_first_ticker_on_its_air_date(monkeypatch):
    from datetime import timezone
    monkeypatch.setattr(settings, "public_api_url", "https://api.tinboker.com")
    aired = datetime(2026, 9, 17, 20, 5, tzinfo=timezone(timedelta(hours=8)))
    ep = _ep("EP710", insights=["x"], tickers=["3324", "3017"], released_ms=int(aired.timestamp() * 1000))
    ep.podcast_name = "兆華與股惑仔"
    frame = threads_publisher.compose_ticker_story(ep)
    assert frame["ticker"] == "3324" and frame["mention_date"] == "2026-09-17"
    q = dict(urllib.parse.parse_qsl(frame["image_url"].split("?", 1)[1]))
    assert frame["image_url"].startswith("https://api.tinboker.com/api/og/stock/3324.png?")
    assert q == {"days": "60", "event": "2026-09-17", "label": "兆華 9/17"}
    assert frame["url"].endswith("/episode/EP710")


@pytest.mark.asyncio
async def test_publish_recent_posts_a_low_ticker_episode_as_a_story_or_falls_back(temp_db, monkeypatch):
    from src.services import social_formats, social_ledger

    class _Svc:
        is_configured = True
        calls: list = []

        def __init__(self, *a, **k):
            pass

        async def publish(self, text, image_url=None):
            self.calls.append(("post", text, image_url))
            return f"m{len(self.calls)}"

        async def publish_reply(self, text, reply_to_id, **_):
            self.calls.append(("reply", text, reply_to_id))
            return "r_link"

        async def publish_carousel(self, image_urls, text):
            self.calls.append(("carousel", text, image_urls))
            return "m_car"
    monkeypatch.setattr(threads_publisher, "ThreadsService", _Svc)
    monkeypatch.setattr(threads_publisher, "_ticker_name", lambda t: "雙鴻")
    asked = []

    async def story(c, mode="post_hoc"):
        asked.append({**c, "mode": mode})
        return "兆華這集講到雙鴻\n他在意的是散熱族群整齊發動" if c["ticker"] == "3324" else None
    monkeypatch.setattr(social_formats, "_story", story)

    eps = [_ep("EP711", insights=["一"], tickers=["3324"]),
           _ep("EP712", insights=["二"], tickers=["2330"])]       # the pipeline has no story for this one
    monkeypatch.setattr(threads_publisher.podcast_service, "get_recent_episodes", await _fake_recent(eps))

    result = await threads_publisher.publish_recent(limit=10, dry_run=False)
    kinds = {p["episode_id"]: p.get("kind") for p in result["posted"]}
    assert kinds == {"EP711": "ticker_story", "EP712": None}          # EP712 took the old path
    assert [(a["episode_id"], a["mode"], a["name"]) for a in asked] == [("EP711", "today", "雙鴻"), ("EP712", "today", "雙鴻")]
    post = next(c for c in _Svc.calls if c[0] == "post" and c[1].startswith("兆華這集講到雙鴻"))
    assert "/api/og/stock/3324.png?" in post[2]
    rows = {r["episode_id"]: r["format"] for r in social_ledger.list_posted("threads")}
    assert rows["EP711"] == "episode_ticker_story" and rows["EP712"] == "episode_single"

    # Dry run never spends the LLM call.
    asked.clear()
    eps.append(_ep("EP713", insights=["三"], tickers=["2454"]))
    dry = await threads_publisher.publish_recent(limit=10, dry_run=True)
    assert asked == [] and [p["kind"] for p in dry["posted"]] == ["ticker_story"] and dry["posted"][0]["dry_run"]


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
        # A card deck implies several stocks; 0 routes to the text post, 1–2 to the story.
        related_tickers=kw.get("tickers", ["2330", "NVDA", "3324"]),
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
    assert draft["replies"][0]["text"] == threads_publisher.link_comment("EP600", "episode_thread")
    assert [r["text"].splitlines()[0] for r in draft["replies"][1:]] == ["【主題A】", "【主題B】"]
    assert "重點1 [01:07]" in draft["replies"][1]["text"]
    assert all(len(r["text"]) <= THREADS_MAX_CHARS for r in draft["replies"])


def test_compose_thread_drops_svg_card_images():
    cards = [
        {"kind": "cover", "image_url": "https://c/0.svg"},
        {"kind": "theme", "title": "A", "bullets": ["x"], "image_url": "https://c/1.png"},
    ]
    draft = threads_publisher.compose_thread(_ep_cards("EP620", cards))
    assert draft["image_urls"] == ["https://c/1.png"]  # .svg dropped


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
    assert draft["replies"][0]["text"] == threads_publisher.link_comment("EP610", "episode_thread")
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
async def test_publish_episode_uses_thread_when_human_copy_without_cards(temp_db):
    # Episode has hand-authored social copy but NO rendered cards: it must publish via
    # the thread composer (human post + link comment + comments), not the mechanical
    # single-post path. Unconfigured creds force dry-run; we assert which composer ran.
    ep = _ep("EP630", insights=["機械重點"])
    ep.social_thread = {"post": "人工總結", "comments": [{"text": "留言一"}]}
    res = await threads_publisher.publish_episode(ep, dry_run=True)
    assert res["reason"] == "dry_run"
    assert res["main_text"].startswith("人工總結")  # human copy, not the key_insights body
    assert res["reply_count"] == 2  # link comment + 1 human comment


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


# ── per-show social kill switch (content_sources.social_enabled) ──────

@pytest.mark.asyncio
async def test_publish_skips_shows_with_social_disabled(temp_db, monkeypatch):
    """A muted show is skipped by both the batch scan and the admin 發佈 button."""
    monkeypatch.setattr(
        threads_publisher, "social_enabled_for", lambda name: name != "財經一路發"
    )
    muted = _ep("EP900", insights=["重點"])
    muted.podcast_name = "財經一路發"
    allowed = _ep("EP901", insights=["重點"])  # 股癌
    monkeypatch.setattr(
        threads_publisher.podcast_service, "get_recent_episodes", await _fake_recent([muted, allowed])
    )

    batch = await threads_publisher.publish_recent(limit=10, dry_run=True)
    reasons = {s["episode_id"]: s["reason"] for s in batch["skipped"]}
    assert reasons["EP900"] == "social_disabled_for_show"
    assert [p["episode_id"] for p in batch["posted"]] == ["EP901"]

    single = await threads_publisher.publish_episode(muted, dry_run=False)
    assert single["posted"] is False
    assert single["reason"] == "social_disabled_for_show"
