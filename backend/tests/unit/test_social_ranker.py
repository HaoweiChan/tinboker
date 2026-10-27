"""Decisions scoring stays isolated from provider failures and never retries."""
import json
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from src.config import settings
from src.services import social_ranker


@pytest.fixture(autouse=True)
def _ranker_settings(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(settings, "social_slot_ranker_model", "typesafe/jev-1.13")
    social_ranker._memo.clear()
    yield
    social_ranker._memo.clear()


@pytest.fixture
def client(monkeypatch):
    client = AsyncMock()
    client.__aenter__.return_value = client
    factory = Mock(return_value=client)
    monkeypatch.setattr(social_ranker.httpx, "AsyncClient", factory)
    return factory, client


def _response(answer, status=200):
    return httpx.Response(
        status, text=json.dumps({"answers": {"counterintuitive": answer}}),
        request=httpx.Request("POST", "https://openrouter.ai/api/alpha/decisions"),
    )


@pytest.mark.asyncio
async def test_score_posts_parses_probabilities(client):
    factory, http = client
    http.post.side_effect = [
        _response({"type": "noul", "noul": 0.82}),
        _response({"type": "noul", "noul": 0}),
    ]
    assert await social_ranker.score_posts({"a": "First post", "b": "Second post"}) == {"a": 0.82, "b": 0.0}
    factory.assert_called_once_with(timeout=15.0)
    assert http.post.await_count == 2
    for call, text in zip(http.post.await_args_list, ["First post", "Second post"]):
        assert call.args == ("https://openrouter.ai/api/alpha/decisions",)
        assert call.kwargs["headers"]["Authorization"] == "Bearer test-key"
        assert call.kwargs["json"] == {
            "model": "typesafe/jev-1.13", "state": text, "questions": social_ranker.QUESTIONS,
        }


@pytest.mark.asyncio
@pytest.mark.parametrize("answer,status", [
    ({"type": "noul", "noul": 0.4}, 500),
    (None, 200),
    ({"type": "bool", "noul": 0.4}, 200),
    ({"type": "noul", "noul": "0.4"}, 200),
    ({"type": "noul", "noul": True}, 200),
    ({"type": "noul", "noul": -0.1}, 200),
    ({"type": "noul", "noul": 1.1}, 200),
    ({"type": "noul", "noul": float("nan")}, 200),
    ({"type": "noul", "noul": float("inf")}, 200),
])
async def test_score_posts_keeps_success_when_an_answer_fails(client, caplog, answer, status):
    _, http = client
    http.post.side_effect = [_response(answer, status), _response({"type": "noul", "noul": 1})]
    assert await social_ranker.score_posts({"bad": "Bad post", "good": "Good post"}) == {"good": 1.0}
    assert http.post.await_count == 2
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "WARNING"


@pytest.mark.asyncio
async def test_score_posts_timeout_keeps_other_scores(client, caplog):
    _, http = client
    http.post.side_effect = [httpx.ReadTimeout("provider timed out"), _response({"type": "noul", "noul": 0.5})]
    assert await social_ranker.score_posts({"bad": "Bad post", "good": "Good post"}) == {"good": 0.5}
    assert "provider timed out" in caplog.text
    assert http.post.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("setting", ["openrouter_api_key", "social_slot_ranker_model"])
async def test_score_posts_disabled_without_key_or_model(client, monkeypatch, setting):
    factory, http = client
    monkeypatch.setattr(settings, setting, "")
    assert await social_ranker.score_posts({"a": "Post"}) == {}
    factory.assert_not_called()
    http.post.assert_not_called()


@pytest.mark.asyncio
async def test_score_posts_memo_uses_text_and_model(client, monkeypatch):
    _, http = client
    http.post.return_value = _response({"type": "noul", "noul": 0.82})
    assert await social_ranker.score_posts({"a": "Same post"}) == {"a": 0.82}
    http.post.reset_mock()
    assert await social_ranker.score_posts({"b": "Same post"}) == {"b": 0.82}
    http.post.assert_not_called()
    monkeypatch.setattr(settings, "social_slot_ranker_model", "other-model")
    assert await social_ranker.score_posts({"b": "Same post"}) == {"b": 0.82}
    http.post.assert_awaited_once()


def _repeat_response(p):
    return httpx.Response(
        200, text=json.dumps({"answers": {"same_story": {"type": "noul", "noul": p}}}),
        request=httpx.Request("POST", "https://openrouter.ai/api/alpha/decisions"),
    )


@pytest.mark.asyncio
async def test_repeats_recent_holds_back_only_scores_at_the_threshold(client):
    _, http = client
    http.post.side_effect = [_repeat_response(0.95), _repeat_response(0.62)]
    recent = ["CoreWeave 債券殖利率被賣到15%\n⬇️ 4 個重點整理", "南亞衝過300元"]
    held = await social_ranker.repeats_recent({"again": "Coreweave 營收翻倍但利息吃掉四分之一", "new": "台光電 CCL 缺到2030"}, recent)
    assert held == {"again"}
    state = http.post.await_args_list[0].kwargs["json"]["state"]
    # Recent posts first, newest first, the carousel tail dropped; then the candidate.
    assert state == ("RECENT POSTS:\nCoreWeave 債券殖利率被賣到15%\n---\n南亞衝過300元"
                     "\n\nCANDIDATE POST:\nCoreweave 營收翻倍但利息吃掉四分之一")
    assert http.post.await_args_list[0].kwargs["json"]["questions"] == social_ranker.REPEAT_QUESTION


@pytest.mark.asyncio
async def test_repeats_recent_fails_open(client, monkeypatch):
    _, http = client
    assert await social_ranker.repeats_recent({"a": "x"}, []) == set()      # nothing posted lately
    http.post.assert_not_called()
    http.post.side_effect = [httpx.ReadTimeout("slow")]
    assert await social_ranker.repeats_recent({"a": "x"}, ["y"]) == set()   # provider down
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    assert await social_ranker.repeats_recent({"a": "x"}, ["y"]) == set()   # no key
