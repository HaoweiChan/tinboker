"""The post-shape rotation: which format a slot gets, and the cooldowns that stop the
same shape or the same subject going out again too soon."""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, call

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


# ── post-hoc ─────────────────────────────────────────────────────────────────

def _cand(**kw):
    base = {"ticker": "3324", "name": "雙鴻", "podcaster": "兆華與股惑仔", "sentiment_label": "BULLISH",
            "thesis": "雙鴻受惠散熱族群齊漲，  股價轉強跟上奇鋐與建準漲勢。", "mention_date": "2026-08-31",
            "baseline_close": 1250.0, "last_date": "2026-09-16", "last_close": 1360.0, "pct": 8.8, "others": 1}
    return {**base, **kw}


STORY = "8 月底那天 兆華聊到散熱族群\n盤面上的族群性終於整齊起來\n\n那天他的焦點就停在這個整齊發動的節奏"


def test_post_hoc_caption_is_the_story_then_the_one_line_only_we_can_write():
    text = sf.post_hoc_text(_cand(), STORY)
    assert text.startswith(STORY)
    assert text.endswith("\n\n雙鴻 8/31到9/16漲8.8%")
    assert sf.post_hoc_text(_cand(pct=-12.34), STORY).endswith("雙鴻 8/31到9/16跌12.3%")
    assert "我" not in text and "對了" not in text and "錯了" not in text
    assert len(text) <= THREADS_MAX_CHARS


def _seed_post_hoc(pct_big=12.0, pct_small=3.0, stance="BULLISH"):
    """Two mentions with a thesis and a 5-session return: one moved, one did not."""
    from datetime import datetime as _dt
    from src.database import postgres as pg
    from src.database.models import (ContentMention, StockDailyClose, StockDailyOHLC, StockTranslation,
                                     TickerPerformanceSnapshot)
    from src.database.postgres import session_scope
    for model in (ContentMention, TickerPerformanceSnapshot, StockDailyOHLC, StockDailyClose, StockTranslation):
        model.__table__.create(bind=pg.engine, checkfirst=True)
    with session_scope() as db:
        db.add(StockTranslation(ticker="3324", market="TW", name_zh_tw="雙鴻"))
        for i, (tk, pct) in enumerate((("3324", pct_big), ("2330", pct_small))):
            m = ContentMention(mention_key=f"ep{i}:ticker:{tk}", episode_id=f"ep{i}", mention_type="ticker",
                               ticker=tk, market="TW", podcaster="兆華與股惑仔", extraction_method="pipeline_llm",
                               mentioned_at=_dt.utcnow() - timedelta(days=10), sentiment_label=stance,
                               thesis=f"{tk} 的理由")
            db.add(m)
            db.flush()
            db.add(TickerPerformanceSnapshot(mention_id=m.id, ticker=tk, mention_date="2026-09-07",
                                             baseline_close=100.0, r5d=pct))
            db.add(StockDailyOHLC(ticker=tk, date="2026-09-07", close=100.0))
            db.add(StockDailyOHLC(ticker=tk, date="2026-09-16", close=100.0 + pct))


def test_post_hoc_candidates_rank_by_move_since_mention_and_drop_small_moves(temp_db):
    _seed_post_hoc()
    cands = sf._post_hoc_candidates(None, datetime(2026, 8, 1))
    assert [c["ticker"] for c in cands] == ["3324"]          # 2330 moved 3%, under the floor
    c = cands[0]
    assert c["name"] == "雙鴻" and c["episode_id"] == "ep0" and c["last_date"] == "2026-09-16"
    assert c["pct"] == pytest.approx(12.0) and c["others"] == 0


async def _no_scope():
    return None


