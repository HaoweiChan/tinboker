"""
Podcast service for managing podcast data from Firestore
"""
import os
import re
import asyncio
from typing import Optional, List
from datetime import datetime
from pathlib import Path
import json
from dotenv import load_dotenv
from google.cloud import storage
from google.oauth2 import service_account
from src.services.firestore_service import FirestoreService
from src.models.podcast import Podcast, Episode
from src.schemas.search import SearchResultItem
from src.cache.redis_client import cache_get, cache_set, cache_delete, cache_delete_pattern
from src.cache.cache_config import CACHE_TTL
from src.config import settings
import httpx
import logging

# Load environment variables
load_dotenv()


class PodcastService:
    """Service for podcast operations"""
    
    def __init__(self, firestore_service: Optional[FirestoreService] = None):
        """
        Initialize podcast service
        
        Args:
            firestore_service: Optional Firestore service instance
        """
        self.firestore_service = firestore_service or FirestoreService()
        self._gcs_client: Optional[storage.Client] = None
        self._semaphore = asyncio.Semaphore(20)
    
    def _get_gcs_client(self) -> Optional[storage.Client]:
        """Get or create GCS client for fetching content"""
        if self._gcs_client is not None:
            return self._gcs_client
        
        import logging
        logger = logging.getLogger(__name__)
        
        # Try to reuse Firebase Admin credentials first (if Firebase is initialized)
        # Since FirestoreService already loaded credentials successfully, we can read them the same way
        try:
            import firebase_admin
            from firebase_admin import credentials as firebase_credentials
            app = firebase_admin.get_app()
            firebase_cred = app.credential
            if firebase_cred and isinstance(firebase_cred, firebase_credentials.Certificate):
                # The Certificate object stores the credential path or info
                # Try to get the service account info from the certificate
                try:
                    # Method 1: Try to read from the certificate's internal path
                    if hasattr(firebase_cred, '_cert_path') and firebase_cred._cert_path:
                        with open(firebase_cred._cert_path, 'r') as f:
                            service_account_info = json.load(f)
                            gcs_credentials = service_account.Credentials.from_service_account_info(service_account_info)
                            project_id = service_account_info.get('project_id')
                            self._gcs_client = storage.Client(credentials=gcs_credentials, project=project_id)
                            logger.debug("Created GCS client using Firebase credentials from certificate file")
                            return self._gcs_client
                    # Method 2: Try to access internal _info attribute
                    elif hasattr(firebase_cred, '_info'):
                        service_account_info = firebase_cred._info
                        gcs_credentials = service_account.Credentials.from_service_account_info(service_account_info)
                        project_id = service_account_info.get('project_id')
                        self._gcs_client = storage.Client(credentials=gcs_credentials, project=project_id)
                        logger.debug("Created GCS client using Firebase credentials from _info")
                        return self._gcs_client
                except (AttributeError, FileNotFoundError, json.JSONDecodeError, Exception) as e:
                    logger.debug(f"Could not extract credentials from Firebase Certificate: {e}")
        except (ValueError, ImportError, AttributeError) as e:
            # Firebase not initialized, continue to other methods
            logger.debug(f"Firebase not initialized: {e}")
            pass
        
        # Try credentials from environment (same pattern as FirestoreService)
        # Read credentials the same way FirestoreService does
        credentials_path = os.getenv("GCP_CREDENTIALS_PATH")
        # Check GCP_CREDENTIALS_JSON first (same as FirestoreService), then GCS_SERVICE_ACCOUNT_JSON
        credentials_json = os.getenv("GCP_CREDENTIALS_JSON") or os.getenv("GCS_SERVICE_ACCOUNT_JSON")
        
        if credentials_path:
            # Use credentials from file path
            try:
                cred_path = Path(credentials_path).expanduser().resolve()
                if cred_path.exists():
                    credentials = service_account.Credentials.from_service_account_file(str(cred_path))
                    # Read project_id from the file
                    with open(cred_path, 'r') as f:
                        cred_info = json.load(f)
                        project_id = cred_info.get("project_id")
                    self._gcs_client = storage.Client(credentials=credentials, project=project_id)
                    logger.debug("Created GCS client using credentials file")
                    return self._gcs_client
                else:
                    logger.warning(f"Credentials file not found: {cred_path}")
            except Exception as e:
                logger.warning(f"Failed to load credentials from file {credentials_path}: {e}")
        
        if credentials_json:
            # Use credentials from JSON string
            try:
                # Handle both string and already-parsed JSON
                if isinstance(credentials_json, str):
                    # Strip whitespace and check if it's empty
                    credentials_json = credentials_json.strip()
                    if not credentials_json:
                        logger.warning("GCP_CREDENTIALS_JSON is set but empty or whitespace only")
                    else:
                        # Try to parse the JSON
                        creds_dict = json.loads(credentials_json)
                        credentials = service_account.Credentials.from_service_account_info(creds_dict)
                        project_id = creds_dict.get("project_id")
                        self._gcs_client = storage.Client(credentials=credentials, project=project_id)
                        logger.info("Created GCS client using credentials JSON")
                        return self._gcs_client
                else:
                    # Already a dict
                    credentials = service_account.Credentials.from_service_account_info(credentials_json)
                    project_id = credentials_json.get("project_id")
                    self._gcs_client = storage.Client(credentials=credentials, project=project_id)
                    logger.info("Created GCS client using credentials dict")
                    return self._gcs_client
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse GCP_CREDENTIALS_JSON (length: {len(credentials_json) if isinstance(credentials_json, str) else 'N/A'}): {e}")
                if isinstance(credentials_json, str) and len(credentials_json) > 0:
                    logger.debug(f"First 100 chars of credentials_json: {credentials_json[:100]}")
            except Exception as e:
                logger.warning(f"Failed to create GCS client with credentials JSON: {e}")
        
        # Try default credentials (from environment or gcloud CLI)
        try:
            self._gcs_client = storage.Client()
            return self._gcs_client
        except Exception:
            return None
    
    def _parse_gs_url(self, gs_url: str) -> Optional[tuple[str, str]]:
        """
        Parse GCS URL into bucket name and blob path
        
        Handles:
        - gs://bucket/path/to/file
        - https://storage.googleapis.com/bucket/path/to/file
        
        Returns:
            Tuple of (bucket_name, blob_path) or None if invalid
        """
        if not gs_url:
            return None
        
        # Handle gs:// URLs
        if gs_url.startswith("gs://"):
            parts = gs_url[5:].split("/", 1)
            if len(parts) == 2:
                return (parts[0], parts[1])
            return None
        
        # Handle https://storage.googleapis.com/ URLs
        pattern = r"https://storage\.googleapis\.com/([^/]+)/(.+)"
        match = re.match(pattern, gs_url)
        if match:
            return (match.group(1), match.group(2))
        
        return None
    
    async def _fetch_gcs_content(self, gs_url: str, timeout: float = 10.0) -> str:
        """
        Fetch content from GCS blob with timeout
        
        Args:
            gs_url: GCS URL (gs:// or https://)
            timeout: Timeout in seconds (default: 10.0)
            
        Returns:
            Content as string, or empty string if fetch fails or times out
        """
        parsed = self._parse_gs_url(gs_url)
        if not parsed:
            return ""
        
        bucket_name, blob_path = parsed
        client = self._get_gcs_client()
        if not client:
            return ""
        
        def _fetch_sync():
            """Synchronous GCS fetch operation"""
            try:
                bucket = client.bucket(bucket_name)
                blob = bucket.blob(blob_path)
                if blob.exists():
                    return blob.download_as_text()
                else:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.debug(f"GCS blob does not exist: {gs_url}")
                    return ""
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Error fetching GCS content from {gs_url}: {e}")
                return ""
        
        try:
            # Run synchronous GCS operations in executor with timeout
            # Use semaphore to limit concurrent GCS connections to avoid thread pool exhaustion
            async with self._semaphore:
                loop = asyncio.get_event_loop()
                content = await asyncio.wait_for(
                    loop.run_in_executor(None, _fetch_sync),
                    timeout=timeout
                )
                return content
        except asyncio.TimeoutError:
            # Timeout - return empty string
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Timeout fetching GCS content from {gs_url} (timeout: {timeout}s)")
            return ""
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Exception fetching GCS content from {gs_url}: {e}")
            return ""
    
    async def _fetch_http_content(self, url: str, timeout: float = 10.0) -> str:
        """
        Fetch content from HTTP/HTTPS URL with timeout
        
        Args:
            url: HTTP/HTTPS URL
            timeout: Timeout in seconds (default: 10.0)
            
        Returns:
            Content as string, or empty string if fetch fails or times out
        """
        import logging
        logger = logging.getLogger(__name__)
        
        if not url or not (url.startswith("http://") or url.startswith("https://")):
            return ""
        
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.text
        except Exception:
            return ""
    
    async def _fetch_url_content(self, url: str, timeout: float = 10.0) -> str:
        """
        Fetch content from URL (GCS or HTTP/HTTPS)
        Tries GCS first if it looks like a GCS URL, otherwise uses HTTP
        
        Args:
            url: URL (gs://, https://storage.googleapis.com/, or regular https://)
            timeout: Timeout in seconds (default: 10.0)
            
        Returns:
            Content as string, or empty string if fetch fails or times out
        """
        if not url:
            return ""
        
        # Try GCS first if it looks like a GCS URL
        if url.startswith("gs://") or "storage.googleapis.com" in url:
            return await self._fetch_gcs_content(url, timeout)
        
        # Otherwise use HTTP
        if url.startswith("http://") or url.startswith("https://"):
            return await self._fetch_http_content(url, timeout)
        
        return ""
    
    async def _enrich_episode_with_content(self, episode_dict: dict) -> dict:
        """
        Enrich episode dict with content from GCS if URLs are present
        """
        # Collect all URLs that need to be fetched
        fetch_tasks = []
        
        # Only fetch if content fields are missing or empty
        # Note: Empty string is falsy, so not '' is True
        if not episode_dict.get('summary_content') and episode_dict.get('summary_url'):
            summary_url = episode_dict.get('summary_url')
            if summary_url:
                fetch_tasks.append(('summary_content', self._fetch_gcs_content(summary_url)))
        
        if not episode_dict.get('transcript') and episode_dict.get('transcript_url'):
            transcript_url = episode_dict.get('transcript_url')
            if transcript_url:
                fetch_tasks.append(('transcript', self._fetch_gcs_content(transcript_url)))
        
        if not episode_dict.get('summary_image') and episode_dict.get('summary_image_url'):
            summary_image_url = episode_dict.get('summary_image_url')
            if summary_image_url:
                fetch_tasks.append(('summary_image', self._fetch_gcs_content(summary_image_url)))
        
        if not episode_dict.get('events_markdown_content') and episode_dict.get('events_markdown_url'):
            events_markdown_url = episode_dict.get('events_markdown_url')
            if events_markdown_url:
                fetch_tasks.append(('events_markdown_content', self._fetch_gcs_content(events_markdown_url)))
        
        if not episode_dict.get('sentences_markdown_content') and episode_dict.get('sentences_markdown_url'):
            sentences_markdown_url = episode_dict.get('sentences_markdown_url')
            if sentences_markdown_url:
                fetch_tasks.append(('sentences_markdown_content', self._fetch_gcs_content(sentences_markdown_url)))
        
        if not episode_dict.get('marp_markdown_content') and episode_dict.get('marp_markdown_url'):
            marp_markdown_url = episode_dict.get('marp_markdown_url')
            if marp_markdown_url:
                fetch_tasks.append(('marp_markdown_content', self._fetch_gcs_content(marp_markdown_url)))
        
        if not episode_dict.get('modified_summary_content') and episode_dict.get('modified_summary_url'):
            modified_summary_url = episode_dict.get('modified_summary_url')
            if modified_summary_url:
                fetch_tasks.append(('modified_summary_content', self._fetch_gcs_content(modified_summary_url)))
        
        # Ticker-specific content (only fetch if URL exists)
        if episode_dict.get('ticker_marp_markdown_url') and not episode_dict.get('ticker_marp_markdown_content'):
            ticker_marp_markdown_url = episode_dict.get('ticker_marp_markdown_url')
            if ticker_marp_markdown_url:
                fetch_tasks.append(('ticker_marp_markdown_content', self._fetch_url_content(ticker_marp_markdown_url)))
        
        if episode_dict.get('ticker_recommendations_public_url') and not episode_dict.get('ticker_recommendations_content'):
            ticker_recommendations_public_url = episode_dict.get('ticker_recommendations_public_url')
            if ticker_recommendations_public_url:
                fetch_tasks.append(('ticker_recommendations_content', self._fetch_url_content(ticker_recommendations_public_url)))
        
        # Fetch all URLs in parallel
        if fetch_tasks:
            try:
                # Wait for all fetches with a combined timeout (max 30 seconds total)
                results = await asyncio.wait_for(
                    asyncio.gather(*[task for _, task in fetch_tasks], return_exceptions=True),
                    timeout=30.0
                )
                
                # Update episode_dict with results
                for (field_name, _), result in zip(fetch_tasks, results):
                    if not isinstance(result, Exception):
                        episode_dict[field_name] = result
            except asyncio.TimeoutError:
                # Timeout - leave fields empty
                pass
            except Exception:
                # Other errors - leave fields empty
                pass
        
        return episode_dict
    
    def _datetime_to_timestamp_ms(self, dt) -> int:
        """Convert datetime to Unix timestamp in milliseconds"""
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        if isinstance(dt, datetime):
            return int(dt.timestamp() * 1000)
        return int(datetime.now().timestamp() * 1000)
    
    def _extract_tags_from_text(self, text: str) -> set:
        """Extract tags from markdown content (format: [Name](#tag:ID))"""
        if not text:
            return set()
        # Regex to find [Name](#tag:ID) and extract ID
        pattern = r"\[.*?\]\(#tag:(.*?)\)"
        try:
            return set(re.findall(pattern, text))
        except Exception:
            return set()

    async def _episode_dict_to_model(self, episode_dict: dict, enrich_content: bool = True) -> Episode:
        """Convert Firestore episode dict to Episode model, enriching with GCS content if needed"""
        import logging
        logger = logging.getLogger(__name__)
        
        # Enrich with GCS content if URLs are present and requested
        if enrich_content:
            logger.info(f"[DEBUG] Enriching episode {episode_dict.get('id')} with GCS content...")
            logger.info(f"[DEBUG] summary_url before: {episode_dict.get('summary_url')}")
            logger.info(f"[DEBUG] summary_content before: {repr(episode_dict.get('summary_content','')[:50]) if episode_dict.get('summary_content') else 'EMPTY'}")
            episode_dict = await self._enrich_episode_with_content(episode_dict)
            logger.info(f"[DEBUG] summary_content after: {repr(episode_dict.get('summary_content','')[:50]) if episode_dict.get('summary_content') else 'STILL EMPTY'}")
        else:
            logger.info(f"[DEBUG] Skipping enrichment for episode {episode_dict.get('id')} (enrich_content=False)")
        
        # Extract tags from content and merge with existing tags
        extracted_tags = set()
        extracted_tags.update(self._extract_tags_from_text(episode_dict.get('summary_content', '')))
        extracted_tags.update(self._extract_tags_from_text(episode_dict.get('events_markdown_content', '')))
        extracted_tags.update(self._extract_tags_from_text(episode_dict.get('sentences_markdown_content', '')))
        
        existing_tags = set(episode_dict.get('tags', []) or [])
        # Filter out empty tags and decode if necessary (though re.findall returns strings)
        all_tags = [t for t in existing_tags.union(extracted_tags) if t]
        
        created_time = episode_dict.get('created_time')
        if isinstance(created_time, str):
            created_time = datetime.fromisoformat(created_time.replace('Z', '+00:00'))
        elif not isinstance(created_time, datetime):
            created_time = datetime.now()
        
        return Episode(
            id=episode_dict.get('id') or episode_dict.get('episode_id', ''),
            podcast_name=episode_dict.get('podcast_name', ''),
            episode_title=episode_dict.get('episode_title'),
            episode_number=episode_dict.get('episode_number'),
            transcript=episode_dict.get('transcript', ''),
            summary_content=episode_dict.get('summary_content', ''),
            summary_image=episode_dict.get('summary_image', ''),
            related_tickers=episode_dict.get('related_tickers', []),
            tags=all_tags,
            created_time=self._datetime_to_timestamp_ms(created_time),
            number_click=episode_dict.get('number_click', 0),
            num_likes=episode_dict.get('num_likes', 0),
            key_insights=episode_dict.get('key_insights', []) or [],
            raw_mp3=episode_dict.get('raw_mp3'),
            # GCS URLs
            mp3_url=episode_dict.get('mp3_url'),
            transcript_url=episode_dict.get('transcript_url'),
            summary_url=episode_dict.get('summary_url'),
            summary_image_url=episode_dict.get('summary_image_url'),
            events_markdown_url=episode_dict.get('events_markdown_url'),
            sentences_markdown_url=episode_dict.get('sentences_markdown_url'),
            marp_markdown_url=episode_dict.get('marp_markdown_url'),
            # Public URLs
            mp3_public_url=episode_dict.get('mp3_public_url'),
            transcript_public_url=episode_dict.get('transcript_public_url'),
            summary_public_url=episode_dict.get('summary_public_url'),
            summary_image_public_url=episode_dict.get('summary_image_public_url'),
            events_markdown_public_url=episode_dict.get('events_markdown_public_url'),
            sentences_markdown_public_url=episode_dict.get('sentences_markdown_public_url'),
            marp_markdown_public_url=episode_dict.get('marp_markdown_public_url'),
            # Additional markdown content
            events_markdown_content=episode_dict.get('events_markdown_content'),
            sentences_markdown_content=episode_dict.get('sentences_markdown_content'),
            marp_markdown_content=episode_dict.get('marp_markdown_content'),
            # Spotify metadata
            spotify_embed_url=episode_dict.get('spotify_embed_url'),
            spotify_id=episode_dict.get('spotify_id'),
            spotify_url=episode_dict.get('spotify_url'),
            spotify_release_date=episode_dict.get('spotify_release_date'),
            spotify_description=episode_dict.get('spotify_description'),
            spotify_duration_ms=episode_dict.get('spotify_duration_ms'),
            spotify_images=episode_dict.get('spotify_images', []),
            # Modified summary fields
            modified_summary_url=episode_dict.get('modified_summary_url'),
            modified_summary_content=episode_dict.get('modified_summary_content'),
            modified_by=episode_dict.get('modified_by'),
            modified_at=episode_dict.get('modified_at'),
            # Ticker-specific fields
            ticker_marp_markdown_url=episode_dict.get('ticker_marp_markdown_url'),
            ticker_marp_markdown_public_url=episode_dict.get('ticker_marp_markdown_public_url'),
            ticker_marp_markdown_content=episode_dict.get('ticker_marp_markdown_content'),
            ticker_recommendations_public_url=episode_dict.get('ticker_recommendations_public_url'),
            ticker_recommendations_content=episode_dict.get('ticker_recommendations_content')
        )
    
    async def get_all_podcasts(
        self,
        sort_by: str = "name",
        order: str = "asc",
        limit: int = 50,
        offset: int = 0
    ) -> List[Podcast]:
        """
        Get all podcasts (aggregated from episodes) with caching
        
        Args:
            sort_by: Sort field (name, episode_count, created_at, updated_at)
            order: Sort order (asc, desc)
            limit: Maximum number of podcasts to return
            offset: Pagination offset
            
        Returns:
            List of Podcast objects
        """
        cache_key = f"podcast:list:{sort_by}:{order}"
        
        # Check cache first
        cached = await cache_get(cache_key)
        if cached:
            try:
                data = json.loads(cached)
                podcasts = [Podcast(**item) for item in data]
                # Apply pagination
                return podcasts[offset:offset + limit]
            except Exception:
                pass  # If deserialization fails, fetch fresh data
        
        # Cache miss - fetch from Firestore
        try:
            # Get all episodes in a separate thread to avoid blocking loop
            all_episodes = await asyncio.to_thread(self.firestore_service.get_all_documents, "episodes")
            
            # Aggregate by podcast_name
            podcast_dict = {}
            for episode_dict in all_episodes:
                podcast_name = episode_dict.get('podcast_name')
                if not podcast_name:
                    continue
                
                if podcast_name not in podcast_dict:
                    podcast_dict[podcast_name] = {
                        'episodes': [],
                        'created_at': None,
                        'updated_at': None
                    }
                
                created_time = episode_dict.get('created_time')
                if isinstance(created_time, str):
                    created_time = datetime.fromisoformat(created_time.replace('Z', '+00:00'))
                elif isinstance(created_time, datetime):
                    pass
                else:
                    created_time = datetime.now()
                
                timestamp_ms = self._datetime_to_timestamp_ms(created_time)
                
                if podcast_dict[podcast_name]['created_at'] is None or timestamp_ms < podcast_dict[podcast_name]['created_at']:
                    podcast_dict[podcast_name]['created_at'] = timestamp_ms
                
                if podcast_dict[podcast_name]['updated_at'] is None or timestamp_ms > podcast_dict[podcast_name]['updated_at']:
                    podcast_dict[podcast_name]['updated_at'] = timestamp_ms
                    # Store latest episode to get its image later
                    podcast_dict[podcast_name]['latest_episode'] = episode_dict
                
                podcast_dict[podcast_name]['episodes'].append(episode_dict)
            
            # Convert to Podcast models
            podcasts = []
            for podcast_name, data in podcast_dict.items():
                # Extract image from latest episode (spotify_images is a list, take first)
                image_url = None
                latest_ep = data.get('latest_episode', {})
                spotify_images = latest_ep.get('spotify_images', [])
                if spotify_images and isinstance(spotify_images, list) and len(spotify_images) > 0:
                    image_url = spotify_images[0]
                
                podcasts.append(Podcast(
                    id=podcast_name,
                    name=podcast_name,
                    episode_count=len(data['episodes']),
                    created_at=data['created_at'],
                    updated_at=data['updated_at'],
                    image_url=image_url
                ))
            
            # Sort podcasts
            reverse = (order.lower() == "desc")
            if sort_by == "name":
                podcasts.sort(key=lambda x: x.name.lower(), reverse=reverse)
            elif sort_by == "episode_count":
                podcasts.sort(key=lambda x: x.episode_count, reverse=reverse)
            elif sort_by == "created_at":
                podcasts.sort(key=lambda x: x.created_at or 0, reverse=reverse)
            elif sort_by == "updated_at":
                podcasts.sort(key=lambda x: x.updated_at or 0, reverse=reverse)
            else:
                # Default to name
                podcasts.sort(key=lambda x: x.name.lower(), reverse=reverse)
            
            # Store in cache (before pagination)
            try:
                await cache_set(
                    cache_key,
                    json.dumps([p.dict() for p in podcasts], default=str),
                    CACHE_TTL["podcast_list"]
                )
            except Exception:
                pass  # Cache failure shouldn't break the request
            
            # Apply pagination
            return podcasts[offset:offset + limit]
            
        except Exception as e:
            raise Exception(f"Failed to get podcasts: {e}") from e
    
    async def get_podcast_by_name(self, podcast_name: str) -> Optional[Podcast]:
        """
        Get podcast by name with caching
        
        Args:
            podcast_name: Podcast name
            
        Returns:
            Podcast object or None if not found
        """
        cache_key = f"podcast:{podcast_name}"
        
        # Check cache first
        cached = await cache_get(cache_key)
        if cached:
            try:
                data = json.loads(cached)
                return Podcast(**data)
            except Exception:
                pass
        
        # Cache miss - fetch from Firestore
        try:
            # Get all episodes for this podcast
            episodes = self.firestore_service.query_collection(
                collection="episodes",
                filters=[("podcast_name", "==", podcast_name)]
            )
            
            if not episodes:
                return None
            
            # Aggregate podcast metadata
            created_at = None
            updated_at = None
            
            for episode_dict in episodes:
                created_time = episode_dict.get('created_time')
                if isinstance(created_time, str):
                    created_time = datetime.fromisoformat(created_time.replace('Z', '+00:00'))
                elif isinstance(created_time, datetime):
                    pass
                else:
                    created_time = datetime.now()
                
                timestamp_ms = self._datetime_to_timestamp_ms(created_time)
                
                if created_at is None or timestamp_ms < created_at:
                    created_at = timestamp_ms
                
                if updated_at is None or timestamp_ms > updated_at:
                    updated_at = timestamp_ms
                    # Get image from latest episode
                    spotify_images = episode_dict.get('spotify_images', [])
                    if spotify_images and isinstance(spotify_images, list) and len(spotify_images) > 0:
                        latest_image_url = spotify_images[0]
            
            podcast = Podcast(
                id=podcast_name,
                name=podcast_name,
                episode_count=len(episodes),
                created_at=created_at,
                updated_at=updated_at,
                image_url=latest_image_url
            )
            
            # Store in cache
            try:
                await cache_set(
                    cache_key,
                    json.dumps(podcast.dict(), default=str),
                    CACHE_TTL["podcast_item"]
                )
            except Exception:
                pass
            
            return podcast
            
        except Exception as e:
            raise Exception(f"Failed to get podcast: {e}") from e
    
    async def get_episodes_by_podcast(
        self,
        podcast_name: str,
        sort_by: str = "created_time",
        order: str = "desc",
        limit: int = 50,
        offset: int = 0,
        enrich_content: bool = False
    ) -> List[Episode]:
        """
        Get episodes for a podcast with caching
        
        Args:
        :
            podcast_name: Podcast name
            sort_by: Sort field (created_time, episode_number, episode_title)
            order: Sort order (asc, desc)
            limit: Maximum number of episodes        Returns:
            List of Episode objects
        """
        cache_key = f"podcast:{podcast_name}:episodes:{sort_by}:{order}:{enrich_content}"
        
        # Check cache first
        cached = await cache_get(cache_key)
        if cached:
            try:
                data = json.loads(cached)
                episodes = [Episode(**item) for item in data]
                # Apply pagination
                return episodes[offset:offset + limit]
            except Exception:
                pass
        
        # Cache miss - fetch from Firestore
        try:
            # Fetch episodes without order_by to avoid Firestore composite index requirement
            # We'll sort in memory instead
            episodes_dict = self.firestore_service.query_collection(
                collection="episodes",
                filters=[("podcast_name", "==", podcast_name)],
                order_by=None,  # Don't use Firestore ordering to avoid index requirement
                direction=None,
                limit=None  # Get all, then sort and paginate
            )
            
            # Convert to Episode models (with GCS content enrichment)
            episodes = []
            # Fetch in parallel to improve performance
            tasks = [self._episode_dict_to_model(ep_dict, enrich_content=enrich_content) for ep_dict in episodes_dict]
            episodes = await asyncio.gather(*tasks)
            
            # Sort in memory
            reverse = (order.lower() == "desc")
            if sort_by == "created_time":
                episodes.sort(key=lambda x: x.created_time or 0, reverse=reverse)
            elif sort_by == "episode_number":
                episodes.sort(key=lambda x: x.episode_number if x.episode_number is not None else 0, reverse=reverse)
            elif sort_by == "episode_title":
                episodes.sort(key=lambda x: (x.episode_title or "").lower(), reverse=reverse)
            else:
                # Default to created_time
                episodes.sort(key=lambda x: x.created_time or 0, reverse=reverse)
            
            # Store in cache (before pagination)
            try:
                await cache_set(
                    cache_key,
                    json.dumps([e.dict() for e in episodes], default=str),
                    CACHE_TTL["podcast_episodes"]
                )
            except Exception:
                pass
            
            # Apply pagination
            return episodes[offset:offset + limit]
            
        except Exception as e:
            raise Exception(f"Failed to get episodes: {e}") from e
    
    async def get_episode_by_id(self, podcast_name: str, episode_id: str) -> Optional[Episode]:
        """
        Get episode by ID with caching
        
        Args:
            podcast_name: Podcast name
            episode_id: Episode ID
            
        Returns:
            Episode object or None if not found
        """
        cache_key = f"podcast:{podcast_name}:episode:{episode_id}"
        
        # Check cache first
        cached = await cache_get(cache_key)
        if cached:
            try:
                data = json.loads(cached)
                return Episode(**data)
            except Exception:
                pass
        
        # Cache miss - fetch from Firestore
        try:
            episode_dict = self.firestore_service.get_document("episodes", episode_id)
            
            if not episode_dict:
                return None
            
            # Verify it belongs to the correct podcast
            if episode_dict.get('podcast_name') != podcast_name:
                return None
            
            episode = await self._episode_dict_to_model(episode_dict)
            
            # Store in cache
            try:
                await cache_set(
                    cache_key,
                    json.dumps(episode.dict(), default=str),
                    CACHE_TTL["podcast_episode"]
                )
            except Exception:
                pass
            
            return episode
            
        except Exception as e:
            raise Exception(f"Failed to get episode: {e}") from e
    
    async def get_recent_episodes(
        self,
        limit: int = 20,
        offset: int = 0,
        podcast_name: Optional[str] = None,
        enrich_content: bool = False
    ) -> List[Episode]:
        """
        Get recent episodes across all podcasts, sorted by created_time descending
        
        Args:
            limit: Maximum number of episodes to return
            offset: Pagination offset
            podcast_name: Optional filter by podcast name
            
        Returns:
            List of Episode objects sorted by created_time (newest first)
        """
        cache_key = f"episodes:recent:{podcast_name or 'all'}:{limit}:{offset}:{enrich_content}"
        
        # Check cache first
        cached = await cache_get(cache_key)
        if cached:
            try:
                data = json.loads(cached)
                episodes = [Episode(**item) for item in data]
                return episodes
            except Exception:
                pass
        
        # Cache miss - fetch from Firestore
        try:
            # Get episodes
            filters = []
            if podcast_name:
                filters = [("podcast_name", "==", podcast_name)]
            
            # Optimization: Use native Firestore sort/limit when fetching all recent episodes
            # This avoids fetching the entire collection (O(N)) when we only need the latest N items.
            # Note: When filtering by podcast_name, we stick to in-memory sort unless we're sure
            # a composite index (podcast_name + created_time) exists.
            order_by = None
            direction = None
            query_limit = None
            
            if not podcast_name:
                order_by = "created_time"
                direction = "DESCENDING"
                query_limit = limit

            # Run query in thread
            episodes_dict = await asyncio.to_thread(
                self.firestore_service.query_collection,
                collection="episodes",
                filters=filters if filters else None,
                order_by=order_by,
                direction=direction,
                limit=query_limit
            )
            
            # Convert to Episode models (with GCS content enrichment)
            episodes = []
            # Fetch in parallel
            tasks = [self._episode_dict_to_model(ep_dict, enrich_content=enrich_content) for ep_dict in episodes_dict]
            episodes = await asyncio.gather(*tasks)
            
            # Sort by created_time descending
            episodes.sort(key=lambda x: x.created_time or 0, reverse=True)
            
            # Apply pagination
            paginated_episodes = episodes[offset:offset + limit]
            
            # Store in cache
            try:
                await cache_set(
                    cache_key,
                    json.dumps([e.dict() for e in paginated_episodes], default=str),
                    CACHE_TTL["podcast_episodes"]
                )
            except Exception:
                pass
            
            return paginated_episodes
            
        except Exception as e:
            raise Exception(f"Failed to get recent episodes: {e}") from e
    
    async def get_episodes_by_ticker(
        self,
        ticker: str,
        limit: int = 50,
        offset: int = 0,
        enrich_content: bool = False
    ) -> List[Episode]:
        """
        Get episodes that mention a specific ticker
        
        Args:
            ticker: Stock ticker symbol (case-insensitive)
            limit: Maximum number of episodes to return
            offset: Pagination offset
            
        Returns:
            List of Episode objects sorted by created_time (newest first)
        """
        ticker_upper = ticker.upper()
        cache_key = f"episodes:ticker:{ticker_upper}:{limit}:{offset}:{enrich_content}"
        
        # Check cache first
        cached = await cache_get(cache_key)
        if cached:
            try:
                data = json.loads(cached)
                episodes = [Episode(**item) for item in data]
                return episodes
            except Exception:
                pass
        
        # Cache miss - fetch from Firestore using subcollection
        try:
            ticker_upper = ticker.upper()
            
            # Get episode references from subcollection
            episode_refs = self.firestore_service.get_subcollection_documents(
                collection="tickers",
                parent_doc_id=ticker_upper,
                subcollection="episodes",
                order_by="created_time",
                direction="DESCENDING",
                limit=limit + offset  # Get enough for pagination
            )
            
            # Apply offset
            episode_refs = episode_refs[offset:offset + limit]
            
            # Get full episode data from episodes collection
            episodes_dicts = []
            for ep_ref in episode_refs:
                episode_id = ep_ref.get('episode_id')
                if episode_id:
                    # Get full episode document
                    episode_dict = self.firestore_service.get_document("episodes", episode_id)
                    if episode_dict:
                        episodes_dicts.append(episode_dict)
            
            # Convert to Episode models (with GCS content enrichment) in parallel
            tasks = [self._episode_dict_to_model(ep_dict, enrich_content=enrich_content) for ep_dict in episodes_dicts]
            episodes = await asyncio.gather(*tasks)
            
            # Store in cache
            try:
                await cache_set(
                    cache_key,
                    json.dumps([e.dict() for e in episodes], default=str),
                    CACHE_TTL["podcast_episodes"]
                )
            except Exception:
                pass
            
            return episodes
            
        except Exception as e:
            raise Exception(f"Failed to get episodes by ticker: {e}") from e
    
    async def get_all_tags(self) -> List[dict]:
        """
        Get all tags with episode counts from Firestore.
        
        Uses subcollection structure: tags/{tag}/episodes/{episode_id}
        
        Since parent documents might be empty containers, we extract unique tags
        from episodes collection and then check their subcollections.
        
        Returns:
            List of tag dictionaries with id, name, and episode_count
        """
        try:
            # Get all episodes to extract unique tags
            # This is more reliable than relying on parent documents which might be empty
            # Run in thread
            episodes_dict = await asyncio.to_thread(
                self.firestore_service.query_collection,
                collection="episodes",
                filters=None,
                order_by=None,
                direction=None,
                limit=None
            )
            
            # Extract unique tags from episodes
            unique_tags = set()
            for ep_dict in episodes_dict:
                ep_tags = ep_dict.get('tags', [])
                if ep_tags:
                    # Normalize to lowercase (as stored in subcollections)
                    unique_tags.update([tag.lower() for tag in ep_tags])
            
            # Now check each tag's subcollection for episode count
            tags = []
            for tag_id in unique_tags:
                try:
                    # Count episodes in subcollection (in thread)
                    episode_count = await asyncio.to_thread(
                        self.firestore_service.count_subcollection_documents,
                        collection="tags",
                        parent_doc_id=tag_id,
                        subcollection="episodes"
                    )
                    
                    if episode_count > 0:  # Only include tags that have episodes
                        tags.append({
                            "id": tag_id,
                            "name": tag_id,  # Tag ID is the tag name (normalized to lowercase)
                            "episode_count": episode_count
                        })
                except Exception:
                    # Skip tags that don't have subcollections or have errors
                    continue
            
            # Sort by episode count descending
            tags.sort(key=lambda x: x["episode_count"], reverse=True)
            
            return tags
        except Exception as e:
            raise Exception(f"Failed to get all tags: {e}") from e
    
    async def get_episodes_by_tag(
        self,
        tag: str,
        limit: int = 50,
        offset: int = 0,
        enrich_content: bool = False
    ) -> List[Episode]:
        """
        Get episodes for a specific tag from Firestore.
        
        Uses subcollection structure: tags/{tag}/episodes/{episode_id}
        
        Args:
            tag: Tag name (normalized to lowercase)
            limit: Maximum number of episodes to return
            offset: Pagination offset
            
        Returns:
            List of Episode objects
        """
        try:
            # Normalize tag to lowercase
            tag_lower = tag.lower()
            
            # Get episode references from subcollection
            episode_refs = self.firestore_service.get_subcollection_documents(
                collection="tags",
                parent_doc_id=tag_lower,
                subcollection="episodes",
                order_by="created_time",
                direction="DESCENDING",
                limit=limit + offset  # Get enough for pagination
            )
            
            # Apply offset
            episode_refs = episode_refs[offset:offset + limit]
            
            # Get full episode data from episodes collection
            episodes_dicts = []
            for ep_ref in episode_refs:
                episode_id = ep_ref.get('episode_id')
                if episode_id:
                    # Get full episode document
                    episode_dict = self.firestore_service.get_document("episodes", episode_id)
                    if episode_dict:
                        episodes_dicts.append(episode_dict)
            
            # Convert to Episode models (with GCS content enrichment) in parallel
            tasks = [self._episode_dict_to_model(ep_dict, enrich_content=enrich_content) for ep_dict in episodes_dicts]
            episodes = await asyncio.gather(*tasks)
            
            return episodes
        except Exception as e:
            raise Exception(f"Failed to get episodes by tag: {e}") from e

    async def search_podcasts(self, query: str, limit: int = 5) -> List[SearchResultItem]:
        """Search podcasts by name with strict timeout"""
        try:
            # Wrap the actual search logic in a timeout
            async def _search():
                # Get all podcasts (cached)
                all_podcasts = await self.get_all_podcasts(limit=1000)
                
                query_lower = query.lower()
                results = []
                
                for podcast in all_podcasts:
                    if query_lower in podcast.name.lower():
                        results.append(SearchResultItem(
                            id=f"podcast-{podcast.id}",
                            type="podcast",
                            title=podcast.name,
                            subtitle=f"{podcast.episode_count} episodes",
                            icon_url=podcast.image_url,
                            link=f"/podcaster/{podcast.name}"
                        ))
                        if len(results) >= limit:
                            break
                return results

            # Strict 2 second timeout for podcast search
            return await asyncio.wait_for(_search(), timeout=2.0)
        except (asyncio.TimeoutError, Exception) as e:
            # Log specific error but return empty list to not block other results
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Podcast search timed out or failed: {e}")
            return []

    async def search_episodes(self, query: str, limit: int = 5) -> List[SearchResultItem]:
        """Search episodes by title or podcast name with strict timeout"""
        try:
            async def _search():
                # We fetch recent episodes (limit 200 for now as a reasonable search space for "recent")
                all_episodes = await self.get_recent_episodes(limit=200)
                
                query_lower = query.lower()
                results = []
                
                for episode in all_episodes:
                    title = episode.episode_title or ""
                    podcast = episode.podcast_name or ""
                    
                    if query_lower in title.lower() or query_lower in podcast.lower():
                        # Use Spotify image or summary image as icon
                        icon_url = None
                        if episode.spotify_images and isinstance(episode.spotify_images, list) and len(episode.spotify_images) > 0:
                            icon_url = episode.spotify_images[0]
                        elif episode.summary_image_url:
                            icon_url = episode.summary_image_url
                        
                        results.append(SearchResultItem(
                            id=f"episode-{episode.id}",
                            type="episode",
                            title=title or f"Episode {episode.episode_number}",
                            subtitle=podcast,
                            icon_url=icon_url,
                            link=f"/podcaster/{podcast}" # Frontend handles deep linking via query params if supported, else just podcast page
                        ))
                        if len(results) >= limit:
                            break
                return results

            return await asyncio.wait_for(_search(), timeout=2.0)
        except (asyncio.TimeoutError, Exception) as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Episode search timed out or failed: {e}")
            return []

    async def search_tags(self, query: str, limit: int = 5) -> List[SearchResultItem]:
        """Search tags with strict timeout"""
        try:
            async def _search():
                try:
                    all_tags = await self.get_all_tags()
                except Exception:
                    all_tags = []
                
                query_lower = query.lower()
                results = []
                
                for tag_data in all_tags:
                    tag_name = tag_data.get("name", "")
                    if query_lower in tag_name.lower():
                        results.append(SearchResultItem(
                            id=f"tag-{tag_data.get('id')}",
                            type="tag",
                            title=tag_name,
                            subtitle=f"{tag_data.get('episode_count')} episodes",
                            link=f"/tag/{tag_name}"
                        ))
                        if len(results) >= limit:
                            break
                return results

            return await asyncio.wait_for(_search(), timeout=2.0)
        except (asyncio.TimeoutError, Exception) as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Tag search timed out or failed: {e}")
            return []
    
    async def save_modified_summary(
        self,
        podcast_name: str,
        episode_id: str,
        content: str,
        modified_by: Optional[str] = None
    ) -> Episode:
        """
        Save modified summary to GCS and update Firestore
        
        Args:
            podcast_name: Podcast name
            episode_id: Episode ID
            content: Modified summary markdown content
            modified_by: Optional user identifier (email or ID)
            
        Returns:
            Updated Episode object
            
        Raises:
            HTTPException: If episode not found or save fails
        """
        from fastapi import HTTPException
        
        # Get GCS client
        client = self._get_gcs_client()
        if not client:
            raise HTTPException(status_code=500, detail="GCS client not available")
        
        # Get bucket name from environment (assume same bucket as other episode content)
        # We'll need to determine the bucket from existing episode data
        episode_dict = self.firestore_service.get_document("episodes", episode_id)
        if not episode_dict:
            raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")
        
        # Verify podcast name matches
        if episode_dict.get('podcast_name') != podcast_name:
            raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found for podcast {podcast_name}")
        
        # Determine bucket name from existing GCS URLs (e.g., summary_url)
        # Parse bucket from gs://bucket/path format
        bucket_name = None
        for url_field in ['summary_url', 'transcript_url', 'mp3_url']:
            if episode_dict.get(url_field):
                parsed = self._parse_gs_url(episode_dict[url_field])
                if parsed:
                    bucket_name = parsed[0]
                    break
        
        if not bucket_name:
            # Fallback: try to get from environment or use a default
            bucket_name = os.getenv("GCS_BUCKET", "tinboker-podcast-data")
        
        # Upload to GCS at {podcast_name}/modified_summary/{episode_id}_summary.md
        blob_path = f"{podcast_name}/modified_summary/{episode_id}_summary.md"
        modified_summary_url = f"gs://{bucket_name}/{blob_path}"
        
        try:
            # Upload to GCS
            def _upload_sync():
                bucket = client.bucket(bucket_name)
                blob = bucket.blob(blob_path)
                blob.upload_from_string(content, content_type='text/markdown')
            
            # Run upload in executor
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _upload_sync)
            
            # Update Firestore
            modified_at = int(datetime.now().timestamp() * 1000)
            update_data = {
                'modified_summary_url': modified_summary_url,
                'modified_at': modified_at
            }
            if modified_by:
                update_data['modified_by'] = modified_by
            
            # Update in thread (use set_document with merge=True to update fields)
            await asyncio.to_thread(
                self.firestore_service.set_document,
                "episodes",
                episode_id,
                update_data,
                True  # merge=True to update only specified fields
            )
            
            # Invalidate caches
            await cache_delete(f"podcast:{podcast_name}:episode:{episode_id}")
            await cache_delete_pattern(f"podcast:{podcast_name}:episodes:*")
            await cache_delete_pattern("episodes:recent:*")
            
            # Return updated episode
            return await self.get_episode_by_id(podcast_name, episode_id)
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to save modified summary: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save modified summary: {str(e)}")
    
    async def delete_modified_summary(
        self,
        podcast_name: str,
        episode_id: str
    ) -> bool:
        """
        Delete modified summary from GCS and Firestore
        
        Args:
            podcast_name: Podcast name
            episode_id: Episode ID
            
        Returns:
            True if successful
            
        Raises:
            HTTPException: If episode not found or delete fails
        """
        from fastapi import HTTPException
        
        # Get episode to verify it exists and get modified_summary_url
        episode_dict = self.firestore_service.get_document("episodes", episode_id)
        if not episode_dict:
            raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found")
        
        # Verify podcast name matches
        if episode_dict.get('podcast_name') != podcast_name:
            raise HTTPException(status_code=404, detail=f"Episode {episode_id} not found for podcast {podcast_name}")
        
        modified_summary_url = episode_dict.get('modified_summary_url')
        if not modified_summary_url:
            # Nothing to delete
            return True
        
        # Get GCS client
        client = self._get_gcs_client()
        if not client:
            raise HTTPException(status_code=500, detail="GCS client not available")
        
        try:
            # Delete from GCS
            parsed = self._parse_gs_url(modified_summary_url)
            if parsed:
                bucket_name, blob_path = parsed
                
                def _delete_sync():
                    bucket = client.bucket(bucket_name)
                    blob = bucket.blob(blob_path)
                    if blob.exists():
                        blob.delete()
                
                # Run delete in executor
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, _delete_sync)
            
            # Remove fields from Firestore using Firestore's DELETE_FIELD
            from google.cloud.firestore import DELETE_FIELD
            
            update_data = {
                'modified_summary_url': DELETE_FIELD,
                'modified_summary_content': DELETE_FIELD,
                'modified_by': DELETE_FIELD,
                'modified_at': DELETE_FIELD
            }
            
            # Update in thread (use set_document with merge=True)
            await asyncio.to_thread(
                self.firestore_service.set_document,
                "episodes",
                episode_id,
                update_data,
                True  # merge=True to update only specified fields
            )
            
            # Invalidate caches
            await cache_delete(f"podcast:{podcast_name}:episode:{episode_id}")
            await cache_delete_pattern(f"podcast:{podcast_name}:episodes:*")
            await cache_delete_pattern("episodes:recent:*")
            
            return True
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to delete modified summary: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to delete modified summary: {str(e)}")


