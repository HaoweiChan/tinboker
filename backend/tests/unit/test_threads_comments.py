"""Comment triage: what gets excluded by rule, and what may go out unattended.

The example comments are real ones from @tinboker (Aug 2026) — the classifier can be
swapped, these rules cannot regress.
"""
import pytest

from src.services import threads_comments_service as svc


# ── rule-level exclusions (no model call) ────────────────────────────

def test_bots_are_never_answered():
    assert svc._is_bot("meta.ai") is True
    assert svc._is_bot("@Meta.AI") is True
    assert svc._is_bot("john_chao369") is False


def test_only_replies_aimed_at_us_count():
    """A reply to another commenter is a conversation we are not in."""
    ours = {"post_1", "our_chain_2"}
    assert svc._addressed_to_us({"replied_to": {"id": "post_1"}}, ours) is True
    assert svc._addressed_to_us({"replied_to": {"id": "our_chain_2"}}, ours) is True
    assert svc._addressed_to_us({"replied_to": {"id": "someone_elses"}}, ours) is False
    assert svc._addressed_to_us({}, ours) is False


# ── the routing decision ─────────────────────────────────────────────

def test_hostile_and_noise_are_ignored():
    assert svc.decide("hostile", False, False, "標準的垃圾訊息產生的垃圾文章") == "ignore"
    assert svc.decide("noise", False, False, "我就空") == "ignore"
    assert svc.decide("promo", False, False, "🦞30秒看盤 https://threads.com/share/x") == "ignore"
    assert svc.decide("bot", True, False, "這則留言半對半錯") == "ignore"


def test_contentless_praise_is_not_queued():
    """Nothing to answer — it does not belong in a queue a human works through."""
    assert svc.decide("praise", False, False, "皓哥出品，必屬精品") == "ignore"


def test_substance_always_waits_for_a_human():
    assert svc.decide("substantive", True, False,
                      "MIT 的調查 95% 企業用 AI 後沒提升效果") == "needs_review"
    assert svc.decide("question", False, True,
                      "只想問替代方案是什麼？什麼時候出來？") == "needs_review"


def test_praise_carrying_a_claim_or_a_question_waits():
    assert svc.decide("praise", True, False, "講得好，毛利率確實快九成") == "needs_review"
    assert svc.decide("praise", False, True, "很喜歡，下一集會講記憶體嗎？") == "needs_review"


@pytest.mark.parametrize("text", [
    "寫得好！2330 現在還能買嗎",
    "同意，$NVDA 我該不該加碼",
    "推，這樣是不是該停損了",
])
def test_praise_touching_a_position_still_reaches_a_human(text):
    """Anything about someone's holdings is a question wearing a compliment."""
    assert svc.decide("praise", False, False, text) == "needs_review"


def test_unknown_category_falls_back_to_review():
    """A failed or nonsense triage must never silently drop a comment."""
    assert svc.decide("weird", False, False, "…") == "needs_review"


# ── send guard ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reply_refuses_empty_text(temp_db):
    with pytest.raises(ValueError):
        await svc.send_reply("c1", "   ")


# ── the sync loop ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sync_files_comments_and_posts_nothing(temp_db, monkeypatch):
    """The rule filters, the dedupe, and the guarantee that matters: a sync never sends.

    /me/threads returns our own chain replies too, so one comment shows up under several
    posts — storing it twice hits the primary key and 500s the whole sync.
    """
    conv = [
        {"id": "own", "is_reply_owned_by_me": True, "replied_to": {"id": "p1"}},
        {"id": "c1", "username": "someone", "text": "群聯的方案不能推理",
         "timestamp": "2026-09-01T10:00:00+0000", "replied_to": {"id": "p1"},
         "permalink": "https://www.threads.com/@someone/post/Dc8IesYkqlS"},
        {"id": "c2", "username": "meta.ai", "text": "翻譯", "replied_to": {"id": "p1"}},
        {"id": "c3", "username": "bystander", "text": "回別人的", "replied_to": {"id": "c1"}},
        {"id": "c4", "username": "sticker", "text": "   ", "replied_to": {"id": "p1"}},
        {"id": "c5", "username": "fan", "text": "推推", "replied_to": {"id": "p1"}},
    ]

    class FakeResponse:
        def __init__(self, payload): self._payload = payload
        def json(self): return self._payload

    class FakeClient:
        async def get(self, url, params=None):
            if url.endswith("/me/threads"):
                return FakeResponse({"data": [{"id": "p1", "text": "貼文"},
                                              {"id": "own", "text": "自己的回覆"}]})
            return FakeResponse({"data": conv})
        async def __aenter__(self): return self
        async def __aexit__(self, *_): return False

    monkeypatch.setattr(svc.httpx, "AsyncClient", lambda **_: FakeClient())
    monkeypatch.setattr(svc.ThreadsService, "is_configured", property(lambda self: True))

    async def fake_triage(_client, _post, text):
        if "推推" in text:
            return {"category": "praise", "has_factual_claim": False,
                    "asks_question": False, "reason": "r", "draft": ""}
        return {"category": "substantive", "has_factual_claim": True,
                "asks_question": False, "reason": "r", "draft": "d"}
    monkeypatch.setattr(svc, "_triage", fake_triage)

    async def never(*a, **k):
        raise AssertionError("a sync must never post a reply")
    monkeypatch.setattr(svc, "send_reply", never)

    counts = await svc.sync_and_triage()
    assert counts["scanned"] == 2
    # bot, side-thread and the textless sticker never reach the model
    assert counts["new"] == 2
    assert counts["needs_review"] == 1 and counts["ignored"] == 1
    assert "auto_replied" not in counts
    pending = svc.list_comments(status="pending")
    assert [c["id"] for c in pending] == ["c1"]
    # the API's own shortcode URL, never one built from the media id — that 404s
    assert pending[0]["permalink"] == "https://www.threads.com/@someone/post/Dc8IesYkqlS"
    assert [c["id"] for c in svc.list_comments(status="ignored")] == ["c5"]