@pytest.mark.asyncio
async def test_post_hoc_up_tells_the_story_and_builds_the_marked_card_url(temp_db, monkeypatch):
    from src.services import threads_publisher
    monkeypatch.setattr(threads_publisher.podcast_service, "_allowed_podcast_names", _no_scope)
    asked = {}

    async def story(c):
        asked.update(c)
        return STORY
    monkeypatch.setattr(sf, "_story", story)
    _seed_post_hoc()

    assert await sf.select_post_hoc_down() is None            # nothing fell ≥ 8%
    draft = await sf.select_post_hoc_up()
    assert asked["episode_id"] == "ep0" and asked["thesis"] == "3324 的理由"
    assert draft["key"] == "post_hoc:3324:ep0" and draft["subject"] == "3324"
    assert draft["text"] == STORY + "\n\n雙鴻 9/7到9/16漲12.0%"
    assert draft["image_url"].endswith("/api/og/stock/3324.png?days=60&event=2026-09-07"
                                       "&label=%E5%85%86%E8%8F%AF%E8%88%87%E8%82%A1%E6%83%91%E4%BB%94%209/7")
    assert draft["url"].endswith("/episode/ep0")
    assert draft["link_hook"] == "兆華 9/7那集講雙鴻的段落" and draft["focus_ms"] is None   # seeded mention has no offset


@pytest.mark.asyncio
async def test_post_hoc_down_is_its_own_format_and_no_story_means_no_post(temp_db, monkeypatch):
    from src.services import threads_publisher
    monkeypatch.setattr(threads_publisher.podcast_service, "_allowed_podcast_names", _no_scope)
    _seed_post_hoc(pct_big=-15.0, stance="BEARISH")

    async def story(c):
        return STORY
    monkeypatch.setattr(sf, "_story", story)
    assert await sf.select_post_hoc_up() is None
    assert (await sf.select_post_hoc_down())["text"].endswith("雙鴻 9/7到9/16跌15.0%")

    async def dead(c):
        return None
    monkeypatch.setattr(sf, "_story", dead)
    assert await sf.select_post_hoc_down() is None             # the number line alone is not a post


@pytest.mark.asyncio
@pytest.mark.parametrize("succeeds", [True, False])
async def test_post_hoc_tries_next_candidate_up_to_cap(monkeypatch, succeeds):
    from src.services import threads_publisher
    candidates = [_cand(ticker=str(i), episode_id=f"ep{i}")
                  for i in range(sf.POST_HOC_MAX_ATTEMPTS + 1)]
    monkeypatch.setattr(threads_publisher.podcast_service, "_allowed_podcast_names", _no_scope)
    monkeypatch.setattr(sf, "_post_hoc_candidates", lambda *_: candidates)
    story = AsyncMock(side_effect=[None, STORY] if succeeds else None, return_value=None)
    monkeypatch.setattr(sf, "_story", story)

    draft = await sf.select_post_hoc_up()
    if succeeds:
        assert draft["key"] == "post_hoc:1:ep1" and draft["subject"] == "1"
        assert draft["text"] == sf.post_hoc_text(candidates[1], STORY)
        assert draft["url"].endswith("/episode/ep1")
        assert "/api/og/stock/1.png?" in draft["image_url"]
    else:
        assert draft is None
    attempts = 2 if succeeds else sf.POST_HOC_MAX_ATTEMPTS
    assert story.await_count == attempts
    assert story.await_args_list == [call(c) for c in candidates[:attempts]]


# ── the stock card's event marker ────────────────────────────────────────────

def test_stock_card_draws_one_named_event_and_nothing_without_it():
    from src.services.stock_card import stock_card_svg
    pts = [{"date": f"2026-08-{d:02d}", "open": 100, "high": 105, "low": 95, "close": 101, "volume": 1000}
           for d in range(1, 31)]
    stock = {"ticker": "3324", "name": "雙鴻", "price": 101, "change": 1, "changePercent": 1.0, "chartData": pts}
    plain = stock_card_svg(stock, [], 30)
    marked = stock_card_svg(stock, [], 30, event={"date": "2026-08-10", "label": "兆華與股惑仔 8/10"})
    assert "兆華與股惑仔 8/10" in marked and "兆華與股惑仔" not in plain
    assert marked.count('stroke-dasharray="6 5"') == 1
    # A date with no session lands on the next one; one past the chart draws nothing.
    assert ">08-10<" in stock_card_svg(stock, [], 30, event={"date": "2026-08-10"})
    assert 'stroke-dasharray="6 5"' not in stock_card_svg(stock, [], 30, event={"date": "2026-09-30"})


# ── the slot, end to end against the ledger ──────────────────────────────────

