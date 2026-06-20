"""Episode watcher: polls feeds and triggers the pipeline for new episodes.

Runs as an async background task inside the podcast-api FastAPI app. Each cycle:
1. Load active shows (platform API -> Postgres registry -> JSON config fallback).
2. For each show, fetch the latest episodes from its canonical RSS feed
   (falling back to the podcasttomp3 mirror) — see ``service.feed_source``.
3. Compare against Firestore to find unprocessed episodes.
4. Run the processing pipeline for each new episode in a thread pool.

The lightweight check (steps 1-3) only reads feed metadata; the heavy
download/transcribe/summarize pipeline (step 4) runs solely for episodes that
are genuinely new, so an idle cycle costs a feed fetch plus a few Firestore reads.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("watcher")


@dataclass
class WatcherConfig:
    enabled: bool = True
    poll_interval_minutes: int = 10
    max_concurrent: int = 1
    episodes_per_show: int = 3


@dataclass
class PollResult:
    show_name: str
    checked_at: str
    new_episodes: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class WatcherStatus:
    running: bool = False
    last_poll_at: str | None = None
    next_poll_at: str | None = None
    total_polls: int = 0
    total_new_episodes: int = 0
    processing_now: list[str] = field(default_factory=list)
    last_results: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "last_poll_at": self.last_poll_at,
            "next_poll_at": self.next_poll_at,
            "total_polls": self.total_polls,
            "total_new_episodes": self.total_new_episodes,
            "processing_now": list(self.processing_now),
            "last_results": list(self.last_results),
        }


class EpisodeWatcher:
    """Watches RSS feeds for new episodes and triggers pipeline processing."""

    def __init__(self, config: WatcherConfig | None = None) -> None:
        self.config = config or WatcherConfig()
        self.status = WatcherStatus()
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if not self.config.enabled:
            logger.info("Episode watcher is disabled by config")
            return
        self._stop_event.clear()
        self.status.running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(
            "Episode watcher started (poll every %d min)",
            self.config.poll_interval_minutes,
        )

    async def stop(self) -> None:
        self._stop_event.set()
        self.status.running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Episode watcher stopped")

    async def trigger_poll(self) -> list[PollResult]:
        """Manually trigger a single poll cycle (used by the admin endpoint)."""
        return await self._run_poll_cycle()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._run_poll_cycle()
            except Exception:
                logger.exception("Watcher poll cycle failed")
            interval = self.config.poll_interval_minutes * 60
            self.status.next_poll_at = _utcnow_iso(offset_seconds=interval)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                break
            except asyncio.TimeoutError:
                pass

    async def _run_poll_cycle(self) -> list[PollResult]:
        now = _utcnow_iso()
        self.status.last_poll_at = now
        self.status.total_polls += 1
        logger.info("Poll cycle #%d started", self.status.total_polls)

        shows = await asyncio.to_thread(_load_active_shows)
        if not shows:
            logger.warning("No active shows found; skipping cycle")
            return []

        results: list[PollResult] = []
        for show in shows:
            result = await self._check_show(show)
            results.append(result)

        self.status.last_results = [_result_to_dict(r) for r in results]
        logger.info(
            "Poll cycle #%d done: %d show(s), %d new episode(s)",
            self.status.total_polls,
            len(shows),
            sum(len(r.new_episodes) for r in results),
        )
        return results

    async def _check_show(self, show: dict[str, Any]) -> PollResult:
        name = show.get("name", "Unknown")
        link = show.get("link", "")
        result = PollResult(show_name=name, checked_at=_utcnow_iso())

        if not link:
            result.error = "missing feed link"
            return result

        try:
            new_episodes = await asyncio.to_thread(
                _find_new_episodes, show, self.config.episodes_per_show
            )
        except Exception as exc:
            result.error = str(exc)
            logger.warning("Error checking %s: %s", name, exc)
            return result

        if not new_episodes:
            return result

        for ep in new_episodes:
            ep_title = ep.get("title", "?")
            result.new_episodes.append(ep_title)
            self.status.total_new_episodes += 1
            logger.info("New episode detected: [%s] %s", name, ep_title)
            await self._process_episode(show, ep)

        return result

    async def _process_episode(
        self, show: dict[str, Any], episode: dict[str, Any]
    ) -> None:
        ep_title = episode.get("title", "?")
        show_name = show.get("name", "?")
        tag = f"{show_name} / {ep_title}"

        self.status.processing_now.append(tag)
        try:
            await asyncio.to_thread(
                _run_pipeline_for_episode, show, episode
            )
            logger.info("Finished processing: %s", tag)
        except Exception:
            logger.exception("Pipeline failed for: %s", tag)
        finally:
            if tag in self.status.processing_now:
                self.status.processing_now.remove(tag)


# ======================================================================
# Pure helpers (run in thread pool — no async)
# ======================================================================

def _utcnow_iso(offset_seconds: int = 0) -> str:
    dt = datetime.now(timezone.utc)
    if offset_seconds:
        from datetime import timedelta
        dt += timedelta(seconds=offset_seconds)
    return dt.isoformat()


def _result_to_dict(r: PollResult) -> dict[str, Any]:
    return {
        "show_name": r.show_name,
        "checked_at": r.checked_at,
        "new_episodes": r.new_episodes,
        "error": r.error,
    }


def _load_active_shows() -> list[dict[str, Any]]:
    """Load active shows using the same 3-tier fallback as the orchestrator."""
    from src.podcast.orchestrator import (
        _load_podcasts_from_db,
        _load_podcasts_from_platform,
        load_podcasts_config,
    )

    shows = _load_podcasts_from_platform()
    if shows is None:
        shows = _load_podcasts_from_db()
    if shows is None:
        try:
            shows = load_podcasts_config(Path("podcasts_tw.json"))
        except Exception as exc:
            logger.warning("Could not load podcasts config: %s", exc)
            shows = []
    return shows or []


def _find_new_episodes(
    show: dict[str, Any], limit: int = 3
) -> list[dict[str, Any]]:
    """Fetch the latest episodes for *show* and return those not yet in Firestore.

    Reads the show's canonical RSS feed (falling back to the podcasttomp3 mirror)
    via :func:`fetch_feed_episodes`, so a freshly-published episode is detected
    within the poll interval rather than after the mirror catches up hours later.
    """
    from src.service.feed_source import fetch_feed_episodes

    name = show.get("name", "Unknown")
    episodes = fetch_feed_episodes(show)
    if not episodes:
        return []

    candidates = episodes[:limit]

    from src.service.upload_to_firebase import FirebaseService
    try:
        fb = FirebaseService()
    except Exception:
        logger.warning("Firebase unavailable; cannot check existing episodes for %s", name)
        return []

    new: list[dict[str, Any]] = []
    for ep in candidates:
        existing = fb.get_episode_by_fields(
            podcast_name=name,
            episode_title=ep.get("title"),
            episode_number=ep.get("episodeNumber"),
        )
        if existing and _is_fully_processed(existing):
            continue
        new.append(ep)
    return new


def _is_fully_processed(episode: dict[str, Any]) -> bool:
    return all(
        episode.get(k)
        for k in ("mp3_url", "transcript_url", "summary_url", "summary_image_url")
    )


def _run_pipeline_for_episode(
    show: dict[str, Any], episode: dict[str, Any]
) -> None:
    """Run the full pipeline for a single episode (blocking)."""
    from src.pipeline import EpisodeProcessor, PipelineConfig
    from src.pipeline.steps import initialize_services

    name = show.get("name", "Unknown")
    link = show.get("link", "")
    spotify_show_link = show.get("spotify_show_link")
    transcript_option = show.get("transcript_option", {})
    transcript_service = transcript_option.get("transcript_service", "groq")
    transcript_model = transcript_option.get("model")

    config_file = Path("podcasts_tw.json")
    temp_dir = Path(tempfile.gettempdir()) / "podcast_watcher"
    temp_dir.mkdir(parents=True, exist_ok=True)

    config = PipelineConfig(
        config_file=config_file,
        podcast_name=name,
        podcast_link=link,
        spotify_show_link=spotify_show_link,
        stt_service_name=transcript_service,
        stt_model=transcript_model,
        use_file_mode=False,
        temp_dir=temp_dir,
    )

    service_container = initialize_services(config)
    processor = EpisodeProcessor(config, service_container)
    success = processor.process_episode(episode)
    if not success:
        raise RuntimeError(f"Pipeline returned failure for [{name}] {episode.get('title')}")


def load_watcher_config() -> WatcherConfig:
    """Read watcher settings from configs/default.yaml."""
    from shared.config import load_yaml_config

    cfg = load_yaml_config(Path(__file__).resolve().parent.parent / "configs" / "default.yaml")
    watcher_cfg = cfg.get("watcher", {})
    return WatcherConfig(
        enabled=watcher_cfg.get("enabled", True),
        poll_interval_minutes=watcher_cfg.get("poll_interval_minutes", 10),
        max_concurrent=watcher_cfg.get("max_concurrent", 1),
        episodes_per_show=watcher_cfg.get("episodes_per_show", 3),
    )
