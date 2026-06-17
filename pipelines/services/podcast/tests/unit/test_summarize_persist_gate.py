"""Unit tests for the summarize step's pre-write persistence gate.

A failed external summarization falls back to the placeholder summarizer (junk
prose + random tickers). Those writes used to land in GCS/Firestore/Postgres/wiki
BEFORE the validate step ran, so a failed run overwrote good content. The gate in
``generate_summary`` now raises ``SummaryNotPersistableError`` before any write
step runs, so a bad run is skipped and existing content is preserved.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from src.pipeline.config import PipelineConfig
from src.pipeline.episode_data import EpisodeData
from src.pipeline.service_container import ServiceContainer
from src.pipeline.steps.summarize import (
    SummaryNotPersistableError,
    assert_summary_persistable,
    generate_summary,
)


def _episode_data(summary_result, tickers=None) -> EpisodeData:
    ed = EpisodeData(api_data={"title": "EP", "episodeNumber": 1}, podcast_name="Gooaye", language="zh")
    ed.summary_result = summary_result
    ed.tickers = tickers or []
    ed.transcript_text = "some transcript"
    return ed


# --- assert_summary_persistable (the gate itself) ---------------------------

def test_placeholder_result_is_rejected():
    ed = _episode_data({"summary_text": "real-looking text", "is_placeholder": True})
    with pytest.raises(SummaryNotPersistableError, match="placeholder"):
        assert_summary_persistable(ed)


def test_empty_summary_text_is_rejected():
    ed = _episode_data({"summary_text": "   "})
    with pytest.raises(SummaryNotPersistableError, match="empty"):
        assert_summary_persistable(ed)


def test_ticker_missing_from_summary_is_rejected():
    # Random placeholder tickers (e.g. JPM/UNH) never appear as #ticker: links in
    # the body — the exact "Ticker Mismatch" the validate step used to raise late.
    ed = _episode_data(
        {"summary_text": "完整的中文摘要，沒有任何股票連結。"},
        tickers=["JPM", "UNH"],
    )
    with pytest.raises(SummaryNotPersistableError, match="missing from summary"):
        assert_summary_persistable(ed)


def test_real_summary_with_consistent_tickers_passes():
    ed = _episode_data(
        {"summary_text": "看好 [輝達](#ticker:NVDA) 與 [台積電](#ticker:2330) 的後市。"},
        tickers=["NVDA", "2330"],
    )
    assert_summary_persistable(ed)  # does not raise


def test_real_summary_without_tickers_passes():
    ed = _episode_data({"summary_text": "一篇沒有個股的總經分析。"}, tickers=[])
    assert_summary_persistable(ed)  # no tickers -> ticker check is N/A


# --- generate_summary gates BEFORE returning (i.e. before write steps) ------

def _config() -> PipelineConfig:
    cfg = MagicMock(spec=PipelineConfig)
    cfg.rerun_from = "summarize"
    cfg.podcast_name = "Gooaye"
    return cfg


def test_generate_summary_raises_on_placeholder_fallback():
    """The repro: external summarizer returns a placeholder -> step raises, so the
    later GCS/Firestore/Postgres/wiki steps never run."""
    services = MagicMock(spec=ServiceContainer)
    services.summarize_service = MagicMock()
    # Mimic placeholders.generate_placeholder_result: junk text + random tickers.
    services.summarize_service.generate_summary_from_text.return_value = {
        "summary_text": "# Episode Summary\n\n*Placeholder content - real summary generation pending.*",
        "svg_content": "<svg/>",
        "related_tickers": ["JPM", "UNH", "WMT"],
        "is_placeholder": True,
    }

    ed = EpisodeData(api_data={"title": "EP671"}, podcast_name="Gooaye", language="zh")
    ed.transcript_text = "long transcript ..."

    with pytest.raises(SummaryNotPersistableError):
        generate_summary(_config(), services, ed)


def test_generate_summary_succeeds_on_real_summary():
    services = MagicMock(spec=ServiceContainer)
    services.summarize_service = MagicMock()
    services.summarize_service.generate_summary_from_text.return_value = {
        "summary_text": "看好 [輝達](#ticker:NVDA) 的後市表現。",
        "svg_content": "<svg/>",
        "related_tickers": ["NVDA"],
    }

    ed = EpisodeData(api_data={"title": "EP"}, podcast_name="Gooaye", language="zh")
    ed.transcript_text = "long transcript ..."

    generate_summary(_config(), services, ed)  # does not raise
    assert ed.summary_result is not None
    assert "NVDA" in [t.upper() for t in ed.tickers]