class _FakeThreads:
    is_configured = True

    def __init__(self):
        self.posts, self.replies = [], []

    async def publish(self, text, image_url=None):
        self.posts.append((text, image_url))
        return f"m{len(self.posts)}"

    async def publish_carousel(self, image_urls, text):
        self.posts.append((text, image_urls))
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
    assert fake.replies == [("▶ https://tinboker.com/weekly/2026-W37"
                             "?utm_source=threads&utm_medium=social&utm_campaign=weekly_movers", "m1")]
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


@pytest.mark.asyncio
async def test_preview_shows_every_draft_and_what_the_slot_would_post(temp_db, monkeypatch):
    monkeypatch.setattr(sf, "ThreadsService", lambda: _FakeThreads())

    async def movers():
        return {"key": "weekly_movers:2026-09-07", "subject": "2026-09-07", "text": "本週"}

    async def broken():
        raise RuntimeError("db down")
    monkeypatch.setattr(sf, "FORMATS", [_fmt("broken", select=broken), _fmt("weekly_movers", select=movers)])

    out = await sf.preview(now=NOW)
    assert out["would_post"]["format"] == "weekly_movers" and out["would_post"]["dry_run"] is True
    assert [f["format"] for f in out["formats"]] == ["broken", "weekly_movers"]
    assert out["formats"][0]["draft"] is None and out["formats"][0]["error"] == "db down"
    assert out["formats"][1]["draft"]["text"] == "本週"
    assert social_ledger.list_posted("threads") == []   # preview never writes


# triage: invariant-gap — a retrospective must not pair a bullish call with a fall.
def test_post_hoc_candidates_reject_opposite_direction(temp_db):
    _seed_post_hoc(pct_big=-15.0)
    assert sf._post_hoc_candidates(None, datetime(2026, 8, 1)) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("stance", ["BEARISH", "STRONG_BEARISH", "NEUTRAL", None, "NOT_BULLISH"])
async def test_post_hoc_selection_rejects_unaligned_stance_before_story(monkeypatch, stance):
    from src.services import threads_publisher
    monkeypatch.setattr(threads_publisher.podcast_service, "_allowed_podcast_names", _no_scope)
    monkeypatch.setattr(sf, "_post_hoc_candidates", lambda *_: [_cand(sentiment_label=stance, episode_id="ep")])
    async def unexpected(c):
        pytest.fail("Rejected candidate must not incur a story call")
    monkeypatch.setattr(sf, "_story", unexpected)
    assert await sf.select_post_hoc_up() is None


def _episode(id_, day="2026-09-14", show="allowed", **kwargs):
    from src.models.podcast import Episode
    return Episode(id=id_, episode_title=id_, podcast_name=show, spotify_release_date=day,
                   released_at_ms=None, summary_content="完整素材" * 30, modified_summary_content=None,
                   **{"created_time": 0, **kwargs})


@pytest.mark.asyncio
async def test_weekly_selector_hydrates_only_scoped_published_week_and_publishes_carousel(temp_db, monkeypatch):
    from datetime import date
    from unittest.mock import AsyncMock
    from src.services import threads_publisher
    service = threads_publisher.podcast_service
    monkeypatch.setattr(sf, "_last_complete_week", lambda: date(2026, 9, 14))
    episodes = [_episode("a"), _episode("b", "2026-09-20"), _episode("c"),
                _episode("before", "2026-09-13"), _episode("after", "2026-09-21"),
                _episode("private", show="excluded"), _episode("undated", None)]
    episodes[0].modified_summary_content = "人工修改後完整素材" * 15
    monkeypatch.setattr(service, "_allowed_podcast_names", AsyncMock(return_value=frozenset({"allowed"})))
    monkeypatch.setattr(service, "get_recent_episodes", AsyncMock(return_value=episodes))
    detail = AsyncMock(side_effect=lambda id_, **_: next(e for e in episodes if e.id == id_))
    monkeypatch.setattr(service, "get_episode_by_id_only", detail)
    images = [f"https://media.test/weekly/2026-W38/{i}.png" for i in range(3)]
    generate = AsyncMock(return_value={"week": "2026-W38", "post": "具體且有依據的觀點", "image_urls": images})
    monkeypatch.setattr(sf, "_weekly_editorial", generate)
    fake = _FakeThreads()
    monkeypatch.setattr(sf, "ThreadsService", lambda: fake)
    monkeypatch.setattr(sf, "FORMATS", [_fmt(select=sf.select_weekly_movers)])
    result = await sf.publish_due_format(now=NOW)
    assert result["posted"] is True
    payload = generate.call_args.args[0]
    assert payload["week"] == "2026-W38" and payload["end"] == "2026-09-20"
    assert [e["episode_id"] for e in payload["episodes"]] == ["a", "b", "c"]
    assert payload["episodes"][0]["summary"] == "人工修改後完整素材" * 15
    assert detail.await_count == 3
    assert fake.posts == [("具體且有依據的觀點", images)]
    assert social_ledger.list_posted("threads")[0]["episode_id"] == "weekly_movers:2026-09-14"


