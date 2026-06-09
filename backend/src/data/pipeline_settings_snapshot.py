"""Static snapshot of the agents' podcast pipeline configuration.

The source of truth is the tinboker-agents repo
(`services/podcast/configs/default.yaml`). This is a committed, read-only snapshot for
operator reference in the admin Pipeline Settings page — NOT a live read. Values may
drift from the live config until this snapshot is refreshed (see SNAPSHOT_META).

To refresh: copy the current default.yaml values here and bump SNAPSHOT_META.
"""

# Mirrors services/podcast/configs/default.yaml at the commit in SNAPSHOT_META.
PIPELINE_SETTINGS: dict = {
    "preprocessor": {
        "max_line_length": 150,
        "min_lines_warning": 10,
        "max_lines_warning": 5000,
        "default_language": "en",
        "detect_speakers": True,
        "mark_segments": True,
        "enable_event_blocks": True,
        "block_coverage_threshold": 0.8,
        "segmentation_model": "gemini-2.0-flash",
        "segmentation_temperature": 0.0,
        "min_block_confidence": 0.6,
        "allow_block_overlap": True,
    },
    "extractor": {
        "min_evidence_lines": 1,
        "max_events": 20,
        "quote_min_words": 5,
        "quote_max_words": 150,
        "min_event_confidence": 0.7,
    },
    "researcher": {
        "max_searches_per_event": 5,
        "max_results_per_query": 5,
        "source_priority": ["official", "news", "analyst", "wiki"],
        "recency_days": 90,
        "confidence_threshold": 0.7,
        "confidence_weights": {"official": 1.0, "news": 0.8, "analyst": 0.6, "wiki": 0.4},
    },
    "writer": {
        "target_word_count": 800,
        "word_count_tolerance_pct": 20,
        "tone": "investor",
        "language": "zh-TW",
        "include_sections": [
            "executive_summary",
            "event_details",
            "conflicting_views",
            "winners_losers",
            "open_questions",
            "sources",
        ],
        "section_weights": {
            "executive_summary": 0.15,
            "event_details": 0.50,
            "winners_losers": 0.20,
            "open_questions": 0.10,
            "sources": 0.05,
        },
    },
    "llm": {
        "default_provider": "openrouter",
        "default_model": "openrouter:xiaomi/mimo-v2.5",
        "extractor_model": "openrouter:xiaomi/mimo-v2.5",
        "writer_model": "openrouter:xiaomi/mimo-v2.5",
        "marp_writer_model": "openrouter:xiaomi/mimo-v2.5",
        "ticker_extractor_model": "openrouter:xiaomi/mimo-v2.5",
        "key_insights_extractor_model": "openrouter:xiaomi/mimo-v2.5",
        "segmentation_model": "gemini-2.5-pro",
        "temperatures": {"extractor": 0.1, "writer": 0.4, "marp_writer": 0.4, "ticker_extractor": 0.1, "key_insights_extractor": 0.3},
        "token_limits": {
            "extractor_input": 100000,
            "extractor_output": 16000,
            "writer_input": 32000,
            "writer_output": 8192,
            "marp_writer_output": 8192,
            "ticker_extractor_output": 2048,
            "key_insights_extractor_output": 1024,
        },
    },
    "search": {"default_engine": "tavily", "timeout_seconds": 30},
    "storage": {"type": "local", "output_dir": "./outputs"},
    "pipeline": {
        "gap_threshold": 10,
        "unfilled_threshold": 3,
        "retry": {"max_retries": 3, "backoff_seconds": [5, 15, 30]},
    },
    "gcp": {"project_id": "gen-lang-client-0901363254", "gcs_bucket_name": "graphfolio-articles"},
}

SNAPSHOT_META: dict = {
    "source": "pipelines/services/podcast/src/podcast/content_builder/llm.py",
    "snapshot_of_commit": "HEAD",
    "snapshot_date": "2026-06-08",
    "read_only": False,
    "note": (
        "Defaults from code. Admin overrides (if any) are merged on top."
    ),
}
