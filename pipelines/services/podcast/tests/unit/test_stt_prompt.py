"""Budget arithmetic for the Whisper vocabulary hint, and the collapse guard.

Both numbers here were measured against the live Groq API, not read off a doc page: a
361-character prompt is refused with "prompt contains 1075 characters", i.e. the
validator counts UTF-8 bytes and the ceiling is 896 of them.
"""

from types import SimpleNamespace

from src.pipeline.stt_prompt import (
    MAX_PROMPT_BYTES,
    MAX_PROMPT_CHARS,
    RECURRING_TERMS,
    _fit_bytes,
    compose,
)
from src.service.speech_to_text import GroqService


def test_compose_dedupes_and_preserves_order():
    assert compose(["欣興", "南電", "欣興", "", "  ", "景碩"]) == "欣興、南電、景碩"


def test_compose_stops_at_budget_but_keeps_scanning():
    # "台積電" overflows a budget of 5 while the later, shorter "南電" still fits.
    assert compose(["欣興", "台積電", "南電"], budget=5) == "欣興、南電"


def test_compose_never_exceeds_its_budget():
    out = compose([f"公司{i}" for i in range(300)], budget=MAX_PROMPT_CHARS)
    assert len(out) <= MAX_PROMPT_CHARS


def test_recurring_terms_always_fit_on_their_own():
    """The reserved tail must never be squeezed out by its own size."""
    tail = compose(list(RECURRING_TERMS))
    assert set(tail.split("、")) == set(RECURRING_TERMS)
    assert len(tail) < MAX_PROMPT_CHARS


def test_fit_bytes_trims_from_the_front():
    # Whisper keeps the tail of the prompt, so the front is what we can afford to lose.
    trimmed = _fit_bytes("、".join(["公司"] * 300))
    assert len(trimmed.encode("utf-8")) <= MAX_PROMPT_BYTES
    assert trimmed.endswith("公司")


def test_fit_bytes_leaves_a_short_prompt_alone():
    assert _fit_bytes("欣興、南電") == "欣興、南電"


# --- the collapse guard ------------------------------------------------------------
# Called unbound: the check reads only _MIN_COVERAGE, and constructing a GroqService
# would demand the groq package and a live API key.
_collapsed = GroqService._looks_collapsed


def _fake(rate=2.5):
    return SimpleNamespace(_MIN_CHARS_PER_SECOND=rate)


def test_collapse_detected_on_a_sparse_transcript():
    """The real failure: 32s of dense market talk came back as a 12-char song credit."""
    assert _collapsed(_fake(), {"duration": 32.0, "text": "詞曲 李宗盛主要的負擔是"}) is True


def test_normal_speech_density_is_not_a_collapse():
    assert _collapsed(_fake(), {"duration": 32.0, "text": "字" * 146}) is False


def test_coverage_is_not_the_signal():
    """Whisper reports a full-length segment while emitting nothing — measured, not assumed."""
    payload = {"duration": 32.0, "text": "詞曲 李宗盛主要的負擔是",
               "segments": [{"start": 0.0, "end": 32.0}]}
    assert _collapsed(_fake(), payload) is True


def test_missing_or_bad_duration_is_not_judged():
    assert _collapsed(_fake(), {"text": "短"}) is False
    assert _collapsed(_fake(), {"duration": "n/a", "text": "短"}) is False
    assert _collapsed(_fake(), {"duration": 0, "text": ""}) is False