@pytest.mark.asyncio
@pytest.mark.parametrize("bundle", [None, {}, {"week": "2026-W37"},
    {"week": "2026-W38", "post": "有內容", "image_urls": ["https://x/1"]},
    {"week": "2026-W38", "post": "有內容", "image_urls": ["https://x/1"] * 3}])
async def test_weekly_failed_or_stale_generation_never_falls_back_to_leaderboard(monkeypatch, bundle):
    from datetime import date
    from unittest.mock import AsyncMock
    monkeypatch.setattr(sf, "_last_complete_week", lambda: date(2026, 9, 14))
    monkeypatch.setattr(sf, "_weekly_sources", AsyncMock(return_value=[{}, {}, {}]))
    monkeypatch.setattr(sf, "_weekly_editorial", AsyncMock(return_value=bundle))
    assert await sf.select_weekly_movers() is None


@pytest.mark.asyncio
async def test_preview_generates_each_draft_once(temp_db, monkeypatch):
    from unittest.mock import AsyncMock
    select = AsyncMock(return_value={"key": "weekly_movers:2026-09-14", "subject": "2026-09-14", "text": "觀點"})
    monkeypatch.setattr(sf, "FORMATS", [_fmt(select=select)])
    result = await sf.preview(now=NOW)
    assert result["would_post"]["dry_run"] is True
    select.assert_awaited_once()


def test_weekly_publication_date_uses_taipei_not_ingestion():
    from datetime import date, timezone
    ep = _episode("e", "2026-09-13")
    ep.released_at_ms = datetime(2026, 9, 13, 16, tzinfo=timezone.utc).timestamp() * 1000
    assert sf._weekly_episode_date(ep) == date(2026, 9, 14)
    ep = _episode("unknown", None, created_time=ep.released_at_ms)
    assert sf._weekly_episode_date(ep) is None


@pytest.mark.asyncio
async def test_weekly_bridge_sends_authenticated_contract_and_fails_closed(monkeypatch):
    import httpx
    monkeypatch.setattr(sf.settings, "netcup_api_url", "http://pipeline.test")
    monkeypatch.setattr(sf.settings, "podcast_api_key", "test-key")
    original_client = httpx.AsyncClient
    payload = {"week": "2026-W38", "start": "2026-09-14", "end": "2026-09-20", "episodes": []}
    requests = []

    def handler(request):
        import json
        requests.append(request)
        assert request.url.path == "/api/podcast/weekly-editorial"
        assert request.headers["X-API-Key"] == "test-key"
        assert json.loads(request.content) == payload
        return httpx.Response(200, json={"week": "2026-W38"})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(
        **kwargs, transport=httpx.MockTransport(handler)))
    assert await sf._weekly_editorial(payload) == {"week": "2026-W38"}
    assert len(requests) == 1
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(
        **kwargs, transport=httpx.MockTransport(lambda _: httpx.Response(503))))
    assert await sf._weekly_editorial(payload) is None


@pytest.mark.asyncio
async def test_weekly_insufficient_material_never_calls_generator(monkeypatch):
    from unittest.mock import AsyncMock
    monkeypatch.setattr(sf, "_weekly_sources", AsyncMock(return_value=[{}]))
    generate = AsyncMock()
    monkeypatch.setattr(sf, "_weekly_editorial", generate)
    assert await sf.select_weekly_movers() is None
    generate.assert_not_awaited()
