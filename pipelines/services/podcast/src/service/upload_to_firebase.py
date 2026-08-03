#!/usr/bin/env python3
"""
Firebase/Firestore Upload Service

This module handles uploading podcast episode data to Google Cloud Firestore.
"""

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.secrets_bootstrap import bootstrap

# Load secrets from GSM (idempotent — safe if already bootstrapped at entry point).
bootstrap()

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except ImportError:
    raise ImportError(
        "firebase-admin is required for Firebase upload functionality. "
        "Install it with: pip install firebase-admin"
    )

from src.models.podcast_models import PodcastEpisode  # noqa: E402


def _normalize_tags(tags: Optional[List[str]]) -> List[str]:
    """Canonical, deduped, sorted tag slugs.

    Enforces the curated vocabulary at this single persistence boundary so
    LLM-hallucinated junk (off-vocab proper nouns, fund/ETF names, ticker
    symbols) can never re-pollute either the ``episodes/{id}.tags`` array or the
    ``tags/{slug}/episodes`` fan-out, regardless of caller (ingest, regen,
    backfill). Idempotent — normalizing an already-normalized list is a no-op.
    """
    from src.podcast.content_builder.tag_vocabulary import (
        canonical_tag_slug,
        normalize_tag_slug,
    )
    return sorted({normalize_tag_slug(t) for t in (tags or []) if t and canonical_tag_slug(t)})


def _mirror_podcast_show_to_postgres(doc_id: str, metadata: Dict) -> None:
    """Best-effort dual-write of a ``podcasts/{doc_id}`` show doc into
    ``firestore_mirror.podcasts`` (Postgres), so ``get_podcast_show``/
    ``get_all_podcast_shows`` (read-flipped in P2) see show adds/edits.
    No-op without ``EPISODE_DATABASE_URL`` — same guard as the other live
    dual-write steps (``pipeline.steps.ticker_insights_export``).
    """
    url = os.getenv("EPISODE_DATABASE_URL")
    if not url:
        return
    try:
        import psycopg
    except ImportError:
        print("  ⚠ psycopg not available — skipping Postgres podcasts mirror")
        return

    from src.podcast.exporters import postgres_mirror

    try:
        with psycopg.connect(url, autocommit=True) as conn, conn.cursor() as cur:
            cur.execute(postgres_mirror.DDL_PODCASTS)
            postgres_mirror.upsert_podcast_show(cur, doc_id, metadata)
        print(f"  ✓ Mirrored to Postgres: {postgres_mirror.SCHEMA}.podcasts/{doc_id}")
    except Exception as e:  # noqa: BLE001 — best-effort, show metadata is not dedup-critical
        import traceback

        print(f"  ⚠ Postgres podcasts mirror failed (non-fatal): {e}")
        traceback.print_exc()


# Lazy import for GCS (only when needed)
def get_gcs_storage_service():
    """Lazy import for GCSStorageService to avoid import errors when not needed."""
    try:
        from src.service.gcs_storage_service import GCSStorageService
        return GCSStorageService
    except ImportError as e:
        raise ImportError(
            "google-cloud-storage is required for GCS upload functionality. "
            "Install it with: pip install google-cloud-storage"
        ) from e


