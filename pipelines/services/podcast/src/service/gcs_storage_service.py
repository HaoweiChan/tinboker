#!/usr/bin/env python3
"""
Google Cloud Storage Service for Podcast Files

This module provides a centralized service for uploading podcast episode files
to Google Cloud Storage and generating URLs for Firestore storage.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from src.secrets_bootstrap import bootstrap

# Load secrets from GSM (idempotent — safe if already bootstrapped at entry point).
bootstrap()

try:
    from google.cloud import storage
    from google.oauth2 import service_account
except ImportError:
    raise ImportError(
        "google-cloud-storage is required for GCS upload functionality. "
        "Install it with: pip install google-cloud-storage"
    )


class GCSStorageService:
    """
    Service for uploading podcast episode files to Google Cloud Storage
    and generating URLs for Firestore storage.
    """
    
    def __init__(self):
        """
        Initialize GCS Storage Service.
        
        Raises:
            ValueError: If required environment variables are missing
            Exception: If GCS client initialization fails
        """
        self.bucket_name = os.getenv("GCS_BUCKET_NAME")
        self.base_path = os.getenv("GCS_BASE_PATH", "").strip('/')
        
        if not self.bucket_name:
            raise ValueError(
                "GCS_BUCKET_NAME is required. Set it in your .env file."
            )
        
        self.client = self._initialize_gcs_client()
        self.bucket = self.client.bucket(self.bucket_name)
    
    def _initialize_gcs_client(self) -> storage.Client:
        """
        Initialize and return a Google Cloud Storage client.
        
        Returns:
            storage.Client: GCS client instance
            
        Raises:
            ValueError: If required environment variables are missing
            Exception: If client initialization fails
        """
        project_id = os.getenv("GCS_PROJECT_ID")
        
        # Priority order: JSON credentials first, then path-based credentials
        # Check GCS-specific credentials first, then fall back to GCP credentials
        credentials_json = os.getenv("GCS_CREDENTIALS_JSON") or os.getenv("GCP_CREDENTIALS_JSON")
        credentials_path = None
        
        # Only check for path-based credentials if JSON is not available
        if not credentials_json:
            credentials_path = os.getenv("GCS_CREDENTIALS_PATH") or os.getenv("GCP_CREDENTIALS_PATH")
        
        if not project_id:
            # Try to get project_id from credentials if not explicitly set
            if credentials_json:
                try:
                    if isinstance(credentials_json, str):
                        creds_dict = json.loads(credentials_json)
                    else:
                        creds_dict = credentials_json
                    project_id = creds_dict.get('project_id')
                except (json.JSONDecodeError, (AttributeError, TypeError)):
                    pass
            elif credentials_path:
                try:
                    cred_path = Path(credentials_path).expanduser().resolve()
                    if cred_path.exists():
                        with open(cred_path, 'r') as f:
                            creds_dict = json.load(f)
                            project_id = creds_dict.get('project_id')
                except (json.JSONDecodeError, (FileNotFoundError, IOError)):
                    pass
        
        if not project_id:
            raise ValueError(
                "GCS_PROJECT_ID is required. Set it in your .env file, or it will be "
                "inferred from credentials if GCP_CREDENTIALS_PATH or GCP_CREDENTIALS_JSON is set."
            )
        
        # Initialize credentials
        # Priority: JSON credentials first, then path-based credentials
        credentials = None
        
        if credentials_json:
            # Use credentials from JSON string (preferred method)
            try:
                if isinstance(credentials_json, str):
                    creds_dict = json.loads(credentials_json)
                else:
                    creds_dict = credentials_json
                credentials = service_account.Credentials.from_service_account_info(
                    creds_dict
                )
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"Invalid JSON in credentials: {e}"
                ) from e
        elif credentials_path:
            # Use credentials from file path (fallback)
            cred_path = Path(credentials_path).expanduser().resolve()
            if not cred_path.exists():
                raise FileNotFoundError(
                    f"Credentials file not found: {cred_path}"
                )
            credentials = service_account.Credentials.from_service_account_file(
                str(cred_path)
            )
        else:
            raise ValueError(
                "Either GCP_CREDENTIALS_JSON, GCS_CREDENTIALS_JSON, GCP_CREDENTIALS_PATH, "
                "or GCS_CREDENTIALS_PATH is required. Set one of them in your .env file. "
                "JSON credentials are preferred over path-based credentials."
            )
        
        # Create and return client
        try:
            client = storage.Client(credentials=credentials, project=project_id)
            return client
        except Exception as e:
            raise Exception(f"Failed to initialize GCS client: {e}") from e
    
    def _get_podcast_hash(self, podcast_name: str) -> str:
        """
        Generate a hash of the podcast name for URL-safe directory naming.
        
        Args:
            podcast_name: Name of the podcast
            
        Returns:
            Hash string (12 characters)
        """
        return hashlib.sha256(podcast_name.encode('utf-8')).hexdigest()[:12]
    
    def _get_file_path(self, file_type: str, podcast_name: str, episode_id: str, extension: str) -> str:
        """
        Generate GCS blob path for a file.
        
        Path structure: {base_path}/{type}/{podcast_hash}/{episode_id}.{ext}
        
        Args:
            file_type: Type of file ('mp3', 'transcripts', 'summaries', 'images')
            podcast_name: Name of the podcast
            episode_id: Episode ID (matches Firestore document ID)
            extension: File extension (e.g., 'mp3', 'txt', 'md', 'svg')
            
        Returns:
            GCS blob path (relative to bucket root)
        """
        podcast_hash = self._get_podcast_hash(podcast_name)
        
        # Build path components
        parts = []
        if self.base_path:
            parts.append(self.base_path)
        parts.extend([file_type, podcast_hash, f"{episode_id}.{extension}"])
        
        # Join with forward slashes (GCS uses forward slashes)
        blob_path = '/'.join(parts)
        return blob_path
    
    def upload_file(
        self,
        local_file_path: Path,
        file_type: str,
        podcast_name: str,
        episode_id: str,
        extension: Optional[str] = None,
        skip_existing: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """
        Upload a single file to Google Cloud Storage.
        
        Args:
            local_file_path: Path to the local file
            file_type: Type of file ('mp3', 'transcripts', 'summaries', 'images')
            podcast_name: Name of the podcast
            episode_id: Episode ID (matches Firestore document ID)
            extension: File extension (if None, inferred from local_file_path)
            skip_existing: If True, skip upload if file already exists with same size
            
        Returns:
            Tuple of (success: bool, gcs_url: Optional[str])
            Returns (True, gcs_url) on success, (False, None) on failure
        """
        try:
            # Infer extension from file path if not provided
            if extension is None:
                extension = local_file_path.suffix.lstrip('.')
            
            # Generate GCS blob path
            blob_path = self._get_file_path(file_type, podcast_name, episode_id, extension)
            
            # Get blob reference
            blob = self.bucket.blob(blob_path)
            
            # Check if file already exists
            if skip_existing and blob.exists():
                # Reload blob to get metadata (size) if not already loaded
                if blob.size is None:
                    blob.reload()
                
                # Get local and remote file sizes
                local_size = local_file_path.stat().st_size
                remote_size = blob.size
                
                # If sizes match, skip upload
                if remote_size is not None and local_size == remote_size:
                    gcs_url = self.generate_gcs_url(blob_path)
                    return (True, gcs_url)
                # If sizes don't match, upload anyway (file might be corrupted or updated)
            
            # Upload file
            blob.upload_from_filename(str(local_file_path))
            
            # Generate and return GCS URL
            gcs_url = self.generate_gcs_url(blob_path)
            return (True, gcs_url)
            
        except Exception as e:
            print(f"  ✗ Error uploading {local_file_path.name} to GCS: {e}")
            return (False, None)
    
    def upload_file_from_string(
        self,
        content: str,
        file_type: str,
        podcast_name: str,
        episode_id: str,
        extension: str,
        skip_existing: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """
        Upload file content from a string to Google Cloud Storage.
        
        Args:
            content: File content as string
            file_type: Type of file ('mp3', 'transcripts', 'summaries', 'images')
            podcast_name: Name of the podcast
            episode_id: Episode ID (matches Firestore document ID)
            extension: File extension (e.g., 'txt', 'md', 'svg')
            skip_existing: If True, skip upload if file already exists
            
        Returns:
            Tuple of (success: bool, gcs_url: Optional[str])
        """
        try:
            # Generate GCS blob path
            blob_path = self._get_file_path(file_type, podcast_name, episode_id, extension)
            
            # Get blob reference
            blob = self.bucket.blob(blob_path)
            
            # Check if file already exists
            if skip_existing and blob.exists():
                gcs_url = self.generate_gcs_url(blob_path)
                return (True, gcs_url)
            
            # Upload content
            blob.upload_from_string(content.encode('utf-8'), content_type=self._get_content_type(extension))
            
            # Generate and return GCS URL
            gcs_url = self.generate_gcs_url(blob_path)
            return (True, gcs_url)
            
        except Exception as e:
            print(f"  ✗ Error uploading {file_type} content to GCS: {e}")
            return (False, None)
    
    def upload_file_from_base64(
        self,
        base64_content: str,
        file_type: str,
        podcast_name: str,
        episode_id: str,
        extension: str,
        skip_existing: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """
        Upload file content from a base64-encoded string to Google Cloud Storage.
        
        Args:
            base64_content: Base64-encoded file content as string
            file_type: Type of file ('pptx', 'presentations', etc.)
            podcast_name: Name of the podcast
            episode_id: Episode ID (matches Firestore document ID)
            extension: File extension (e.g., 'pptx')
            skip_existing: If True, skip upload if file already exists
            
        Returns:
            Tuple of (success: bool, gcs_url: Optional[str])
        """
        try:
            import base64 as b64
            
            # Generate GCS blob path
            blob_path = self._get_file_path(file_type, podcast_name, episode_id, extension)
            
            # Get blob reference
            blob = self.bucket.blob(blob_path)
            
            # Check if file already exists
            if skip_existing and blob.exists():
                gcs_url = self.generate_gcs_url(blob_path)
                return (True, gcs_url)
            
            # Decode base64 content
            file_content = b64.b64decode(base64_content)
            
            # Upload binary content
            blob.upload_from_string(file_content, content_type=self._get_content_type(extension))
            
            # Generate and return GCS URL
            gcs_url = self.generate_gcs_url(blob_path)
            return (True, gcs_url)
            
        except Exception as e:
            print(f"  ✗ Error uploading {file_type} from base64 to GCS: {e}")
            return (False, None)

    def download_text_by_gcs_url(self, gcs_url: str, encoding: str = "utf-8") -> str:
        """
        Download a text file from GCS given a gs:// URL.
        
        Note: For transcripts, use download_transcript_by_gcs_url() instead to get both text and words.

        Args:
            gcs_url: GCS URL in the form gs://bucket/path/to/blob.ext
            encoding: Text encoding to use when decoding bytes (default: utf-8)

        Returns:
            The decoded text content.

        Raises:
            ValueError: If the URL is not a valid gs:// URL or bucket mismatches.
            Exception: If download fails for any reason.
        """
        if not gcs_url.startswith("gs://"):
            raise ValueError(f"Invalid GCS URL (must start with gs://): {gcs_url}")

        # Strip scheme and split into bucket and path
        without_scheme = gcs_url[len("gs://") :]
        parts = without_scheme.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid GCS URL format: {gcs_url}")

        bucket_name, blob_path = parts

        # Reads are safe cross-bucket: legacy episodes keep their transcript/media in
        # ``podcast-data-web`` while new ones live in the configured bucket
        # (``graphfolio-articles``). Use the configured bucket when it matches
        # (cached handle), else read directly from the URL's bucket. These are
        # read-only downloads, so no write-safety guard is needed.
        if bucket_name == self.bucket_name:
            source_bucket = self.bucket
        else:
            source_bucket = self.client.bucket(bucket_name)

        try:
            blob = source_bucket.blob(blob_path)
            content_bytes = blob.download_as_bytes()
            return content_bytes.decode(encoding)
        except Exception as e:
            raise Exception(f"Failed to download GCS object {gcs_url}: {e}") from e
    
    def download_transcript_by_gcs_url(self, gcs_url: str, encoding: str = "utf-8") -> Dict[str, Any]:
        """
        Download a transcript file from GCS given a gs:// URL.
        
        Auto-detects format: JSON (with text, sentences, and words) or text-only.
        Returns a dict with 'text', 'sentences', and 'words' keys.

        Args:
            gcs_url: GCS URL in the form gs://bucket/path/to/blob.ext
            encoding: Text encoding to use when decoding bytes (default: utf-8)

        Returns:
            Dictionary with keys:
                - 'text': str - The transcript text
                - 'sentences': Optional[List[Dict]] - List of sentence objects with timing, or None if unavailable
                - 'words': Optional[List[Dict]] - List of word objects with timing, or None if unavailable (deprecated)

        Raises:
            ValueError: If the URL is not a valid gs:// URL or bucket mismatches.
            Exception: If download fails for any reason.
        """
        if not gcs_url.startswith("gs://"):
            raise ValueError(f"Invalid GCS URL (must start with gs://): {gcs_url}")

        # Strip scheme and split into bucket and path
        without_scheme = gcs_url[len("gs://") :]
        parts = without_scheme.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid GCS URL format: {gcs_url}")

        bucket_name, blob_path = parts

        # Reads are safe cross-bucket: legacy episodes keep their transcript/media in
        # ``podcast-data-web`` while new ones live in the configured bucket
        # (``graphfolio-articles``). Use the configured bucket when it matches
        # (cached handle), else read directly from the URL's bucket. These are
        # read-only downloads, so no write-safety guard is needed.
        if bucket_name == self.bucket_name:
            source_bucket = self.bucket
        else:
            source_bucket = self.client.bucket(bucket_name)

        try:
            blob = source_bucket.blob(blob_path)
            content_bytes = blob.download_as_bytes()
            content = content_bytes.decode(encoding)
            
            # Auto-detect format: check file extension or try to parse as JSON
            is_json = blob_path.lower().endswith('.json')
            
            if is_json:
                # Try to parse as JSON
                try:
                    transcript_data = json.loads(content)
                    # Ensure it has the expected structure
                    if isinstance(transcript_data, dict):
                        return {
                            'text': transcript_data.get('text', ''),
                            'sentences': transcript_data.get('sentences'),
                            'words': transcript_data.get('words')  # Deprecated, kept for backward compatibility
                        }
                    else:
                        # Invalid JSON structure, treat as text
                        return {'text': content, 'sentences': None, 'words': None}
                except json.JSONDecodeError:
                    # JSON parse failed, treat as text
                    return {'text': content, 'sentences': None, 'words': None}
            else:
                # Text file (backward compatibility)
                return {'text': content, 'sentences': None, 'words': None}
                
        except Exception as e:
            raise Exception(f"Failed to download GCS object {gcs_url}: {e}") from e
    
    def download_file_by_gcs_url(self, gcs_url: str, output_path: Path) -> Path:
        """
        Download a binary file (e.g., MP3) from GCS given a gs:// URL.
        
        Args:
            gcs_url: GCS URL in the form gs://bucket/path/to/blob.ext
            output_path: Path where the file should be saved
            
        Returns:
            Path to the downloaded file
            
        Raises:
            ValueError: If the URL is not a valid gs:// URL or bucket mismatches.
            Exception: If download fails for any reason.
        """
        if not gcs_url.startswith("gs://"):
            raise ValueError(f"Invalid GCS URL (must start with gs://): {gcs_url}")

        # Strip scheme and split into bucket and path
        without_scheme = gcs_url[len("gs://") :]
        parts = without_scheme.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid GCS URL format: {gcs_url}")

        bucket_name, blob_path = parts

        # Ensure we're using the configured bucket
        if bucket_name != self.bucket_name:
            raise ValueError(
                f"GCS URL bucket '{bucket_name}' does not match configured bucket '{self.bucket_name}'"
            )

        try:
            # Ensure output directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Download file
            blob = self.bucket.blob(blob_path)
            blob.download_to_filename(str(output_path))
            return output_path
        except Exception as e:
            raise Exception(f"Failed to download GCS file {gcs_url}: {e}") from e
    
    def _get_content_type(self, extension: str) -> str:
        """
        Get MIME content type for a file extension.
        
        Args:
            extension: File extension (without dot)
            
        Returns:
            MIME content type string
        """
        content_types = {
            'mp3': 'audio/mpeg',
            'txt': 'text/plain',
            'json': 'application/json',
            'md': 'text/markdown',
            'svg': 'image/svg+xml',
            'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        }
        return content_types.get(extension.lower(), 'application/octet-stream')
    
    def generate_gcs_url(self, blob_path: str) -> str:
        """
        Generate GCS URL (gs://) for a blob path.
        
        Args:
            blob_path: GCS blob path (relative to bucket root)
            
        Returns:
            GCS URL in format: gs://{bucket_name}/{blob_path}
        """
        return f"gs://{self.bucket_name}/{blob_path}"
    
    def generate_public_url(self, blob_path: str) -> Optional[str]:
        """
        Generate public HTTPS URL for a blob.
        
        Note: This assumes the bucket or blob is configured for public access.
        Returns None if the bucket is not public.
        
        Args:
            blob_path: GCS blob path (relative to bucket root)
            
        Returns:
            Public HTTPS URL or None if bucket is not public
        """
        # Standard public URL format for GCS
        # https://storage.googleapis.com/{bucket_name}/{blob_path}
        return f"https://storage.googleapis.com/{self.bucket_name}/{blob_path}"
    
    def upload_episode_files(
        self,
        episode_id: str,
        podcast_name: str,
        mp3_path: Optional[Path] = None,
        transcript_data: Optional[Dict] = None,
        transcript_content: Optional[str] = None,
        transcript_path: Optional[Path] = None,
        summary_content: Optional[str] = None,
        summary_path: Optional[Path] = None,
        svg_content: Optional[str] = None,
        svg_path: Optional[Path] = None,
        events_markdown_content: Optional[str] = None,
        events_markdown_path: Optional[Path] = None,
        sentences_markdown_content: Optional[str] = None,
        sentences_markdown_path: Optional[Path] = None,
        pptx_base64: Optional[str] = None,
        marp_markdown_content: Optional[str] = None,
        ticker_recommendations_data: Optional[Dict] = None,
        ticker_marp_markdown_content: Optional[str] = None,
        skip_existing: bool = True
    ) -> Dict[str, Optional[str]]:
        """
        Upload all episode files to GCS and return URLs.
        
        This method uploads MP3, transcript, summary, and SVG files for an episode.
        It can accept either file paths or content strings (for streaming mode).
        
        Args:
            episode_id: Episode ID (matches Firestore document ID)
            podcast_name: Name of the podcast
            mp3_path: Path to MP3 file (optional)
            transcript_data: Transcript data as dict with 'text' and 'words' keys (preferred, uploads as JSON)
            transcript_content: Transcript content as string (deprecated, for backward compatibility)
            transcript_path: Path to transcript file (optional, if transcript_data not provided)
            summary_content: Summary content as string (optional, if summary_path not provided)
            summary_path: Path to summary file (optional, if summary_content not provided)
            svg_content: SVG content as string (optional, if svg_path not provided)
            svg_path: Path to SVG file (optional, if svg_content not provided)
            pptx_base64: Optional base64-encoded PPTX file content (optional)
            marp_markdown_content: Optional marp markdown content as string (optional)
            ticker_recommendations_data: Optional ticker recommendations data as dict (optional, uploads as JSON)
            ticker_marp_markdown_content: Optional ticker marp markdown content as string (optional)
            skip_existing: If True, skip upload if file already exists
            
        Returns:
            Dictionary with URLs:
            {
                'mp3_url': gs://... or None,
                'mp3_public_url': https://... or None,
                'transcript_url': gs://... or None,
                'transcript_public_url': https://... or None,
                'summary_url': gs://... or None,
                'summary_public_url': https://... or None,
                'summary_image_url': gs://... or None,
                'summary_image_public_url': https://... or None,
                'pptx_url': gs://... or None,
                'pptx_public_url': https://... or None,
                'marp_markdown_url': gs://... or None,
                'marp_markdown_public_url': https://... or None,
                'ticker_recommendations_url': gs://... or None,
                'ticker_recommendations_public_url': https://... or None,
                'ticker_marp_markdown_url': gs://... or None,
                'ticker_marp_markdown_public_url': https://... or None,
            }
        """
        result = {
            'mp3_url': None,
            'mp3_public_url': None,
            'transcript_url': None,
            'transcript_public_url': None,
            'summary_url': None,
            'summary_public_url': None,
            'summary_image_url': None,
            'summary_image_public_url': None,
            'pptx_url': None,
            'pptx_public_url': None,
            'marp_markdown_url': None,
            'marp_markdown_public_url': None,
            'ticker_recommendations_url': None,
            'ticker_recommendations_public_url': None,
            'ticker_marp_markdown_url': None,
            'ticker_marp_markdown_public_url': None,
        }
        
        # Upload MP3
        if mp3_path and mp3_path.exists():
            success, gcs_url = self.upload_file(
                mp3_path, 'mp3', podcast_name, episode_id, 'mp3', skip_existing
            )
            if success and gcs_url:
                result['mp3_url'] = gcs_url
                # Generate public URL
                blob_path = gcs_url.replace(f"gs://{self.bucket_name}/", "")
                result['mp3_public_url'] = self.generate_public_url(blob_path)
        
        # Upload transcript
        # Priority: transcript_data (dict) > transcript_path > transcript_content (string)
        if transcript_data is not None:
            # Upload transcript as JSON with text, sentences, and words
            # Ensure sentences are included in the data
            if isinstance(transcript_data, dict) and 'sentences' not in transcript_data:
                transcript_data['sentences'] = None
            transcript_json = json.dumps(transcript_data, ensure_ascii=False, indent=2)
            success, gcs_url = self.upload_file_from_string(
                transcript_json, 'transcripts', podcast_name, episode_id, 'json', skip_existing
            )
            if success and gcs_url:
                result['transcript_url'] = gcs_url
                blob_path = gcs_url.replace(f"gs://{self.bucket_name}/", "")
                result['transcript_public_url'] = self.generate_public_url(blob_path)
        elif transcript_path and transcript_path.exists():
            # Check if it's a JSON file or text file
            if transcript_path.suffix.lower() == '.json':
                # Upload JSON file as-is
                success, gcs_url = self.upload_file(
                    transcript_path, 'transcripts', podcast_name, episode_id, 'json', skip_existing
                )
            else:
                # Upload text file (backward compatibility)
                success, gcs_url = self.upload_file(
                    transcript_path, 'transcripts', podcast_name, episode_id, 'txt', skip_existing
                )
            if success and gcs_url:
                result['transcript_url'] = gcs_url
                blob_path = gcs_url.replace(f"gs://{self.bucket_name}/", "")
                result['transcript_public_url'] = self.generate_public_url(blob_path)
        elif transcript_content:
            # Backward compatibility: upload as text file
            success, gcs_url = self.upload_file_from_string(
                transcript_content, 'transcripts', podcast_name, episode_id, 'txt', skip_existing
            )
            if success and gcs_url:
                result['transcript_url'] = gcs_url
                blob_path = gcs_url.replace(f"gs://{self.bucket_name}/", "")
                result['transcript_public_url'] = self.generate_public_url(blob_path)
        
        # Upload summary
        if summary_path and summary_path.exists():
            success, gcs_url = self.upload_file(
                summary_path, 'summaries', podcast_name, episode_id, 'md', skip_existing
            )
            if success and gcs_url:
                result['summary_url'] = gcs_url
                blob_path = gcs_url.replace(f"gs://{self.bucket_name}/", "")
                result['summary_public_url'] = self.generate_public_url(blob_path)
        elif summary_content:
            success, gcs_url = self.upload_file_from_string(
                summary_content, 'summaries', podcast_name, episode_id, 'md', skip_existing
            )
            if success and gcs_url:
                result['summary_url'] = gcs_url
                blob_path = gcs_url.replace(f"gs://{self.bucket_name}/", "")
                result['summary_public_url'] = self.generate_public_url(blob_path)
        
        # Upload SVG image
        if svg_path and svg_path.exists():
            success, gcs_url = self.upload_file(
                svg_path, 'images', podcast_name, episode_id, 'svg', skip_existing
            )
            if success and gcs_url:
                result['summary_image_url'] = gcs_url
                blob_path = gcs_url.replace(f"gs://{self.bucket_name}/", "")
                result['summary_image_public_url'] = self.generate_public_url(blob_path)
        elif svg_content:
            success, gcs_url = self.upload_file_from_string(
                svg_content, 'images', podcast_name, episode_id, 'svg', skip_existing
            )
            if success and gcs_url:
                result['summary_image_url'] = gcs_url
                blob_path = gcs_url.replace(f"gs://{self.bucket_name}/", "")
                result['summary_image_public_url'] = self.generate_public_url(blob_path)
        
        # Upload events markdown to 'events' folder (separate from 'summaries')
        if events_markdown_path and events_markdown_path.exists():
            success, gcs_url = self.upload_file(
                events_markdown_path, 'events', podcast_name, episode_id, 'md', skip_existing
            )
            if success and gcs_url:
                result['events_markdown_url'] = gcs_url
                blob_path = gcs_url.replace(f"gs://{self.bucket_name}/", "")
                result['events_markdown_public_url'] = self.generate_public_url(blob_path)
        elif events_markdown_content:
            success, gcs_url = self.upload_file_from_string(
                events_markdown_content, 'events', podcast_name, episode_id, 'md', skip_existing
            )
            if success and gcs_url:
                result['events_markdown_url'] = gcs_url
                blob_path = gcs_url.replace(f"gs://{self.bucket_name}/", "")
                result['events_markdown_public_url'] = self.generate_public_url(blob_path)
        
        # Upload sentences markdown to 'sentences' folder
        if sentences_markdown_path and sentences_markdown_path.exists():
            success, gcs_url = self.upload_file(
                sentences_markdown_path, 'sentences', podcast_name, episode_id, 'md', skip_existing
            )
            if success and gcs_url:
                result['sentences_markdown_url'] = gcs_url
                blob_path = gcs_url.replace(f"gs://{self.bucket_name}/", "")
                result['sentences_markdown_public_url'] = self.generate_public_url(blob_path)
        elif sentences_markdown_content:
            success, gcs_url = self.upload_file_from_string(
                sentences_markdown_content, 'sentences', podcast_name, episode_id, 'md', skip_existing
            )
            if success and gcs_url:
                result['sentences_markdown_url'] = gcs_url
                blob_path = gcs_url.replace(f"gs://{self.bucket_name}/", "")
                result['sentences_markdown_public_url'] = self.generate_public_url(blob_path)
        
        # Upload PPTX file from base64 to 'presentations' folder
        if pptx_base64:
            success, gcs_url = self.upload_file_from_base64(
                pptx_base64, 'presentations', podcast_name, episode_id, 'pptx', skip_existing
            )
            if success and gcs_url:
                result['pptx_url'] = gcs_url
                blob_path = gcs_url.replace(f"gs://{self.bucket_name}/", "")
                result['pptx_public_url'] = self.generate_public_url(blob_path)
        
        # Upload marp markdown to 'marp' folder
        if marp_markdown_content:
            success, gcs_url = self.upload_file_from_string(
                marp_markdown_content, 'marp', podcast_name, episode_id, 'md', skip_existing
            )
            if success and gcs_url:
                result['marp_markdown_url'] = gcs_url
                blob_path = gcs_url.replace(f"gs://{self.bucket_name}/", "")
                result['marp_markdown_public_url'] = self.generate_public_url(blob_path)
        
        # Upload ticker_recommendations to 'ticker_recommendations' folder as JSON
        if ticker_recommendations_data:
            ticker_recommendations_json = json.dumps(ticker_recommendations_data, ensure_ascii=False, indent=2)
            success, gcs_url = self.upload_file_from_string(
                ticker_recommendations_json, 'ticker_recommendations', podcast_name, episode_id, 'json', skip_existing
            )
            if success and gcs_url:
                result['ticker_recommendations_url'] = gcs_url
                blob_path = gcs_url.replace(f"gs://{self.bucket_name}/", "")
                result['ticker_recommendations_public_url'] = self.generate_public_url(blob_path)
        
        # Upload ticker_marp_markdown to 'ticker_marp' folder
        if ticker_marp_markdown_content:
            success, gcs_url = self.upload_file_from_string(
                ticker_marp_markdown_content, 'ticker_marp', podcast_name, episode_id, 'md', skip_existing
            )
            if success and gcs_url:
                result['ticker_marp_markdown_url'] = gcs_url
                blob_path = gcs_url.replace(f"gs://{self.bucket_name}/", "")
                result['ticker_marp_markdown_public_url'] = self.generate_public_url(blob_path)
        
        return result

