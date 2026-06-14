"""Pipeline orchestrator: coordinates the full podcast processing flow."""

import json
import os
import sys
import tempfile
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from src.pipeline import EpisodeProcessor, PipelineConfig
from src.pipeline.reconcile import reconcile_show_released_at_ms
from src.pipeline.steps import initialize_services
from src.service.download_podcasts import extract_podcast_id, fetch_episodes

from .firestore_reprocessor import process_firestore_episode


def _load_podcasts_from_db() -> List[Dict] | None:
    """Load active shows from Postgres. Returns None if DB unavailable or empty."""
    try:
        import os
        db_url = os.environ.get("WIKI_DATABASE_URL")
        if not db_url:
            return None
        from shared.wiki_builder import get_show_repository
        repo = get_show_repository(db_url)
        if repo is None:
            return None
        shows = repo.list_shows(active_only=True)
        if not shows:
            return None
        print(f"Loaded {len(shows)} active show(s) from Postgres show registry")
        return [s.to_pipeline_config() for s in shows]
    except Exception as e:
        print(f"Warning: Could not load shows from DB, falling back to config file: {e}")
        return None


def _source_to_podcast(source: Dict) -> Dict:
    """Map a platform ContentSourcePublic record to the pipeline's podcast dict shape."""
    transcript_service = source.get("transcript_service")
    transcript_option = (
        {"transcript_service": transcript_service, "model": source.get("transcript_model")}
        if transcript_service
        else {}
    )
    return {
        "name": source.get("name"),
        "link": source.get("feed_url"),
        "spotify_show_link": source.get("spotify_url"),
        "transcript_option": transcript_option,
        "lookback_days": source.get("lookback_days"),
        "max_episodes": source.get("max_episodes"),
        # Legacy count field; the recency window is the real filter when lookback_days is set.
        "limit": source.get("max_episodes"),
    }


def _load_podcasts_from_platform() -> List[Dict] | None:
    """Load active podcast shows from the platform /api/sources.

    Returns None when the platform pull is disabled (TINBOKER_PLATFORM_API_URL unset)
    or unavailable, so the caller falls back to the Postgres registry / JSON config.
    """
    try:
        from shared.platform_client import fetch_sources
        items = fetch_sources("podcast")
        if not items:
            return None
        print(f"Loaded {len(items)} active podcast(s) from platform /api/sources")
        return [_source_to_podcast(s) for s in items]
    except Exception as e:
        print(f"Warning: Could not load podcasts from platform, falling back: {e}")
        return None


def load_podcasts_config(config_path: Path) -> List[Dict]:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        podcasts = json.load(f)
    if not isinstance(podcasts, list):
        raise ValueError("Config file must contain a list of podcast objects")
    return podcasts


def create_podcast_config_mapping(config_path: Path) -> Dict[str, Dict]:
    try:
        podcasts = load_podcasts_config(config_path)
        mapping = {}
        for podcast in podcasts:
            name = podcast.get("name")
            transcript_option = podcast.get("transcript_option")
            if name and transcript_option:
                mapping[name] = transcript_option
        return mapping
    except Exception as e:
        print(f"Warning: Could not load podcast config mapping: {e}")
        return {}


