"""Offline checks for selection boundaries, paid-call replay, and evidence provenance."""
import copy
import json
import os
from unittest.mock import Mock

import pytest
from podcast.content_builder import news_drafts as drafts

NOW = drafts.timestamp("2026-10-02T10:00:00Z")


def article(aid="a"):
    return {"id": aid, "language": "en", "title": "New customer deployment",
            "url": "https://example.com/news", "published_at": "2026-10-02T08:00:00Z",
            "publication_verified": True,
            "paragraphs": [{"id": "0", "text": "A named customer deployed a new product. " * 8}]}


def answer(value=0.9):
    return {"answers": {key: {"type": "noul", "noul": value} for key in drafts.QUESTIONS}}


@pytest.mark.parametrize("change", [
    {"publication_verified": "true"}, {"language": "zh-TW"},
    {"published_at": "2026-09-01T00:00:00Z"},
    {"published_at": "2026-10-03T00:00:00Z"},
    {"published_at": "2026-10-02T08:00:00"},
    {"paragraphs": [{"id": "0", "text": "headline only"}]},
    {"url": "http://example.com/news"},
])
def test_ineligible_never_calls_models(tmp_path, monkeypatch, change):
    source = article() | change
    call = Mock(side_effect=AssertionError("Unexpected paid call"))
    monkeypatch.setattr(drafts, "jev", call)
    monkeypatch.setattr(drafts, "write", call)
    result = drafts.run({"articles": [source]}, tmp_path, as_of=NOW, select_with_jev=True)
    assert not result["candidates"] and result["draft"] is None
    call.assert_not_called()


def test_posted_identity_dedup_precedes_dates_and_order():
    posted = article("posted") | {"published_at": "2020-01-01T00:00:00Z"}
    duplicate = article("copy") | {"url": "https://example.com/news/?utm_source=rss#top"}
    for sources in ([duplicate, posted], [posted, duplicate]):
        kept, _ = drafts.prefilter({"articles": sources, "already_posted_ids": ["posted"]}, NOW)
        assert kept == []
    second_url = article("other") | {"url": "https://example.org/other"}
    kept, _ = drafts.prefilter({"articles": [article(), second_url]}, NOW)
    assert len(kept) == 1


@pytest.mark.parametrize("value", [True, "0.9", -0.1, 1.1, float("nan"), None])
def test_invalid_jev_probabilities_rejected(value):
    with pytest.raises(ValueError):
        drafts.selection_score(answer(value))


def test_uncertain_skips_writer_and_malformed_answers_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(drafts, "jev", lambda _: answer(0.79))
    writer = Mock(side_effect=AssertionError("Unexpected writer"))
    monkeypatch.setattr(drafts, "write", writer)
    assert drafts.run({"articles": [article()]}, tmp_path, as_of=NOW,
                      select_with_jev=True)["draft"] is None
    writer.assert_not_called()
    with pytest.raises(ValueError):
        drafts.selection_score({"answers": {}})


def test_english_source_cache_and_separate_comment(tmp_path, monkeypatch):
    source = article() | {"screenshot_path": str(tmp_path / "missing.png")}
    selector = Mock(return_value=answer())
    writer = Mock(return_value={"draft": {"post": "新設備開始交貨\n\n客戶已經用上了",
                                          "evidence_ids": ["0"]}, "usage": {"input_tokens": 25}})
    monkeypatch.setattr(drafts, "jev", selector)
    monkeypatch.setattr(drafts, "write", writer)
    monkeypatch.setenv("SOCIAL_COPY_WRITER_MODEL", "original-model")
    for _ in range(2):
        result = drafts.run({"articles": [source]}, tmp_path, as_of=NOW, select_with_jev=True)
        assert not result["publish_ready"]
        assert result["draft"]["first_comment"] == source["url"]
        assert not result["draft"]["screenshot_exists"]
        assert result["draft"]["review_required"]
    assert selector.call_count == writer.call_count == 1
    assert selector.call_args.args[0]["state"] == source
    assert os.environ["SOCIAL_COPY_WRITER_MODEL"] == "original-model"
    user_data = json.loads(writer.call_args.args[0]["messages"][1]["content"])
    assert user_data["article"] == source
    assert all(call["cache_hit"] for call in result["calls"])


