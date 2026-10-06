"""Optional, single-call theme extraction; the API is its only write destination."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict

from shared import platform_client

from ..config import PipelineConfig
from ..episode_data import EpisodeData
from ..service_container import ServiceContainer

logger = logging.getLogger(__name__)


def _json_object(text: str) -> str:
    """Models often wrap the object in a code fence or a sentence; keep the outermost braces."""
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if 0 <= start < end else text


def extract_theme_views(
    config: PipelineConfig, services: ServiceContainer, episode_data: EpisodeData,
) -> None:
    """Fail open without retrying, including on invalid model output or a failed PUT."""
    episode_id = episode_data.episode_id or "unknown"
    if config.rerun_from not in (None, "download", "transcribe", "summarize", "theme-views"):
        return
    try:
        if not platform_client.admin_base_url() or not os.environ.get("TINBOKER_WRITE_TOKEN"):
            logger.info("Theme views skipped for %s: API URL or write token is unset", episode_id)
            return
        # Opt-in: without its own model pin this would add a full-transcript call on the
        # global model to every ingested episode, back-catalogue included.
        if not os.environ.get("THEME_VIEWS_EXTRACTOR_MODEL"):
            logger.info("Theme views skipped for %s: THEME_VIEWS_EXTRACTOR_MODEL is unset", episode_id)
            return
        from podcast.content_builder.llm import get_model, load_prompt
        from podcast.content_builder.theme_views import build_episode_input, validate_theme_views
        from shared.sectors import load_universe

        # Resolve configuration before fetching inputs or taxonomy. Disable SDK retries too.
        model = get_model("theme_views_extractor", max_retries=0, timeout=120.0)
        if not episode_data.episode_id:
            raise ValueError("episode id is missing")
        summary = (episode_data.summary_result or {}).get("summary_text")
        transcript = {
            "sentences": [
                sentence if isinstance(sentence, dict) else asdict(sentence)
                for sentence in (episode_data.transcript_sentences or [])
            ],
        }
        if config.rerun_from == "theme-views" and services.gcs_service:
            urls = episode_data.gcs_urls or {}
            if not transcript["sentences"] and urls.get("transcript_url"):
                transcript = services.gcs_service.download_transcript_by_gcs_url(urls["transcript_url"])
            if not summary and urls.get("summary_url"):
                summary = services.gcs_service.download_text_by_gcs_url(urls["summary_url"])
        if not summary:
            raise ValueError("summary is missing")
        episode_input, starts, anchors, text = build_episode_input(
            episode_id, transcript, summary, podcaster=episode_data.podcast_name,
        )
        taxonomy = load_universe()["exposures"]
        preferred = "、".join(
            theme.get("display_zh") or theme.get("display_name") or ""
            for theme in taxonomy
        )
        prompt = load_prompt("theme_views_extractor")
        system = prompt["system"].replace("{preferred_theme_names}", preferred)
        # Keep the proven instructions, identifying the actual show in each request.
        system = system.replace("Gooaye 股癌", episode_data.podcast_name)
        response = model.invoke([("system", system), ("human", episode_input)])
        views = validate_theme_views(json.loads(_json_object(response.content)), episode_id, starts, anchors, text, taxonomy)
        released_at_ms = episode_data.api_data.get("released_at_ms")
        if episode_data.episode:
            released_at_ms = episode_data.episode.resolved_publish_ms()
        body = {
            "podcaster": episode_data.podcast_name,
            "episode_number": str(episode_data.api_data.get("episodeNumber") or ""),
            "released_at_ms": released_at_ms,
            "source": "pipeline",
            "theme_views": views,
        }
        if platform_client.put_theme_views(episode_id, body) is None:
            logger.warning("Theme views skipped for %s: PUT did not store a result", episode_id)
            return
        logger.info("Theme views stored for %s: %d views", episode_id, len(views))
    except Exception as exc:
        # Exception messages may contain provider credentials/URLs: log only the type.
        logger.warning("Theme views skipped for %s: %s", episode_id, type(exc).__name__)
