"""An endpoint that refuses ``reasoning.enabled=false`` must not stall the pipeline.

Regression: the reasoning switch is set on the client in ``get_model``, not in the
per-call kwargs, so ``invoke_json``'s "retry without the JSON-mode kwarg" path could
never clear it. When deepseek-v4-pro began answering

    400 - Reasoning is mandatory for this endpoint and cannot be disabled.

both calls raised, every episode fell back to the placeholder summarizer, and the
summarize step refused to persist — no show completed.
"""

from __future__ import annotations

import pytest
from src.podcast.content_builder import llm


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content


class _MandatoryReasoningModel:
    """Rejects any call while the client disables reasoning; fine once it doesn't."""

    def __init__(self, disable_reasoning: bool):
        self.disable_reasoning = disable_reasoning
        self.calls = 0

    def invoke(self, messages, **kwargs):
        self.calls += 1
        if self.disable_reasoning:
            raise RuntimeError(
                "Error code: 400 - {'error': {'message': 'Reasoning is mandatory for "
                "this endpoint and cannot be disabled.', 'code': 400}}"
            )
        return _FakeResponse('{"ok": true}')


def test_it_rebuilds_the_client_with_reasoning_enabled_and_succeeds(monkeypatch):
    built: list[bool] = []

    def fake_get_model(role, *, disable_reasoning=True):
        built.append(disable_reasoning)
        return _MandatoryReasoningModel(disable_reasoning)

    monkeypatch.setattr(llm, "get_model", fake_get_model)
    monkeypatch.setattr(llm, "_model_name", lambda role: "openrouter:x/y")

    assert llm.invoke_json("writer", [{"role": "user", "content": "hi"}]) == {"ok": True}
    # First client disables reasoning, the retry client does not.
    assert built == [True, False]


def test_an_unrelated_error_is_not_swallowed_as_a_reasoning_problem(monkeypatch):
    class _AlwaysBroken:
        def invoke(self, messages, **kwargs):
            raise RuntimeError("Error code: 500 - upstream exploded")

    monkeypatch.setattr(llm, "get_model", lambda role, **kw: _AlwaysBroken())
    monkeypatch.setattr(llm, "_model_name", lambda role: "openrouter:x/y")

    with pytest.raises(RuntimeError, match="upstream exploded"):
        llm.invoke_json("writer", [{"role": "user", "content": "hi"}])


def test_reasoning_enabled_clients_get_extra_completion_headroom(monkeypatch):
    """Reasoning tokens share the completion budget, so the fallback needs room or the
    JSON truncates mid-array — the failure disabling reasoning was there to prevent."""
    captured: dict = {}

    class _FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    import langchain_openai

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", _FakeChatOpenAI)
    monkeypatch.setattr(llm, "_model_name", lambda role: "openrouter:x/y")

    llm.get_model("writer")
    assert captured["extra_body"] == {"reasoning": {"enabled": False}}
    baseline = captured["max_tokens"]

    llm.get_model("writer", disable_reasoning=False)
    assert captured["extra_body"] == {}
    assert captured["max_tokens"] == baseline * 2
