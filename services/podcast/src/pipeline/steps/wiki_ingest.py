"""
Step 5b: Ingest episode data into the knowledge wiki.

Runs after summarization and GCS upload. Writes/updates markdown wiki pages
so knowledge compounds across episodes without a graph database.
"""

from ..config import PipelineConfig
from ..service_container import ServiceContainer
from ..episode_data import EpisodeData


def ingest_into_wiki(
    config: PipelineConfig,
    services: ServiceContainer,
    episode_data: EpisodeData,
) -> None:
    """Write episode data into the wiki.

    This is a best-effort step — failures here do not block the pipeline.
    """
    should_ingest = config.rerun_from in [None, "download", "transcribe", "summarize"]
    if not should_ingest:
        return
    if not episode_data.summary_result:
        return

    try:
        from src.wiki_builder.ingest import ingest_episode
        from src.wiki_builder.index import rebuild_index
    except ImportError:
        print("  ⚠ wiki_builder not available — skipping wiki ingest")
        return

    episode_title = episode_data.api_data.get("title", "Untitled Episode")
    print(f"  📖 Ingesting into wiki: {episode_title}")

    try:
        summary = episode_data.summary_result
        source_urls = {}
        if episode_data.gcs_urls:
            for key in ["mp3_url", "transcript_url", "summary_url"]:
                val = episode_data.gcs_urls.get(key)
                if val:
                    source_urls[key.replace("_url", "")] = val

        date = None
        if episode_data.spotify_metadata:
            date = episode_data.spotify_metadata.get("release_date")
        if not date and episode_data.created_time:
            date = episode_data.created_time.strftime("%Y-%m-%d")

        tickers = [str(t) for t in (episode_data.tickers or [])]
        tags = [str(t) for t in (episode_data.tags or [])]

        ep_path = ingest_episode(
            podcast_name=episode_data.podcast_name,
            episode_number=episode_data.api_data.get("episodeNumber"),
            title=episode_title,
            date=date,
            tickers=tickers,
            tags=tags,
            summary_text=summary.get("summary_text", ""),
            events_markdown=summary.get("events_markdown"),
            ticker_recommendations=summary.get("ticker_recommendations"),
            source_urls=source_urls or None,
        )

        rebuild_index()
        print(f"  ✓ Wiki updated: {ep_path.name}")

    except Exception as e:
        import traceback
        print(f"  ⚠ Wiki ingest failed (non-fatal): {e}")
        traceback.print_exc()