def run_pipeline(
    config_file: Path = Path("podcasts_tw.json"),
    rerun_from: Optional[str] = None,
    transcript_service: str = "groq",
    use_file_mode: bool = False,
    reuse_existing_transcript: bool = False,
    episode_id: Optional[str] = None,
    fill_limit: bool = False,
) -> None:
    """Run the full podcast processing pipeline."""
    print("=" * 60)
    print("Podcast Processing Pipeline")
    print("=" * 60)
    print(f"Config file: {config_file}")
    print(f"Transcript Service: {transcript_service}")
    print(f"Mode: {'File-based' if use_file_mode else 'Streaming'}")
    print(f"Rerun from: {rerun_from if rerun_from else 'Full pipeline'}")
    if episode_id:
        print(f"Episode ID: {episode_id} (fetching from Firestore)")
    print("=" * 60)

    base_config = PipelineConfig(
        config_file=config_file,
        podcast_name="",
        podcast_link="",
        stt_service_name=transcript_service,
        rerun_from=rerun_from,
        reuse_existing_transcript=reuse_existing_transcript,
        use_file_mode=use_file_mode,
        temp_dir=Path(tempfile.gettempdir()) / "podcast_downloader" if not use_file_mode else None,
    )

    print("\nInitializing services...")
    try:
        service_container = initialize_services(base_config)
        print("All services initialized successfully\n")
    except Exception as e:
        print("\nFatal error: Service initialization failed")
        print(f"  {e}")
        print("\nPipeline terminated. Please fix the errors above and try again.")
        sys.exit(1)

    podcast_config_mapping = create_podcast_config_mapping(config_file)

    podcasts = _load_podcasts_from_platform()
    if podcasts is None:
        podcasts = _load_podcasts_from_db()
    if podcasts is None:
        try:
            podcasts = load_podcasts_config(config_file)
        except Exception as e:
            print(f"Warning: Could not load podcasts config: {e}")
            podcasts = []

    if episode_id:
        _handle_firestore_mode(
            episode_id=episode_id,
            config_file=config_file,
            rerun_from=rerun_from,
            transcript_service=transcript_service,
            use_file_mode=use_file_mode,
            reuse_existing_transcript=reuse_existing_transcript,
            base_config=base_config,
            service_container=service_container,
            podcast_config_mapping=podcast_config_mapping,
            podcasts=podcasts,
        )
        return

    _handle_api_mode(
        podcasts=podcasts,
        config_file=config_file,
        rerun_from=rerun_from,
        transcript_service=transcript_service,
        use_file_mode=use_file_mode,
        reuse_existing_transcript=reuse_existing_transcript,
        fill_limit=fill_limit,
        base_config=base_config,
        service_container=service_container,
    )


def _handle_firestore_mode(
    episode_id: str,
    config_file: Path,
    rerun_from: Optional[str],
    transcript_service: str,
    use_file_mode: bool,
    reuse_existing_transcript: bool,
    base_config: PipelineConfig,
    service_container,
    podcast_config_mapping: Dict,
    podcasts: List[Dict],
) -> None:
    if not service_container.firebase_service:
        print("Error: Cannot fetch episode from Firestore without Firebase service")
        sys.exit(1)

    common_kwargs = dict(
        config_file=config_file,
        rerun_from=rerun_from,
        transcript_service=transcript_service,
        use_file_mode=use_file_mode,
        reuse_existing_transcript=reuse_existing_transcript,
        base_config=base_config,
        service_container=service_container,
        podcast_config_mapping=podcast_config_mapping,
        podcasts=podcasts,
    )

    try:
        if episode_id.lower() == "all":
            _process_all_firestore_episodes(service_container, common_kwargs)
        else:
            _process_single_firestore_episode(episode_id, service_container, common_kwargs)
    except Exception as e:
        print(f"Error fetching/processing episode from Firestore: {e}")
        traceback.print_exc()
        sys.exit(1)


def _process_all_firestore_episodes(service_container, common_kwargs: dict) -> None:
    print("Fetching all episodes from Firestore...")
    all_episodes = service_container.firebase_service.get_all_episodes()
    if not all_episodes:
        print("No episodes found in Firestore")
        sys.exit(1)

    print(f"Found {len(all_episodes)} episode(s) in Firestore\n")
    success_count = 0
    error_count = 0

    for idx, firestore_episode in enumerate(all_episodes, 1):
        ep_id = firestore_episode.get("id")
        ep_title = firestore_episode.get("episode_title", "Unknown")
        print(f"\n{'='*60}")
        print(f"Episode {idx}/{len(all_episodes)}: {ep_title}")
        print(f"Episode ID: {ep_id}")
        print(f"{'='*60}")

        try:
            success = process_firestore_episode(firestore_episode, ep_id, **common_kwargs)
            if success:
                success_count += 1
                print(f"Episode {idx} processed successfully")
            else:
                error_count += 1
                print(f"Episode {idx} failed")
        except Exception as e:
            error_count += 1
            print(f"Error processing episode {idx}: {e}")
            traceback.print_exc()

    print(f"\n{'='*60}")
    print("Processing Summary")
    print(f"{'='*60}")
    print(f"Total episodes: {len(all_episodes)}")
    print(f"Successful: {success_count}")
    print(f"Failed: {error_count}")
    print(f"{'='*60}")
    if error_count > 0:
        sys.exit(1)