async def poll_regeneration_status(podcast_name: str, episode_id: str):
    """
    Background task to poll external status API and clear cache when done.
    
    - Polls every 5 seconds
    - Max timeout: 10 minutes
    - Clears cache on completion
    
    Args:
        podcast_name: Podcast name
        episode_id: Episode ID
    """
    logger = logging.getLogger(__name__)
    api_url = settings.netcup_api_url
    api_key = settings.podcast_api_key
    
    if not api_key:
        logger.error(f"PODCAST_API_KEY not configured, cannot poll status for {episode_id}")
        return
    
    max_attempts = 120  # 10 minutes at 5-second intervals
    
    async with httpx.AsyncClient() as client:
        for attempt in range(max_attempts):
            try:
                response = await client.get(
                    f"{api_url}/api/episodes/status/{episode_id}",
                    headers={"X-API-Key": api_key},
                    timeout=10.0
                )
                response.raise_for_status()
                data = response.json()
                status = data.get("status")
                
                if status == "completed":
                    # Clear cache
                    await cache_delete(f"podcast:{podcast_name}:episode:{episode_id}")
                    await cache_delete_pattern(f"podcast:{podcast_name}:episodes:*")
                    await cache_delete_pattern("episodes:recent:*")
                    logger.info(f"Regeneration completed for {podcast_name}/{episode_id}, cache cleared")
                    return
                    
                elif status == "failed":
                    error_msg = data.get("error", "Unknown error")
                    logger.error(f"Regeneration failed for {podcast_name}/{episode_id}: {error_msg}")
                    return
                    
                # status == "running", continue polling
                if attempt % 12 == 0:  # Log every minute (12 * 5 seconds)
                    logger.info(f"Regeneration still running for {podcast_name}/{episode_id} (attempt {attempt + 1}/{max_attempts})")
                await asyncio.sleep(5)
                
            except httpx.HTTPStatusError as e:
                logger.warning(f"HTTP error polling status for {episode_id}: {e.response.status_code} - {e.response.text}")
                await asyncio.sleep(5)
            except httpx.RequestError as e:
                logger.warning(f"Request error polling status for {episode_id}: {e}")
                await asyncio.sleep(5)
            except Exception as e:
                logger.warning(f"Unexpected error polling status for {episode_id}: {e}")
                await asyncio.sleep(5)
    
    logger.warning(f"Regeneration polling timed out for {podcast_name}/{episode_id} after {max_attempts} attempts")