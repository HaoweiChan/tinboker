"""Mention refresh happens after both writes and never breaks ingest on HTTP failure."""

from unittest.mock import MagicMock

import pytest
from shared import platform_client
from src.pipeline import processor as module


@pytest.mark.parametrize("rerun_from", [None, "summarize", "upload", "validate"])
@pytest.mark.parametrize("http_fails", [False, True])
def test_processor_syncs_after_writes(monkeypatch, base_config, base_context, rerun_from, http_fails):
    base_config.rerun_from = rerun_from
    base_config.skip_summarize = False
    processor = module.EpisodeProcessor(base_config, base_context)
    monkeypatch.setattr(processor, "_should_skip_episode", lambda data: False)
    monkeypatch.setattr(processor, "_load_existing_data", lambda data: setattr(data, "episode_id", "show_ep"))
    monkeypatch.setenv("TINBOKER_ADMIN_API_URL", "https://admin.test/")
    monkeypatch.setenv("TINBOKER_WRITE_TOKEN", "test-service-token")
    calls = []
    for step in (
        "download_episode", "transcribe_episode", "generate_summary", "upload_to_gcs",
        "render_social_cards",
        "trigger_syndicate", "validate_episode",
    ):
        monkeypatch.setattr(module, step, lambda *args: None)
    monkeypatch.setattr(module, "extract_theme_views", lambda *args: calls.append("themes"))
    monkeypatch.setattr(module, "ingest_into_wiki", lambda *args: calls.append("wiki"))
    monkeypatch.setattr(module, "persist_episode", lambda *args: calls.append("episode"))
    monkeypatch.setattr(module, "export_ticker_insights", lambda *args: calls.append("insights"))

    def urlopen(request, timeout):
        assert calls == ["episode", "insights"]
        calls.append("sync")
        assert request.full_url == "https://admin.test/api/admin/episodes/show_ep/sync-mentions"
        assert request.method == "POST"
        assert request.get_header("Authorization") == "Bearer test-service-token"
        assert request.get_header("User-agent") == platform_client.USER_AGENT
        assert timeout == 45.0
        if http_fails:
            raise OSError("offline")
        response = MagicMock()
        response.__enter__.return_value.status = 200
        return response

    monkeypatch.setattr(platform_client.urllib.request, "urlopen", urlopen)
    assert processor.process_episode({"title": "Episode"}) is True
    assert calls == ["episode", "insights"] + ([] if rerun_from == "validate" else ["sync"]) + ["themes", "wiki"]


def test_missing_credentials_skip_http(monkeypatch, caplog):
    monkeypatch.delenv("TINBOKER_WRITE_TOKEN", raising=False)
    request = MagicMock()
    monkeypatch.setattr(platform_client.urllib.request, "urlopen", request)
    assert platform_client.sync_episode_mentions("ep") is False
    request.assert_not_called()
    assert "Mention sync skipped" in caplog.text


def test_sync_http_failure_is_logged(monkeypatch, caplog):
    monkeypatch.setenv("TINBOKER_ADMIN_API_URL", "https://admin.test")
    monkeypatch.setenv("TINBOKER_WRITE_TOKEN", "test-service-token")
    response = MagicMock()
    response.__enter__.return_value.status = 503
    monkeypatch.setattr(platform_client.urllib.request, "urlopen", lambda *args, **kwargs: response)
    assert platform_client.sync_episode_mentions("ep") is False
    assert "Mention sync failed for ep" in caplog.text
