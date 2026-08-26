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


def test_plain_praise_may_go_out_unattended():
    assert svc.decide("praise", False, False, "皓哥出品，必屬精品") == "auto_reply"


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
def test_praise_touching_a_position_never_auto_replies(text):
    """Anything about someone's holdings is advice — never unattended, whatever the model said."""
    assert svc.decide("praise", False, False, text) == "needs_review"


def test_unknown_category_falls_back_to_review():
    """A failed or nonsense triage must never silently drop a comment."""
    assert svc.decide("weird", False, False, "…") == "needs_review"


# ── send guard ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reply_refuses_empty_text(temp_db):
    with pytest.raises(ValueError):
        await svc.send_reply("c1", "   ")
