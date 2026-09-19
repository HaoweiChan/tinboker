"""Routing for the three cost levers: provider pin, local models, decisions models.

Measured 2026-09-19: one model is served by 16 OpenRouter providers at a 3.7x spread in
posted input price (and 8x in what we actually paid), and the roles whose entire answer
is a verdict were ~10% of pipeline spend while costing ~97% less on a decisions model.
Each lever is one env var, so the thing worth testing is that the env var actually
reaches the client — a silent no-op here looks exactly like "the saving didn't happen".
"""

from __future__ import annotations

import pytest
from src.podcast.content_builder import llm
from src.podcast.content_builder.nodes import sector_exposures


class _CapturedClient:
    """Stands in for ChatOpenAI and records how it was built."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs


@pytest.fixture
def captured(monkeypatch):
    import langchain_openai

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", _CapturedClient)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("OPENROUTER_PROVIDER_ORDER", raising=False)
    monkeypatch.delenv("LOCAL_LLM_BASE_URL", raising=False)
    monkeypatch.setattr(llm, "_LLM_OVERRIDES", {}, raising=False)
    return _CapturedClient


def test_provider_order_is_forwarded_to_openrouter(captured, monkeypatch):
    monkeypatch.setenv("PIPELINE_LLM_MODEL", "openrouter:deepseek/deepseek-v4-pro")
    monkeypatch.setenv("OPENROUTER_PROVIDER_ORDER", "StreamLake, Baidu")

    client = llm.get_model("writer")

    assert client.kwargs["extra_body"]["provider"] == {
        "order": ["StreamLake", "Baidu"],
        "allow_fallbacks": True,
    }
    # The pin must not clobber the reasoning switch that shares extra_body.
    assert client.kwargs["extra_body"]["reasoning"] == {"enabled": False}


def test_no_provider_key_when_the_env_var_is_unset(captured, monkeypatch):
    monkeypatch.setenv("PIPELINE_LLM_MODEL", "openrouter:deepseek/deepseek-v4-pro")

    client = llm.get_model("writer")

    assert "provider" not in client.kwargs["extra_body"]


def test_local_prefix_points_the_client_at_our_own_server(captured, monkeypatch):
    monkeypatch.setenv("EXTRACTOR_MODEL", "local:qwen3:30b-a3b-instruct-2507-q4_K_M")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://mac-mini:11434/v1")

    client = llm.get_model("extractor")

    assert client.kwargs["base_url"] == "http://mac-mini:11434/v1"
    assert client.kwargs["model"] == "qwen3:30b-a3b-instruct-2507-q4_K_M"
    # OpenRouter-only fields would be dead weight (or a 400) on a local server.
    assert "extra_body" not in client.kwargs


def test_local_prefix_without_a_base_url_fails_loud(captured, monkeypatch):
    monkeypatch.setenv("EXTRACTOR_MODEL", "local:qwen3:30b")

    with pytest.raises(RuntimeError, match="LOCAL_LLM_BASE_URL"):
        llm.get_model("extractor")


def test_decisions_model_is_refused_by_the_chat_path(captured, monkeypatch):
    monkeypatch.setenv("SECTOR_VERIFIER_MODEL", "decisions:typesafe/jev-1.13")

    assert llm.is_decisions_model("sector_verifier") is True
    with pytest.raises(RuntimeError, match="decisions"):
        llm.get_model("sector_verifier")


def test_sector_verifier_uses_the_decisions_path_and_the_cutoff(monkeypatch):
    asked: list[dict] = []

    def fake_decide(role, state, questions, **kwargs):
        asked.append({"role": role, "state": state, "questions": questions})
        # Calibrated probability, not a boolean — 0.82 keeps, 0.11 drops.
        return {"is_relevant": {"type": "noul", "noul": 0.82 if state["sector_id"] == "ai" else 0.11}}

    monkeypatch.setattr(llm, "is_decisions_model", lambda role: True)
    monkeypatch.setattr(llm, "decide", fake_decide)

    result = sector_exposures._verify_relevance(
        [{"sector_id": "ai", "context": "談 AI 伺服器供應鏈"}, {"sector_id": "oil", "context": "油價當溫度計"}]
    )

    assert result == {"ai": True, "oil": False}
    assert [a["role"] for a in asked] == ["sector_verifier", "sector_verifier"]
    assert asked[0]["questions"]["is_relevant"]["type"] == "noul"
    # The criteria come from the prompt file, so the two paths cannot drift apart.
    assert "Taiwan-listed" in asked[0]["questions"]["is_relevant"]["instructions"]


def test_sector_verifier_still_batches_on_a_chat_model(monkeypatch):
    seen: list[list[dict]] = []

    def fake_invoke_json(role, messages):
        seen.append(messages)
        return {"verifications": [{"sector_id": "ai", "is_relevant": True}]}

    monkeypatch.setattr(llm, "is_decisions_model", lambda role: False)
    monkeypatch.setattr(llm, "invoke_json", fake_invoke_json)

    result = sector_exposures._verify_relevance([{"sector_id": "ai", "context": "談 AI"}])

    assert result == {"ai": True}
    assert len(seen) == 1, "the chat path must stay a single batched call"


def test_routing_question_does_not_raise_for_an_unconfigured_role(monkeypatch):
    """Regression: ``is_decisions_model`` must answer, not raise, with no model set.

    It first asked ``_model_name``, which raises when no model env var is configured.
    In the sector verifier that turned a missing env var into an exception inside the
    verify step, whose fallback fails CLOSED for ticker-derived candidates — so every
    such exposure silently vanished instead of the pipeline reporting a config error.
    """
    for var in ("PIPELINE_LLM_MODEL", "SECTOR_VERIFIER_MODEL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(llm, "_LLM_OVERRIDES", {}, raising=False)

    assert llm.is_decisions_model("sector_verifier") is False