def test_transport_failures_cached_and_evidence_invalid(tmp_path, monkeypatch):
    failed = Mock(side_effect=TimeoutError())
    monkeypatch.setattr(drafts, "jev", failed)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            drafts.run({"articles": [article()]}, tmp_path, as_of=NOW, select_with_jev=True)
    assert failed.call_count == 1
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["draft"] is None and not report["publish_ready"]
    with pytest.raises(ValueError):
        drafts.validate_draft({"draft": {"post": "內容", "evidence_ids": ["invented"]}}, article())


def test_candidate_cap_and_no_selection_default(tmp_path, monkeypatch):
    articles = []
    for index in range(10):
        item = copy.deepcopy(article(str(index)))
        item["url"] += str(index)
        item["paragraphs"][0]["text"] += str(index)
        articles.append(item)
    result = drafts.run({"articles": articles}, tmp_path, as_of=NOW)
    assert len(result["candidates"]) == 6
    assert result["calls"] == [] and result["draft"] is None


def test_jev_http_contract(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "test-only-placeholder")
    response = Mock()
    response.json.return_value = answer()
    post = Mock(return_value=response)
    monkeypatch.setattr(drafts.requests, "post", post)
    payload = {"model": drafts.JEV_MODEL, "state": article(), "questions": drafts.QUESTIONS}
    assert drafts.jev(payload) == answer()
    assert post.call_args.args == ("https://api.typesafe.ai/v1/systemone",)
    assert post.call_args.kwargs["json"] == payload
    assert post.call_args.kwargs["timeout"] == 30
    response.raise_for_status.assert_called_once()


def test_newest_revision_wins_and_english_only_is_rejected():
    old = article("old") | {"published_at": "2026-10-02T01:00:00Z"}
    new = article("corrected")
    kept, _ = drafts.prefilter({"articles": [old, new]}, NOW)
    assert [a["id"] for a in kept] == ["corrected"]
    with pytest.raises(ValueError, match="Chinese"):
        drafts.validate_draft({"draft": {"post": "English only", "evidence_ids": ["0"]}}, new)


def test_explicit_writer_model_beats_db_override(monkeypatch):
    import langchain_openai
    from podcast.content_builder import llm

    monkeypatch.setattr(llm, "_LLM_OVERRIDES", {"social_copy_writer_model": "expensive/model"})
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-only-placeholder")
    constructor = Mock()
    monkeypatch.setattr(langchain_openai, "ChatOpenAI", constructor)
    llm.get_model("social_copy_writer", model_override="deepseek/deepseek-v4-pro")
    assert constructor.call_args.kwargs["model"] == "deepseek/deepseek-v4-pro"
    assert constructor.call_args.kwargs["base_url"] == "https://openrouter.ai/api/v1"


def test_writer_transport_has_no_retries_and_bounded_timeout(monkeypatch):
    from types import SimpleNamespace

    from podcast.content_builder import llm
    model = Mock()
    model.model_copy.return_value.invoke.return_value = SimpleNamespace(
        content='{"post":"測試內容","evidence_ids":["0"]}',
        usage_metadata={}, response_metadata={})
    factory = Mock(return_value=model)
    monkeypatch.setattr(llm, "get_model", factory)
    drafts.write({"model": "deepseek/deepseek-v4-pro", "messages": []})
    factory.assert_called_once_with("social_copy_writer", model_override="deepseek/deepseek-v4-pro")
    model.root_client.with_options.assert_called_once_with(timeout=60, max_retries=0)
    assert model.model_copy.call_args.kwargs["update"]["max_tokens"] == 2048
