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

def _movers(rows, total=900):
    return {"week_start": "2026-09-07", "week_end": "2026-09-13", "total": total, "rows": rows}


def test_weekly_caption_is_about_the_leader_and_says_what_the_number_is():
    text = sf.weekly_movers_text(_movers([
        {"ticker": "3037", "name": "欣興", "n": 31, "prev": 4, "casts": 6, "bull": 9, "bear": 14},
        {"ticker": "8299", "name": "群聯", "n": 5, "prev": 0, "casts": 2, "bull": 3, "bear": 0},
    ]))
    assert text.startswith("3037 欣興 這週 6 個節目提了 31 次 上週 4 看空的多")
    assert "8299" not in text                      # a +5 runner-up is not worth a line
    assert "不是漲幅" in text and "我" not in text and "#" not in text
    assert len(text) <= THREADS_MAX_CHARS


def test_weekly_caption_lists_runners_up_only_when_they_are_loud_too():
    text = sf.weekly_movers_text(_movers([
        {"ticker": "3037", "name": "欣興", "n": 31, "prev": 4, "casts": 6, "bull": 9, "bear": 9},
        {"ticker": "2330", "name": "台積電", "n": 60, "prev": 45, "casts": 8, "bull": 30, "bear": 2},
        {"ticker": "8299", "name": "群聯", "n": 12, "prev": 1, "casts": 3, "bull": 5, "bear": 0},
        {"ticker": "3006", "name": "晶豪科", "n": 9, "prev": 0, "casts": 2, "bull": 1, "bear": 0},
    ]))
    assert "多空各半" in text
    assert "也很吵的還有\n2330 台積電 60 次 上週 45\n8299 群聯 12 次 上週 1" in text
    assert "3006" not in text                      # two runners-up at most


@pytest.mark.asyncio
async def test_weekly_select_stays_quiet_on_a_thin_week(monkeypatch):
    """W37 for real: 327 mentions, leader +6. Nothing goes out rather than a weak post."""
    import src.routers.og as og
    from src.services import threads_publisher

    async def allowed():
        return None
    monkeypatch.setattr(threads_publisher.podcast_service, "_allowed_podcast_names", allowed)
    thin = _movers([{"ticker": "3661", "name": "世芯-KY", "n": 6, "prev": 0, "casts": 2, "bull": 4, "bear": 1}], total=327)
    monkeypatch.setattr(og, "_weekly_movers", lambda *_: thin)
    assert await sf.select_weekly_movers() is None

    loud = _movers([{"ticker": "3037", "name": "欣興", "n": 31, "prev": 4, "casts": 6, "bull": 9, "bear": 14}], total=900)
    monkeypatch.setattr(og, "_weekly_movers", lambda *_: loud)
    draft = await sf.select_weekly_movers()
    assert draft["key"] == "weekly_movers:2026-09-07" and draft["subject"] == "2026-09-07"
    assert draft["image_url"].endswith("/api/og/weekly.png") and draft["url"].endswith("/weekly/2026-W37")


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
    assert text.endswith("\n\n8/31 到 9/16 漲 8.8%")
    assert sf.post_hoc_text(_cand(pct=-12.34), STORY).endswith("8/31 到 9/16 跌 12.3%")
    assert "我" not in text and "對了" not in text and "錯了" not in text
    assert len(text) <= THREADS_MAX_CHARS


def _seed_post_hoc(pct_big=12.0, pct_small=3.0):
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
                               mentioned_at=_dt.utcnow() - timedelta(days=10), sentiment_label="BULLISH",
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
    assert draft["text"] == STORY + "\n\n9/7 到 9/16 漲 12.0%"
    assert draft["image_url"].endswith("/api/og/stock/3324.png?days=60&event=2026-09-07"
                                       "&label=%E5%85%86%E8%8F%AF%E8%88%87%E8%82%A1%E6%83%91%E4%BB%94%209/7")
    assert draft["url"].endswith("/episode/ep0")


@pytest.mark.asyncio
async def test_post_hoc_down_is_its_own_format_and_no_story_means_no_post(temp_db, monkeypatch):
    from src.services import threads_publisher
    monkeypatch.setattr(threads_publisher.podcast_service, "_allowed_podcast_names", _no_scope)
    _seed_post_hoc(pct_big=-15.0)

    async def story(c):
        return STORY
    monkeypatch.setattr(sf, "_story", story)
    assert await sf.select_post_hoc_up() is None
    assert (await sf.select_post_hoc_down())["text"].endswith("9/7 到 9/16 跌 15.0%")

    async def dead(c):
        return None
    monkeypatch.setattr(sf, "_story", dead)
    assert await sf.select_post_hoc_down() is None             # the number line alone is not a post


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