def _process_single_firestore_episode(episode_id: str, service_container, common_kwargs: dict) -> None:
    print(f"Fetching episode {episode_id} from Firestore...")
    firestore_episode = service_container.firebase_service.get_episode_by_id(episode_id)
    if not firestore_episode:
        print(f"Episode not found in Firestore: {episode_id}")
        sys.exit(1)

    print(f"Found episode: {firestore_episode.get('episode_title', 'Unknown')}")
    success = process_firestore_episode(firestore_episode, episode_id, **common_kwargs)

    if success:
        print("\n" + "=" * 60)
        print("Pipeline completed successfully!")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("Pipeline completed with errors")
        print("=" * 60)
        sys.exit(1)


def _handle_api_mode(
    podcasts: List[Dict],
    config_file: Path,
    rerun_from: Optional[str],
    transcript_service: str,
    use_file_mode: bool,
    reuse_existing_transcript: bool,
    fill_limit: bool,
    base_config: PipelineConfig,
    service_container,
) -> None:
    if not podcasts:
        try:
            podcasts = load_podcasts_config(config_file)
            print(f"Found {len(podcasts)} podcast(s) to process\n")
        except Exception as e:
            print(f"Error loading config: {e}")
            sys.exit(1)
    else:
        print(f"Found {len(podcasts)} podcast(s) to process\n")

    if not use_file_mode:
        temp_dir = Path(tempfile.gettempdir()) / "podcast_downloader"
        temp_dir.mkdir(parents=True, exist_ok=True)
        base_config.temp_dir = temp_dir

    for podcast in podcasts:
        _process_single_podcast(
            podcast=podcast,
            config_file=config_file,
            rerun_from=rerun_from,
            transcript_service=transcript_service,
            use_file_mode=use_file_mode,
            reuse_existing_transcript=reuse_existing_transcript,
            fill_limit=fill_limit,
            base_config=base_config,
            service_container=service_container,
        )

    if not use_file_mode and base_config.temp_dir and base_config.temp_dir.exists():
        try:
            for file in base_config.temp_dir.glob("*"):
                if file.is_file():
                    file.unlink()
        except Exception as e:
            print(f"Warning: Failed to clean up temp directory: {e}")

    print("\n" + "=" * 60)
    print("Pipeline completed!")
    print("=" * 60)


def _process_single_podcast(
    podcast: Dict,
    config_file: Path,
    rerun_from: Optional[str],
    transcript_service: str,
    use_file_mode: bool,
    reuse_existing_transcript: bool,
    fill_limit: bool,
    base_config: PipelineConfig,
    service_container,
) -> None:
    name = podcast.get("name")
    link = podcast.get("link")
    limit = podcast.get("limit", 2)
    lookback_days = podcast.get("lookback_days")
    max_episodes = podcast.get("max_episodes")
    spotify_show_link = podcast.get("spotify_show_link")
    transcript_option = podcast.get("transcript_option", {})

    if not name or not link:
        print("Warning: Skipping invalid podcast entry (missing 'name' or 'link')")
        return

    podcast_transcript_service = transcript_option.get("transcript_service", transcript_service)
    podcast_transcript_model = transcript_option.get("model", None)

    print(f"\n{'='*60}")
    print(f"Processing: {name}")
    print(f"URL: {link}")
    if lookback_days:
        cap_note = f", max {max_episodes}" if max_episodes else ""
        print(f"Window: last {lookback_days} day(s){cap_note}")
    else:
        print(f"Limit: {limit} episodes")
    print(f"{'='*60}")

    try:
        podcast_id = extract_podcast_id(link)
        if not podcast_id or podcast_id.strip() == "":
            print(f"Error: Invalid podcast ID extracted from URL: {link}")
            return

        print("Fetching episode list from API...")
        episodes = fetch_episodes(podcast_id)

        if not episodes:
            print("No episodes found or error fetching episodes")
            return

        print(f"Found {len(episodes)} episodes from API")

        # Keep the full feed (every episode + its true datePublished) before the
        # window/limit narrowing below — the reconcile pass needs all of it.
        feed_episodes = list(episodes)

        if fill_limit:
            episodes = _filter_unprocessed_episodes(
                episodes, name, max_episodes or limit, service_container
            )
        elif lookback_days or max_episodes:
            episodes = _select_recent_episodes(
                episodes,
                lookback_days=lookback_days,
                max_episodes=max_episodes,
                legacy_limit=limit,
            )
            print(f"Selected {len(episodes)} episode(s) to process")
        elif limit and limit > 0:
            episodes = episodes[:limit]
            print(f"Limited to latest {len(episodes)} episodes")

        podcast_config = PipelineConfig(
            config_file=config_file,
            podcast_name=name,
            podcast_link=link,
            spotify_show_link=spotify_show_link,
            episode_limit=max_episodes or limit,
            stt_service_name=podcast_transcript_service,
            stt_model=podcast_transcript_model,
            rerun_from=rerun_from,
            reuse_existing_transcript=reuse_existing_transcript,
            use_file_mode=use_file_mode,
            fill_limit=fill_limit,
            temp_dir=base_config.temp_dir,
        )

        processor = EpisodeProcessor(podcast_config, service_container)

        if not episodes:
            print("No episodes to process")
            return

        successful = 0
        failed = 0
        for i, api_episode_data in enumerate(episodes, 1):
            success = processor.process_episode(api_episode_data)
            if success:
                successful += 1
            else:
                failed += 1

        print(f"\nSummary for {name}:")
        print(f"  Successful: {successful}")
        print(f"  Failed: {failed}")
        print(f"  Total: {len(episodes)}")

        # Self-heal released_at_ms for this show's already-ingested episodes
        # against the feed's true datePublished. Gated on actual ingest activity
        # (successful > 0) so idle 10-minute runs add no Firestore reads; new
        # episodes drop only a few times a week per show. Best-effort: a failure
        # here must never fail the run. Disable with RECONCILE_RELEASE_DATES=0.
        if successful > 0 and os.environ.get("RECONCILE_RELEASE_DATES", "1") != "0":
            try:
                reconcile_show_released_at_ms(
                    service_container.firebase_service, name, feed_episodes
                )
            except Exception as e:  # noqa: BLE001
                print(f"  [reconcile] skipped for {name} (non-critical): {e}")

    except Exception as e:
        print(f"Error processing podcast {name}: {e}")
        traceback.print_exc()


