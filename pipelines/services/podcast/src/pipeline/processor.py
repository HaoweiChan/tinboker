"""
Episode Processor

This module contains the EpisodeProcessor class that orchestrates all processing steps.
"""

import os
from typing import Dict

from src.models.podcast_models import PodcastEpisode

from .config import PipelineConfig
from .episode_data import EpisodeData
from .service_container import ServiceContainer
from .steps import (
    download_episode,
    export_ticker_insights,
    generate_summary,
    ingest_into_wiki,
    initialize_stt_service,
    mirror_episode_to_postgres,
    render_social_cards,
    transcribe_episode,
    trigger_social_publish,
    upload_to_firestore,
    upload_to_gcs,
    validate_episode,
)
from .utils import determine_language


class EpisodeProcessor:
    """Main processor for podcast episodes."""
    
    def __init__(self, config: PipelineConfig, services: ServiceContainer):
        """
        Initialize episode processor.
        
        Args:
            config: Pipeline configuration
            services: Service container with initialized services
        """
        self.config = config
        self.services = services
        
        # Re-initialize STT service if config has different service/model than current
        # This allows per-podcast transcript options
        if services.stt_service:
            current_service_name = services.stt_service.get_service_name().lower()
            config_service_name = config.stt_service_name.lower()
            needs_reinit = False
            
            # Check if service type changed
            # Map service names: "whisper" and "openai" both use WhisperService
            if config_service_name in ["whisper", "openai"]:
                config_service_name = "whisper"
            
            if current_service_name != config_service_name:
                needs_reinit = True
            # For Groq, also check if model changed
            elif config_service_name == "groq" and hasattr(services.stt_service, 'model'):
                current_model = getattr(services.stt_service, 'model', None)
                expected_model = config.stt_model if config.stt_model else "whisper-large-v3-turbo"
                if current_model != expected_model:
                    needs_reinit = True
            
            if needs_reinit:
                try:
                    services.stt_service = initialize_stt_service(config)
                    service_info = f"{services.stt_service.get_service_name()}"
                    if config.stt_model:
                        service_info += f" (model: {config.stt_model})"
                    print(f"  🔄 Re-initialized STT service: {service_info}")
                except Exception as e:
                    print(f"  ⚠ Warning: Failed to re-initialize STT service: {e}")
                    # Continue with existing service
    
    def process_episode(self, api_episode_data: Dict) -> bool:
        """
        Process a single episode through all steps.
        
        Args:
            api_episode_data: Episode data from API
            
        Returns:
            True if successful, False otherwise
        """
        episode_data = None
        try:
            # Create fresh episode data - NO CLEARING NEEDED!
            # Each episode gets its own isolated data instance
            episode_data = EpisodeData(
                api_data=api_episode_data,
                podcast_name=self.config.podcast_name,
                language=determine_language(self.config.podcast_name)
            )

            # Load existing data from Firestore/GCS if available
            self._load_existing_data(episode_data)

            # Check if we should skip (based on what we have in episode_data)
            if self._should_skip_episode(episode_data):
                return True  # Skip is successful

            episode_title = api_episode_data.get('title', 'Untitled Episode')
            episode_number = api_episode_data.get('episodeNumber')
            print(f"\nProcessing: {episode_title}")
            if episode_number is not None:
                print(f"  Episode #: {episode_number}")

            # Execute steps in order based on rerun_from logic
            # Each step mutates episode_data fields directly
            # Step 1: Download MP3 + Fetch Spotify Metadata
            if self.config.rerun_from == "spotify-metadata":
                # Force a fresh Spotify lookup even if the existing doc already
                # has partial metadata loaded by `_load_existing_data`.
                episode_data.spotify_metadata = None
            download_episode(self.config, self.services, episode_data)

            # Backfill-only path: write the refreshed Spotify fields and stop.
            if self.config.rerun_from == "spotify-metadata":
                self._upsert_spotify_metadata(episode_data)
                return True

            # Step 2: Transcribe
            transcribe_episode(self.config, self.services, episode_data)

            # Step 3: Summarize
            generate_summary(self.config, self.services, episode_data)

            # Step 4: Upload to GCS
            upload_to_gcs(self.config, self.services, episode_data)

            # Step 4b: Render + upload social-card PNGs — ONLY when auto-publish is on
            # (its only consumer). In the default manual flow the brand reviews each
            # episode on the admin Social page, where the platform renders the PNGs on
            # demand ("產生卡片圖" button / auto-on-publish) — so we don't pre-render +
            # store cards for every episode that never gets posted. The social_cards
            # DATA + marp_markdown are always built (cheap) and drive the admin preview.
            if os.environ.get("SOCIAL_AUTOPUBLISH", "").strip().lower() in ("1", "true", "yes", "on"):
                render_social_cards(self.config, self.services, episode_data)

            # Step 5: Upload to Firestore
            upload_to_firestore(self.config, self.services, episode_data)

            # Step 5b: Ingest into knowledge wiki (best-effort)
            ingest_into_wiki(self.config, self.services, episode_data)

            # Step 5c: Mirror episode into Postgres (best-effort; no-op w/o EPISODE_DATABASE_URL)
            mirror_episode_to_postgres(self.config, self.services, episode_data)

            # Step 5d: Export ticker insights to Firestore subcollection per platform contract
            export_ticker_insights(self.config, self.services, episode_data)

            # Step 5e: Trigger the platform to fan the new episode out to Threads (best-effort)
            trigger_social_publish(self.config, self.services, episode_data)

            # Step 6: Validate
            validate_episode(self.config, self.services, episode_data)

            print(f"  ✓ Successfully processed: {episode_title}\n")
            return True

        except Exception as e:
            episode_title = api_episode_data.get('title', 'Unknown Episode')
            print(f"  ✗ Error processing episode {episode_title}: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # Delete temp MP3 from /tmp after each episode to prevent tmpfs exhaustion
            # across a multi-show nightly run. In file mode the MP3 lives in a persistent
            # downloads dir and must not be removed here.
            if (
                episode_data is not None
                and not self.config.use_file_mode
                and episode_data.mp3_path is not None
                and episode_data.mp3_path.exists()
            ):
                episode_data.mp3_path.unlink(missing_ok=True)
    
    def _load_existing_data(self, episode_data: EpisodeData) -> None:
        """
        Load existing data from Firestore/GCS into episode_data.
        
        This fills the episode_data with existing data so that steps can check
        if they need to run or can skip (idempotency).
        
        Args:
            episode_data: Episode data to populate
        """
        if not self.services.firebase_service:
            return
        
        episode_title = episode_data.api_data.get('title', 'Untitled Episode')
        episode_number = episode_data.api_data.get('episodeNumber')
        
        # Try to get existing episode from Firestore
        existing = self.services.firebase_service.get_episode_by_fields(
            podcast_name=self.config.podcast_name,
            episode_title=episode_title,
            episode_number=episode_number
        )
        
        if existing:
            # Load episode ID
            episode_data.episode_id = existing.get('id')
            
            # Load GCS URLs
            # For rerun_from="summarize", we want to preserve MP3 and transcript URLs
            # but regenerate summary URLs, so we don't load summary URLs
            if existing.get('mp3_url') or existing.get('transcript_url'):
                if self.config.rerun_from == "summarize":
                    # For summarize rerun, only load MP3 and transcript URLs
                    # Summary URLs will be regenerated
                    episode_data.gcs_urls = {
                        'mp3_url': existing.get('mp3_url'),
                        'transcript_url': existing.get('transcript_url'),
                        'mp3_public_url': existing.get('mp3_public_url'),
                        'transcript_public_url': existing.get('transcript_public_url'),
                        # Don't load summary URLs - they will be regenerated
                    }
                else:
                    # For other modes, load all URLs
                    episode_data.gcs_urls = {
                        'mp3_url': existing.get('mp3_url'),
                        'transcript_url': existing.get('transcript_url'),
                        'summary_url': existing.get('summary_url'),
                        'summary_image_url': existing.get('summary_image_url'),
                        'mp3_public_url': existing.get('mp3_public_url'),
                        'transcript_public_url': existing.get('transcript_public_url'),
                        'summary_public_url': existing.get('summary_public_url'),
                        'summary_image_public_url': existing.get('summary_image_public_url'),
                        'events_markdown_url': existing.get('events_markdown_url'),
                        'events_markdown_public_url': existing.get('events_markdown_public_url'),
                        'sentences_markdown_url': existing.get('sentences_markdown_url'),
                        'sentences_markdown_public_url': existing.get('sentences_markdown_public_url'),
                        'pptx_url': existing.get('pptx_url'),
                        'pptx_public_url': existing.get('pptx_public_url'),
                        'marp_markdown_url': existing.get('marp_markdown_url'),
                        'marp_markdown_public_url': existing.get('marp_markdown_public_url'),
                        'ticker_insights_url': existing.get('ticker_insights_url') or existing.get('ticker_recommendations_url'),
                        'ticker_insights_public_url': existing.get('ticker_insights_public_url') or existing.get('ticker_recommendations_public_url'),
                        'ticker_marp_markdown_url': existing.get('ticker_marp_markdown_url'),
                        'ticker_marp_markdown_public_url': existing.get('ticker_marp_markdown_public_url'),
                    }
            
            # Load Spotify metadata if available
            if existing.get('spotify_id'):
                episode_data.spotify_metadata = {
                    'spotify_id': existing.get('spotify_id'),
                    'spotify_url': existing.get('spotify_url'),
                    'spotify_embed_url': existing.get('spotify_embed_url'),
                    'release_date': existing.get('spotify_release_date'),
                    'description': existing.get('spotify_description'),
                    'duration_ms': existing.get('spotify_duration_ms'),
                    'images': existing.get('spotify_images', []),
                }
            
            # Load created_time if available
            if existing.get('created_time'):
                from datetime import datetime
                created_time = existing.get('created_time')
                if isinstance(created_time, str):
                    episode_data.created_time = datetime.fromisoformat(created_time)
                elif isinstance(created_time, datetime):
                    episode_data.created_time = created_time
            
            # Load tags and tickers if available
            if existing.get('tags'):
                episode_data.tags = [tag.lower() if isinstance(tag, str) else str(tag).lower() for tag in existing.get('tags', [])]
            if existing.get('related_tickers'):
                episode_data.tickers = [ticker.upper() if isinstance(ticker, str) else str(ticker).upper() for ticker in existing.get('related_tickers', [])]
            
            # For rerun_from="summarize", download transcript from GCS
            if self.config.rerun_from == "summarize" and self.services.gcs_service:
                transcript_url = existing.get('transcript_url')
                if transcript_url:
                    try:
                        # Use new download method that returns dict with text, sentences, and words
                        transcript_data = self.services.gcs_service.download_transcript_by_gcs_url(transcript_url)
                        if transcript_data and transcript_data.get('text'):
                            episode_data.transcript_text = transcript_data.get('text', '')
                            episode_data.transcript_words = transcript_data.get('words')
                            # Extract sentences from transcript data
                            sentences_data = transcript_data.get('sentences', [])
                            if sentences_data:
                                from src.models.podcast_models import Sentence
                                episode_data.transcript_sentences = [
                                    Sentence(**s) if isinstance(s, dict) else s
                                    for s in sentences_data
                                ]
                            print(f"  ♻ Loaded transcript from GCS ({len(episode_data.transcript_text):,} characters)")
                            if episode_data.transcript_sentences:
                                print(f"  ♻ Sentence-level timing available ({len(episode_data.transcript_sentences)} sentences)")
                            if episode_data.transcript_words:
                                print(f"  ♻ Word-level timing available ({len(episode_data.transcript_words)} words)")
                    except Exception as e:
                        print(f"  ⚠ Warning: Could not download transcript from GCS: {e}")
    
    def _should_skip_episode(self, episode_data: EpisodeData) -> bool:
        """
        Check if episode should be skipped based on what we have in episode_data.
        
        After loading existing data, we check if we have everything needed.
        If we have everything, we skip. If we're missing something, we proceed.
        
        Args:
            episode_data: Episode data to check
            
        Returns:
            True if episode should be skipped, False otherwise
        """
        episode_title = episode_data.api_data.get('title', 'Unknown Episode')
        episode_number = episode_data.api_data.get('episodeNumber')
        episode_info = episode_title
        if episode_number is not None:
            episode_info += f" (#{episode_number})"
        
        # Check if episode exists in Firestore (we loaded it in _load_existing_data)
        has_existing_episode = episode_data.episode_id is not None
        
        # Special handling for rerun_from modes
        if self.config.rerun_from == "download":
            # For rerun_from="download", treat each episode as new and rerun all steps
            # Don't skip - proceed to download MP3 and process everything
            return False
        
        if self.config.rerun_from == "transcribe":
            # For rerun_from="transcribe", we want to re-transcribe even if episode exists
            # Don't skip - proceed to download MP3 and transcribe
            return False
        
        if self.config.rerun_from == "summarize":
            # For rerun_from="summarize", we need transcript in episode_data
            if not has_existing_episode:
                print(f"  ⏭ Skipping episode (not found in Firestore, cannot download transcript): {episode_info}")
                return True
            if not episode_data.transcript_text:
                print(f"  ⏭ Skipping episode (no transcript available in GCS): {episode_info}")
                return True
            # We have transcript, proceed to regenerate summary
            return False
        
        if self.config.rerun_from == "upload":
            # For rerun_from="upload", we need GCS URLs in episode_data
            if not has_existing_episode:
                print(f"  ⏭ Skipping episode (not found in Firestore, cannot upload): {episode_info}")
                return True
            if not episode_data.gcs_urls:
                print(f"  ⏭ Skipping episode (no GCS URLs available): {episode_info}")
                return True
            # We have GCS URLs, proceed to re-upload
            return False
        
        if self.config.rerun_from == "validate":
            # For rerun_from="validate", we need episode in Firestore
            if not has_existing_episode:
                print(f"  ⏭ Skipping episode (not found in Firestore, cannot validate): {episode_info}")
                return True
            # Episode exists, proceed to validate
            return False

        if self.config.rerun_from == "spotify-metadata":
            # Need an existing doc to patch and a show link to query Spotify.
            if not has_existing_episode:
                print(f"  ⏭ Skipping episode (not in Firestore, cannot patch): {episode_info}")
                return True
            if not self.config.spotify_show_link:
                print(f"  ⏭ Skipping episode (no spotify_show_link configured): {episode_info}")
                return True
            return False
        
        # Normal mode: Skip if episode already exists and we have all required data
        if has_existing_episode:
            # If reuse_transcript, we still want to process (regenerate summary)
            if self.config.reuse_existing_transcript:
                return False
            # Check if we have all required data (GCS URLs indicate complete processing)
            if episode_data.gcs_urls and all([
                episode_data.gcs_urls.get('mp3_url'),
                episode_data.gcs_urls.get('transcript_url'),
                episode_data.gcs_urls.get('summary_url'),
                episode_data.gcs_urls.get('summary_image_url'),
            ]):
                print(f"  ⏭ Skipping existing episode (already fully processed): {episode_info}")
                return True

        return False

    def _upsert_spotify_metadata(self, episode_data: EpisodeData) -> None:
        """Patch only the Spotify fields on an existing Firestore episode doc.

        Used by ``--rerun-from spotify-metadata``. Maps the metadata-helper key
        names (``release_date``, ``description``, ``duration_ms``, ``images``)
        to the Firestore field names (``spotify_release_date``, ...).
        """
        if not self.services.firebase_service:
            print("  ⚠ Firebase service unavailable; cannot persist Spotify metadata")
            return
        if not episode_data.episode_id:
            print("  ⚠ No episode_id on the loaded record; cannot patch")
            return
        meta = episode_data.spotify_metadata or {}
        if not meta:
            print("  ⚠ No Spotify metadata fetched; nothing to patch")
            return
        fields = {
            "spotify_id": meta.get("spotify_id"),
            "spotify_url": meta.get("spotify_url"),
            "spotify_embed_url": meta.get("spotify_embed_url"),
            "spotify_release_date": PodcastEpisode.normalize_spotify_release_date(
                meta.get("release_date")
            ),
            "spotify_description": meta.get("description"),
            "spotify_duration_ms": meta.get("duration_ms"),
            "spotify_images": meta.get("images", []),
        }
        # Drop None values so we don't overwrite existing fields with nulls.
        fields = {k: v for k, v in fields.items() if v is not None}
        self.services.firebase_service.update_episode_fields(
            episode_data.episode_id, fields
        )
        print(f"  ✓ Patched Spotify fields on {episode_data.episode_id}: {sorted(fields.keys())}")
