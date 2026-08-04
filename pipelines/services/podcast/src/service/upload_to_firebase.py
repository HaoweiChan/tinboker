#!/usr/bin/env python3
"""Episode/show persistence service.

Historically the Firestore writer. Since P4 (``docs/firestore-contract.md``
§ 11.5) every read AND every write goes to Postgres (``podcast_db``, schema
``firestore_mirror``); the class name and this module name are kept so the
dozens of ``scripts/`` entry points and the pipeline wiring stay put.

``self.db`` is still a real Firestore client, built lazily on first touch — only
the archival/backfill scripts under ``scripts/`` reach for it. Nothing on the
live pipeline path does, so the admin SDK is never bootstrapped in a normal run.
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
    symbols) can never re-pollute the ``episodes/{id}.tags`` array, regardless of
    caller (ingest, regen, backfill). Idempotent — normalizing an
    already-normalized list is a no-op.
    """
    from src.podcast.content_builder.tag_vocabulary import (
        canonical_tag_slug,
        normalize_tag_slug,
    )
    return sorted({normalize_tag_slug(t) for t in (tags or []) if t and canonical_tag_slug(t)})


def _write_podcast_show_to_postgres(doc_id: str, metadata: Dict) -> None:
    """Upsert a ``podcasts/{doc_id}`` show doc into ``firestore_mirror.podcasts``.

    Sole write since P4 (the Firestore half is gone), so it raises instead of
    logging: a silently-dropped show edit would never show up on the :8003
    ``/shows`` endpoints that read this table.
    """
    import psycopg

    from src.podcast.exporters import postgres_mirror

    url = os.getenv("EPISODE_DATABASE_URL")
    if not url:
        raise RuntimeError(
            "EPISODE_DATABASE_URL is not set — cannot persist the podcast show doc."
        )
    with psycopg.connect(url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(postgres_mirror.DDL_PODCASTS)
        postgres_mirror.upsert_podcast_show(cur, doc_id, metadata)
    print(f"  ✓ Persisted show: {postgres_mirror.SCHEMA}.podcasts/{doc_id}")


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
    """Service for reading and writing podcast data (Postgres since P4)."""

    def __init__(self):
        """Cheap — no credentials touched until something asks for ``.db``."""
        self._db = None
        self.collection_name = "podcasts"
        self.document_id = "podcast"

    @property
    def db(self):
        """The raw Firestore client, bootstrapped on first touch.

        Only the archival/backfill scripts under ``scripts/`` still use it; the
        live pipeline reads and writes Postgres exclusively, so a normal run
        never initializes the admin SDK.
        """
        if self._db is None:
            self._initialize_firebase()
            self._db = self._get_firestore_client()
        return self._db


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
        """Partial update of an existing episode document (jsonb-merge, P4).

        Used by ``--rerun-from spotify-metadata`` and the ``released_at_ms``
        reconcile/backfill paths. The episode must already exist — a missing row
        raises rather than fabricating a partial doc, same as the Firestore
        ``update()`` this replaced (which 404s on a missing document).
        """
        if not episode_id:
            raise ValueError("episode_id is required")
        if not fields:
            return

        import psycopg

        from src.podcast.exporters import postgres_mirror

        url = os.getenv("EPISODE_DATABASE_URL")
        if not url:
            raise RuntimeError(
                "EPISODE_DATABASE_URL is not set — cannot update episode fields."
            )
        with psycopg.connect(url, autocommit=True) as conn, conn.cursor() as cur:
            if not postgres_mirror.merge_episode_doc(cur, episode_id, fields):
                raise RuntimeError(
                    f"Failed to update episode {episode_id}: no such row in "
                    f"{postgres_mirror.SCHEMA}.episodes"
                )


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
        """Create or update a show doc in ``firestore_mirror.podcasts``, which the
        :8003 /shows endpoints read.

        Args:
            podcast_name: Canonical podcast name (used as document ID after sanitizing)
            metadata: Show-level metadata dict (thumbnail_url, description, etc.)
        """
        doc_id = re.sub(r'[/]', '_', podcast_name)
        metadata["podcast_name"] = podcast_name
        _write_podcast_show_to_postgres(doc_id, metadata)

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