def _parse_episode_date(value) -> Optional[datetime]:
    """Parse an episode ``datePublished`` (ISO 8601, e.g. ``2026-06-03T07:34:50.000Z``).

    Returns a timezone-aware UTC datetime, or None when the value is missing/unparseable.
    """
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _select_recent_episodes(
    episodes: List[Dict],
    *,
    lookback_days: Optional[int],
    max_episodes: Optional[int],
    legacy_limit: Optional[int],
) -> List[Dict]:
    """Select episodes by recency window, then cap.

    The source API returns episodes newest-first. When ``lookback_days`` is set we keep
    only episodes whose ``datePublished`` falls within the window; if NONE of the
    episodes carry a parseable date we fall back to the count cap so a feed/API change
    can't silently stall ingestion. ``max_episodes`` (else ``legacy_limit``) caps the
    result to the most-recent N.
    """
    cap = max_episodes or legacy_limit
    if lookback_days and lookback_days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        dated = [(ep, _parse_episode_date(ep.get("datePublished"))) for ep in episodes]
        if not any(dt is not None for _, dt in dated):
            print(
                f"Warning: no parseable datePublished on {len(episodes)} episode(s); "
                f"falling back to count cap ({cap})"
            )
            return episodes[:cap] if cap else episodes
        kept = [ep for ep, dt in dated if dt is not None and dt >= cutoff]
        print(f"Recency window {lookback_days}d: kept {len(kept)} of {len(episodes)} episode(s)")
        if cap and cap > 0 and len(kept) > cap:
            kept = kept[:cap]
            print(f"Capped to {cap} most-recent episode(s)")
        return kept
    if cap and cap > 0:
        return episodes[:cap]
    return episodes


def _filter_unprocessed_episodes(episodes, name, limit, service_container) -> list:
    total_episodes = len(episodes)
    non_processed = []
    checked_count = 0
    for episode in episodes:
        checked_count += 1
        if service_container.firebase_service:
            existing = service_container.firebase_service.get_episode_by_fields(
                podcast_name=name,
                episode_title=episode.get("title"),
                episode_number=episode.get("episodeNumber"),
            )
            if not existing:
                existing = service_container.firebase_service.get_episode_by_title_and_number(
                    episode_title=episode.get("title"),
                    episode_number=episode.get("episodeNumber"),
                )
            if (
                existing
                and existing.get("mp3_url")
                and existing.get("transcript_url")
                and existing.get("summary_url")
                and existing.get("summary_image_url")
            ):
                continue
        non_processed.append(episode)
        if len(non_processed) >= limit:
            break

    print(f"Found {len(non_processed)} non-processed episodes (checked {checked_count} out of {total_episodes} total)")
    return non_processed