class FirebaseService:
    """
    Service for uploading podcast data to Google Cloud Firestore.
    """
    
    def __init__(self):
        """
        Initialize Firebase Admin SDK and Firestore client.
        
        Raises:
            ValueError: If required credentials are missing
            Exception: If Firebase initialization fails
        """
        self._initialize_firebase()
        self.db = self._get_firestore_client()
        self.collection_name = "podcasts"
        self.document_id = "podcast"
    
    def _initialize_firebase(self) -> None:
        """
        Initialize Firebase Admin SDK with credentials from environment variables.
        
        Raises:
            ValueError: If credentials are missing or invalid
            Exception: If initialization fails
        """
        # Check if Firebase app is already initialized
        try:
            firebase_admin.get_app()
            # App already initialized, skip
            return
        except ValueError:
            # App not initialized, proceed with initialization
            pass
        
        # Get credentials from environment
        credentials_path = os.getenv("GCP_CREDENTIALS_PATH")
        credentials_json = os.getenv("GCP_CREDENTIALS_JSON")
        
        if not credentials_path and not credentials_json:
            raise ValueError(
                "GCP_CREDENTIALS_PATH or GCP_CREDENTIALS_JSON is required. "
                "Set one of them in your .env file."
            )
        
        # Initialize credentials
        cred = None
        if credentials_path:
            # Use credentials from file path
            cred_path = Path(credentials_path).expanduser().resolve()
            if not cred_path.exists():
                raise FileNotFoundError(
                    f"Credentials file not found: {cred_path}"
                )
            cred = credentials.Certificate(str(cred_path))
        elif credentials_json:
            # Use credentials from JSON string
            try:
                if isinstance(credentials_json, str):
                    creds_dict = json.loads(credentials_json)
                else:
                    creds_dict = credentials_json
                cred = credentials.Certificate(creds_dict)
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"Invalid JSON in GCP_CREDENTIALS_JSON: {e}"
                ) from e
        
        # Initialize Firebase Admin SDK
        try:
            firebase_admin.initialize_app(cred)
        except Exception as e:
            raise Exception(f"Failed to initialize Firebase Admin SDK: {e}") from e
    
    def _get_firestore_client(self) -> firestore.Client:
        """
        Get Firestore client, optionally with custom database ID.
        
        Returns:
            firestore.Client: Firestore client instance
            
        Note:
            The database must already exist in Google Cloud Console.
            Databases cannot be created programmatically - they must be created
            via Google Cloud Console or gcloud CLI.
        """
        database_id = os.getenv("FIRESTORE_DATABASE_ID")
        
        if database_id:
            # Use custom database ID (parameter name is 'database_id', not 'database')
            return firestore.client(database_id=database_id)
        else:
            # Use default database (default)
            return firestore.client()
    
    def upload_podcast_data(
        self,
        podcast_name: str,
        episode: PodcastEpisode,
        gcs_service=None,
        mp3_path: Optional[Path] = None,
        transcript_path: Optional[Path] = None,
        transcript_content: Optional[str] = None,
        summary_path: Optional[Path] = None,
        summary_content: Optional[str] = None,
        svg_path: Optional[Path] = None,
        svg_content: Optional[str] = None,
        tags: Optional[List[str]] = None,
        tickers: Optional[List[str]] = None
    ) -> None:
        """
        Upload podcast episode data to Firestore.
        
        Each episode is stored as a separate document to avoid Firestore's 1MB document size limit.
        Files are uploaded to GCS first, then URLs are stored in Firestore.
        
        Structure:
        - Collection: `episodes`
        - Document ID: `{podcast_name}_{episode_title}` (sanitized)
        - Document data: Episode metadata with GCS URLs
        
        Args:
            podcast_name: Name of the podcast
            episode: PodcastEpisode object containing episode data (may have URLs already set)
            gcs_service: Optional GCSStorageService instance for uploading files
            mp3_path: Optional path to MP3 file
            transcript_path: Optional path to transcript file
            transcript_content: Optional transcript content as string (for streaming mode)
            summary_path: Optional path to summary file
            summary_content: Optional summary content as string (for streaming mode)
            svg_path: Optional path to SVG file
            svg_content: Optional SVG content as string (for streaming mode)
        
        Raises:
            Exception: If upload fails
        """
        try:
            # Generate a stable, unique episode ID
            # Use hash of podcast_name + episode_title + created_time for uniqueness
            episode_id = self._generate_episode_id(podcast_name, episode)
            print(f"  📝 Uploading episode with ID: {episode_id}")
            
            # Upload files to GCS if GCS service is provided and episode doesn't already have URLs
            if gcs_service and not episode.mp3_url:
                print("  ☁️  Uploading files to GCS...")
                gcs_urls = gcs_service.upload_episode_files(
                    episode_id=episode_id,
                    podcast_name=podcast_name,
                    mp3_path=mp3_path,
                    transcript_path=transcript_path,
                    transcript_content=transcript_content,
                    summary_path=summary_path,
                    summary_content=summary_content,
                    svg_path=svg_path,
                    svg_content=svg_content,
                    skip_existing=True
                )
                
                # Update episode with GCS URLs
                episode.mp3_url = gcs_urls.get('mp3_url', '')
                episode.transcript_url = gcs_urls.get('transcript_url', '')
                episode.summary_url = gcs_urls.get('summary_url', '')
                episode.summary_image_url = gcs_urls.get('summary_image_url', '')
                episode.mp3_public_url = gcs_urls.get('mp3_public_url')
                episode.transcript_public_url = gcs_urls.get('transcript_public_url')
                episode.summary_public_url = gcs_urls.get('summary_public_url')
                episode.summary_image_public_url = gcs_urls.get('summary_image_public_url')
                episode.pptx_url = gcs_urls.get('pptx_url')
                episode.pptx_public_url = gcs_urls.get('pptx_public_url')
                episode.marp_markdown_url = gcs_urls.get('marp_markdown_url')
                episode.marp_markdown_public_url = gcs_urls.get('marp_markdown_public_url')
                
                print("  ✓ Files uploaded to GCS")
            
            # Get reference to the episode document
            episodes_collection = self.db.collection("episodes")
            doc_ref = episodes_collection.document(episode_id)
            
            # Stamp the canonical tag list onto the episode BEFORE building the doc dict,
            # so episodes/{id}.tags (contract §2.1: always present, may be empty) is
            # written in the SAME call as the rest of the doc — and any other consumer
            # of to_firestore_dict() (e.g. the Postgres mirror step, which runs right
            # after this one on the same episode object) sees the final tags too.
            episode.tags = _normalize_tags(tags)

            # Prepare episode data with episode_id included
            episode_data = episode.to_firestore_dict()
            episode_data['episode_id'] = episode_id  # Add episode_id to document for easy retrieval
            
            # Ensure podcast_name is set (use parameter if episode.podcast_name is empty)
            if not episode_data.get('podcast_name') and podcast_name:
                episode_data['podcast_name'] = podcast_name
            
            # Check if episode already exists
            existing_doc = doc_ref.get()
            if existing_doc.exists:
                print(f"  🔄 Updating existing episode document: {episode_id}")
                # Preserve existing podcast_name if new one is empty
                existing_data = existing_doc.to_dict() or {}
                if not episode_data.get('podcast_name') and existing_data.get('podcast_name'):
                    episode_data['podcast_name'] = existing_data['podcast_name']
                    print(f"  ⚠ Preserved existing podcast_name: {existing_data['podcast_name']}")
                # Contract invariants: created_time is immutable once the
                # episode exists, and platform-owned modified_* fields must not
                # be overwritten by pipeline regeneration writes.
                update_data = dict(episode_data)
                for protected_field in (
                    'created_time',
                    'modified_summary_url',
                    'modified_summary_content',
                    'modified_by',
                    'modified_at',
                ):
                    update_data.pop(protected_field, None)
                if update_data.get('retracted_at') is None:
                    update_data.pop('retracted_at', None)
                # Merge keeps unknown/frontend-owned fields intact.
                doc_ref.set(update_data, merge=True)
            else:
                print(f"  ✨ Creating new episode document: {episode_id}")
                # Create new episode document
                episode_data.setdefault('retracted_at', None)
                doc_ref.set(episode_data)
            
            # Upload episode to tags and tickers subcollections
            if tags or tickers:
                self.upload_tags_and_tickers(
                    episode_id=episode_id,
                    tags=tags or [],
                    tickers=tickers or [],
                    episode_data=episode_data
                )
            
        except Exception as e:
            error_msg = str(e)
            # Provide helpful error message if database doesn't exist
            if "does not exist" in error_msg or "404" in error_msg:
                database_id = os.getenv("FIRESTORE_DATABASE_ID", "(default)")
                project_id = os.getenv("GCP_PROJECT_ID")
                if not project_id:
                    # Try to get project ID from credentials
                    try:
                        creds_path = os.getenv("GCP_CREDENTIALS_PATH")
                        if creds_path:
                            with open(creds_path, 'r') as f:
                                creds_data = json.load(f)
                                project_id = creds_data.get('project_id', 'your-project')
                    except Exception:
                        project_id = 'your-project'
                
                raise Exception(
                    f"Firestore database '{database_id}' does not exist.\n"
                    f"Please create the database first:\n"
                    f"1. Go to: https://console.cloud.google.com/firestore/databases?project={project_id}\n"
                    f"2. Click 'Create Database'\n"
                    f"3. Choose 'Native mode' (recommended)\n"
                    f"4. Enter database ID: {database_id}\n"
                    f"5. Select location and click 'Create'\n\n"
                    f"Original error: {error_msg}"
                ) from e
            else:
                raise Exception(f"Failed to upload podcast data to Firestore: {e}") from e
    
    def _ensure_tag_exists(self, tag_name: str) -> None:
        """
        Ensure tag parent document exists (create if it doesn't).
        Parent documents are created implicitly when subcollection is accessed,
        but we can create an empty document for consistency.
        
        Args:
            tag_name: Tag name (normalized to lowercase)
        """
        try:
            tag_ref = self.db.collection("tags").document(tag_name)
            tag_doc = tag_ref.get()
            if not tag_doc.exists:
                # Create empty document (parent document can be empty)
                tag_ref.set({})
        except Exception:
            # If creation fails, it's okay - parent doc will be created implicitly
            pass
    
    def _ensure_ticker_exists(self, ticker_symbol: str) -> None:
        """
        Ensure ticker parent document exists (create if it doesn't).
        Parent documents are created implicitly when subcollection is accessed,
        but we can create an empty document for consistency.
        
        Args:
            ticker_symbol: Ticker symbol (normalized to uppercase)
        """
        try:
            ticker_ref = self.db.collection("tickers").document(ticker_symbol)
            ticker_doc = ticker_ref.get()
            if not ticker_doc.exists:
                # Create empty document (parent document can be empty)
                ticker_ref.set({})
        except Exception:
            # If creation fails, it's okay - parent doc will be created implicitly
            pass
    
    def _add_episode_to_tag(self, tag_name: str, episode_id: str, episode_data: Dict) -> None:
        """
        Add episode reference to tag's episodes subcollection.
        
        Args:
            tag_name: Tag name (normalized to lowercase)
            episode_id: Episode document ID
            episode_data: Episode data dictionary (from episode.to_firestore_dict())
        """
        try:
            tag_ref = self.db.collection("tags").document(tag_name)
            episode_ref = tag_ref.collection("episodes").document(episode_id)
            
            # Create episode document in subcollection with minimal fields
            episode_subdoc = {
                'episode_id': episode_id,
                'episode_title': episode_data.get('episode_title', ''),
                'podcast_name': episode_data.get('podcast_name', ''),
                'episode_number': episode_data.get('episode_number'),
                'created_time': episode_data.get('created_time')
            }
            
            episode_ref.set(episode_subdoc)
        except Exception as e:
            raise Exception(f"Failed to add episode to tag '{tag_name}': {e}") from e
    
    def _add_episode_to_ticker(self, ticker_symbol: str, episode_id: str, episode_data: Dict) -> None:
        """
        Add episode reference to ticker's episodes subcollection.
        
        Args:
            ticker_symbol: Ticker symbol (normalized to uppercase)
            episode_id: Episode document ID
            episode_data: Episode data dictionary (from episode.to_firestore_dict())
        """
        try:
            ticker_ref = self.db.collection("tickers").document(ticker_symbol)
            episode_ref = ticker_ref.collection("episodes").document(episode_id)
            
            # Create episode document in subcollection with minimal fields
            episode_subdoc = {
                'episode_id': episode_id,
                'episode_title': episode_data.get('episode_title', ''),
                'podcast_name': episode_data.get('podcast_name', ''),
                'episode_number': episode_data.get('episode_number'),
                'created_time': episode_data.get('created_time')
            }
            
            episode_ref.set(episode_subdoc)
        except Exception as e:
            raise Exception(f"Failed to add episode to ticker '{ticker_symbol}': {e}") from e
    
    def upload_tags_and_tickers(
        self,
        episode_id: str,
        tags: List[str],
        tickers: List[str],
        episode_data: Dict
    ) -> None:
        """
        Upload episode to tags and tickers subcollections.
        
        For each tag/ticker:
        1. Ensure parent document exists
        2. Add episode to subcollection
        
        Args:
            episode_id: Episode document ID
            tags: List of tag names (will be normalized to lowercase)
            tickers: List of ticker symbols (will be normalized to uppercase)
            episode_data: Episode data dictionary (from episode.to_firestore_dict())
        """
        if not tags and not tickers:
            return

        # Normalize tags (shared with upload_podcast_data's episode.tags stamp — same
        # vocabulary-filtered slug set both places, see _normalize_tags) and tickers.
        # The doc id is the NORMALIZED slug (lowercased, separators stripped) so
        # spellings like ``ai_supply_chain`` and ``aisupplychain`` can never fragment
        # into two docs; membership is tested on that same normalized form.
        normalized_tags = _normalize_tags(tags)
        normalized_tickers = [ticker.upper() for ticker in tickers if ticker]
        
        # Process tags
        for tag_name in normalized_tags:
            try:
                self._ensure_tag_exists(tag_name)
                self._add_episode_to_tag(tag_name, episode_id, episode_data)
            except Exception as e:
                print(f"  ⚠ Warning: Failed to add episode to tag '{tag_name}': {e}")
        
        # Process tickers
        for ticker_symbol in normalized_tickers:
            try:
                self._ensure_ticker_exists(ticker_symbol)
                self._add_episode_to_ticker(ticker_symbol, episode_id, episode_data)
            except Exception as e:
                print(f"  ⚠ Warning: Failed to add episode to ticker '{ticker_symbol}': {e}")
        
        if normalized_tags or normalized_tickers:
            print(f"  ✓ Added episode to {len(normalized_tags)} tags and {len(normalized_tickers)} tickers")
    
    def _generate_episode_id(self, podcast_name: str, episode: PodcastEpisode) -> str:
        """
        Generate a stable, unique episode ID.
        
        Uses podcast_name + episode_title for stable matching with API episodes.
        Falls back to episode_number if title is missing, then to hash-based if both are missing.
        
        Args:
            podcast_name: Name of the podcast
            episode: PodcastEpisode object
            
        Returns:
            Stable episode ID (URL-friendly)
        """
        # Use hash of podcast name to handle non-ASCII characters (e.g., Chinese)
        # This ensures consistent, URL-friendly identifiers regardless of language
        podcast_hash = hashlib.sha256(podcast_name.encode('utf-8')).hexdigest()[:12]
        
        # Also try to get a readable prefix if possible (for English podcast names)
        # Sanitize podcast name for URL (keep only alphanumeric, underscore, hyphen)
        sanitized_podcast = re.sub(r'[^a-zA-Z0-9_-]', '', podcast_name)
        # If sanitized name is meaningful (has letters/numbers, not just underscores), use it
        if sanitized_podcast and len(sanitized_podcast) > 0 and not sanitized_podcast.replace('_', '').replace('-', '').strip() == '':
            # Use sanitized name if it has actual content
            podcast_prefix = sanitized_podcast[:30]  # Limit length
        else:
            # If sanitized name is empty or only special chars, use hash prefix
            podcast_prefix = podcast_hash[:8]
        
        # Prefer episode_title for stable matching (always available from API)
        if episode.episode_title:
            # Use hash of title to ensure consistent length and avoid issues with special chars
            title_hash = hashlib.sha256(episode.episode_title.encode('utf-8')).hexdigest()[:16]
            episode_id = f"{podcast_prefix}_{title_hash}"
            print(f"  🔑 Generated episode ID (from title): {episode_id}")
            return episode_id
        
        # Fallback to episode_number if title is missing
        if episode.episode_number is not None:
            episode_id = f"{podcast_prefix}_ep{episode.episode_number}"
            print(f"  🔑 Generated episode ID (from number): {episode_id}")
            return episode_id
        
        # Last resort: use timestamp hash
        timestamp = episode.created_time.isoformat() if hasattr(episode.created_time, 'isoformat') else str(episode.created_time)
        unique_string = f"{podcast_name}|{timestamp}"
        hash_obj = hashlib.sha256(unique_string.encode('utf-8'))
        hash_hex = hash_obj.hexdigest()[:16]
        episode_id = f"{podcast_prefix}_{hash_hex}"
        print(f"  🔑 Generated episode ID (from timestamp): {episode_id}")
        return episode_id
    
    def get_podcast_episodes(self, podcast_name: str, limit: Optional[int] = None, order_by: str = "created_time", descending: bool = True) -> List[Dict]:
        """
        Get all episodes for a specific podcast (read-flipped onto firestore_mirror.episodes, P2).

        Args:
            podcast_name: Name of the podcast
            limit: Optional limit on number of episodes to return
            order_by: Field to sort by (default: "created_time")
            descending: Sort in descending order (default: True, newest first)

        Returns:
            List of episode dictionaries, sorted by created_time (newest first by default)
        """
        from src.service import postgres_mirror_reader
        return postgres_mirror_reader.get_podcast_episodes(
            podcast_name, limit=limit, order_by=order_by, descending=descending
        )

    def get_episode_by_id(self, episode_id: str) -> Optional[Dict]:
        """
        Get a single episode by its episode_id (read-flipped onto firestore_mirror.episodes, P2).

        Args:
            episode_id: The episode ID (document ID in Firestore, same as the mirror's PK)

        Returns:
            Episode dictionary if found, None otherwise
        """
        from src.service import postgres_mirror_reader
        return postgres_mirror_reader.get_episode_by_id(episode_id)

    def update_episode_fields(self, episode_id: str, fields: Dict[str, Any]) -> None:
        """Partial update of an existing episode document.

        Used by the ``--rerun-from spotify-metadata`` mode to refresh Spotify
        fields without rewriting the whole document. The episode must already
        exist; this method does not create new documents.
        """
        if not episode_id:
            raise ValueError("episode_id is required")
        if not fields:
            return
        try:
            self.db.collection("episodes").document(episode_id).update(fields)
        except Exception as e:
            raise Exception(f"Failed to update episode {episode_id}: {e}") from e
    
    def get_all_episodes(self, order_by: str = "created_time", descending: bool = True) -> List[Dict]:
        """
        Get all episodes (read-flipped onto firestore_mirror.episodes, P2).

        Args:
            order_by: Field to sort by (default: "created_time")
            descending: Sort in descending order (default: True, newest first)

        Returns:
            List of episode dictionaries, sorted by specified field
        """
        from src.service import postgres_mirror_reader
        return postgres_mirror_reader.get_all_episodes(order_by=order_by, descending=descending)

    def get_episode_by_fields(
        self,
        podcast_name: str,
        episode_title: str,
        episode_number: Optional[int] = None,
    ) -> Optional[Dict]:
        """
        Get a single episode by its identifying fields (read-flipped onto
        firestore_mirror.episodes, P2 — same match semantics: podcast_name AND
        episode_title, optionally narrowed by episode_number).

        Args:
            podcast_name: Name of the podcast
            episode_title: Episode title (primary identifier)
            episode_number: Optional episode number for additional matching

        Returns:
            Dictionary containing episode data plus an 'id' field for the
            document ID, or None if not found.
        """
        from src.service import postgres_mirror_reader
        return postgres_mirror_reader.get_episode_by_fields(
            podcast_name, episode_title, episode_number
        )

    def get_episode_by_title_and_number(
        self,
        episode_title: str,
        episode_number: Optional[int] = None,
    ) -> Optional[Dict]:
        """
        Get a single episode by title and number, without a podcast_name filter
        (read-flipped onto firestore_mirror.episodes, P2).

        This is a fallback method for cases where podcast_name might be empty.
        It queries by episode_title and optionally episode_number only.

        Args:
            episode_title: Episode title (primary identifier)
            episode_number: Optional episode number for additional matching

        Returns:
            Dictionary containing episode data plus an 'id' field for the
            document ID, or None if not found.
        """
        from src.service import postgres_mirror_reader
        return postgres_mirror_reader.get_episode_by_title_and_number(
            episode_title, episode_number
        )

    def get_all_podcasts(self) -> List[str]:
        """
        Get a list of all unique podcast names (read-flipped onto
        firestore_mirror.episodes, P2).

        Returns:
            List of podcast names (sorted alphabetically)
        """
        from src.service import postgres_mirror_reader
        return postgres_mirror_reader.get_all_podcast_names()

    def get_existing_episode_titles(self, podcast_name: str) -> set:
        """
        Get set of episode titles that already exist for a podcast (read-flipped
        onto firestore_mirror.episodes, P2).

        This is used for deduplication - only process episodes that don't exist yet.
        Uses episode_title as the primary matching field since it's always available.

        Args:
            podcast_name: Name of the podcast

        Returns:
            Set of episode titles (strings) that already exist
        """
        from src.service import postgres_mirror_reader
        return postgres_mirror_reader.get_existing_episode_titles(podcast_name)

    def get_existing_episode_numbers(self, podcast_name: str) -> set:
        """
        Get set of episode numbers that already exist for a podcast (read-flipped
        onto firestore_mirror.episodes, P2).

        This is used for additional deduplication matching (secondary to episode_title).

        Args:
            podcast_name: Name of the podcast

        Returns:
            Set of episode numbers (integers) that already exist
        """
        from src.service import postgres_mirror_reader
        return postgres_mirror_reader.get_existing_episode_numbers(podcast_name)

    def episode_exists(self, podcast_name: str, episode_title: str, episode_number: Optional[int] = None) -> bool:
        """
        Check if a specific episode already exists (read-flipped onto
        firestore_mirror.episodes, P2).

        This method queries by podcast_name and episode_title field, not by document
        ID, because older episodes may have hash-based document IDs. Querying by
        field ensures we find episodes regardless of their document ID format.

        Args:
            podcast_name: Name of the podcast
            episode_title: Episode title (always available from API)
            episode_number: Optional episode number (for additional matching if available)

        Returns:
            True if episode exists, False otherwise
        """
        from src.service import postgres_mirror_reader
        return postgres_mirror_reader.episode_exists(podcast_name, episode_title, episode_number)
    
    def upsert_podcast_show(self, podcast_name: str, metadata: Dict) -> None:
        """
        Create or update a podcast show document in the `podcasts` collection,
        dual-written into firestore_mirror.podcasts (best-effort — see
        ``_mirror_podcast_show_to_postgres``) so the :8003 /shows endpoints
        (read-flipped onto the mirror in P2) see the update.

        Args:
            podcast_name: Canonical podcast name (used as document ID after sanitizing)
            metadata: Show-level metadata dict (thumbnail_url, description, etc.)
        """
        doc_id = re.sub(r'[/]', '_', podcast_name)
        doc_ref = self.db.collection("podcasts").document(doc_id)
        metadata["podcast_name"] = podcast_name
        doc_ref.set(metadata, merge=True)
        _mirror_podcast_show_to_postgres(doc_id, metadata)

    def get_podcast_show(self, podcast_name: str) -> Optional[Dict]:
        """
        Get podcast show-level metadata (read-flipped onto
        firestore_mirror.podcasts, P2).

        Args:
            podcast_name: Canonical podcast name

        Returns:
            Show metadata dict or None if not found
        """
        from src.service import postgres_mirror_reader
        return postgres_mirror_reader.get_podcast_show(podcast_name)

    def get_all_podcast_shows(self) -> List[Dict]:
        """
        Get all podcast show documents (read-flipped onto
        firestore_mirror.podcasts, P2).

        Returns:
            List of show metadata dicts
        """
        from src.service import postgres_mirror_reader
        return postgres_mirror_reader.get_all_podcast_shows()

    def validate_episode_in_tags_and_tickers(
        self,
        episode_id: str,
        tags: List[str],
        tickers: List[str]
    ) -> Dict[str, bool]:
        """
        Validate that episode is tagged/tickered as expected (read-flipped onto
        firestore_mirror.episodes, P2).

        The former ``tags/{tag}/episodes`` and ``tickers/{ticker}/episodes``
        Firestore subcollections this used to check aren't mirrored (contract
        § 11.1 — they're pure derivations of ``episodes.tags`` /
        ``episodes.related_tickers``), so membership is now checked against
        those same arrays on the episode's own mirrored doc.

        Args:
            episode_id: Episode document ID
            tags: List of tag names that should be on this episode
            tickers: List of ticker symbols that should be on this episode

        Returns:
            Dictionary with validation results:
            - 'tags_valid': True if all tags are present
            - 'tickers_valid': True if all tickers are present
            - 'tags_details': Dict mapping tag_name -> present (bool)
            - 'tickers_details': Dict mapping ticker_symbol -> present (bool)
        """
        from src.service import postgres_mirror_reader
        return postgres_mirror_reader.validate_episode_in_tags_and_tickers(
            episode_id, tags, tickers
        )
