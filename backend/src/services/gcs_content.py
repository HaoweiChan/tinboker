"""GCS content fetching service for retrieving blob data from Google Cloud Storage"""
import os
import re
import json
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Optional
from pathlib import Path
from google.cloud import storage
from google.oauth2 import service_account
from google.api_core.exceptions import NotFound
import httpx


logger = logging.getLogger(__name__)

# Dedicated I/O thread pool for blocking GCS calls, shared across all service
# instances. The default asyncio executor is only ~(cpu+4) threads (≈8 on the
# 4-core VPS) and is shared with every other run_in_executor call (FinMind, etc.),
# so under a post-cache-purge spike GCS fetches would queue behind it. A dedicated
# pool sized to the fetch semaphore keeps episode hydration from starving.
_GCS_EXECUTOR = ThreadPoolExecutor(max_workers=20, thread_name_prefix="gcs")


class GCSContentService:
    """Handles all Google Cloud Storage content fetching operations"""

    def __init__(self):
        self._client: Optional[storage.Client] = None
        self._semaphore = asyncio.Semaphore(20)

    def get_client(self) -> Optional[storage.Client]:
        """Get or create GCS client, trying multiple credential sources"""
        if self._client is not None:
            return self._client

        # Try Firebase Admin credentials first
        try:
            import firebase_admin
            from firebase_admin import credentials as firebase_credentials
            app = firebase_admin.get_app()
            firebase_cred = app.credential
            if firebase_cred and isinstance(firebase_cred, firebase_credentials.Certificate):
                try:
                    if hasattr(firebase_cred, '_cert_path') and firebase_cred._cert_path:
                        with open(firebase_cred._cert_path, 'r') as f:
                            sa_info = json.load(f)
                            creds = service_account.Credentials.from_service_account_info(sa_info)
                            self._client = storage.Client(credentials=creds, project=sa_info.get('project_id'))
                            logger.debug("Created GCS client from Firebase certificate file")
                            return self._client
                    elif hasattr(firebase_cred, '_info'):
                        sa_info = firebase_cred._info
                        creds = service_account.Credentials.from_service_account_info(sa_info)
                        self._client = storage.Client(credentials=creds, project=sa_info.get('project_id'))
                        logger.debug("Created GCS client from Firebase _info")
                        return self._client
                except (AttributeError, FileNotFoundError, json.JSONDecodeError, Exception) as e:
                    logger.debug(f"Could not extract credentials from Firebase Certificate: {e}")
        except (ValueError, ImportError, AttributeError) as e:
            logger.debug(f"Firebase not initialized: {e}")

        # Try credentials from file path
        credentials_path = os.getenv("GCP_CREDENTIALS_PATH")
        if credentials_path:
            try:
                cred_path = Path(credentials_path).expanduser().resolve()
                if cred_path.exists():
                    creds = service_account.Credentials.from_service_account_file(str(cred_path))
                    with open(cred_path, 'r') as f:
                        project_id = json.load(f).get("project_id")
                    self._client = storage.Client(credentials=creds, project=project_id)
                    logger.debug("Created GCS client from credentials file")
                    return self._client
                else:
                    logger.warning(f"Credentials file not found: {cred_path}")
            except Exception as e:
                logger.warning(f"Failed to load credentials from file {credentials_path}: {e}")

        # Try credentials from JSON env var
        credentials_json = os.getenv("GCP_CREDENTIALS_JSON") or os.getenv("GCS_SERVICE_ACCOUNT_JSON")
        if credentials_json:
            try:
                if isinstance(credentials_json, str):
                    credentials_json = credentials_json.strip()
                    if credentials_json:
                        creds_dict = json.loads(credentials_json)
                        creds = service_account.Credentials.from_service_account_info(creds_dict)
                        self._client = storage.Client(credentials=creds, project=creds_dict.get("project_id"))
                        logger.info("Created GCS client from credentials JSON")
                        return self._client
                else:
                    creds = service_account.Credentials.from_service_account_info(credentials_json)
                    self._client = storage.Client(credentials=creds, project=credentials_json.get("project_id"))
                    return self._client
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse GCP_CREDENTIALS_JSON: {e}")
            except Exception as e:
                logger.warning(f"Failed to create GCS client with credentials JSON: {e}")

        # Default credentials fallback
        try:
            self._client = storage.Client()
            return self._client
        except Exception:
            return None

    @staticmethod
    def parse_gs_url(gs_url: str) -> Optional[tuple[str, str]]:
        """Parse GCS URL into (bucket_name, blob_path) or None if invalid"""
        if not gs_url:
            return None
        if gs_url.startswith("gs://"):
            parts = gs_url[5:].split("/", 1)
            return (parts[0], parts[1]) if len(parts) == 2 else None
        match = re.match(r"https://storage\.googleapis\.com/([^/]+)/(.+)", gs_url)
        return (match.group(1), match.group(2)) if match else None

    async def fetch_gcs_content(self, gs_url: str, timeout: float = 10.0) -> str:
        """Fetch content from a GCS blob with timeout, returns empty string on failure"""
        parsed = self.parse_gs_url(gs_url)
        if not parsed:
            return ""
        bucket_name, blob_path = parsed
        client = self.get_client()
        if not client:
            return ""

        def _fetch_sync():
            # Download directly — skip the separate blob.exists() probe, which doubled
            # the GCS round trips on every cold episode hydration (the dominant cold-load
            # cost, since the payloads themselves are tiny). A genuinely missing blob
            # raises NotFound (no retry — not transient); other errors retry once.
            last_err = None
            for _attempt in range(2):
                try:
                    blob = client.bucket(bucket_name).blob(blob_path)
                    return blob.download_as_text()
                except NotFound:
                    return ""
                except Exception as e:
                    last_err = e
            logger.warning(f"Error fetching GCS content from {gs_url} after retry: {last_err}")
            return ""

        try:
            async with self._semaphore:
                loop = asyncio.get_event_loop()
                return await asyncio.wait_for(loop.run_in_executor(_GCS_EXECUTOR, _fetch_sync), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching GCS content from {gs_url} (timeout: {timeout}s)")
            return ""
        except Exception as e:
            logger.warning(f"Exception fetching GCS content from {gs_url}: {e}")
            return ""

    async def fetch_http_content(self, url: str, timeout: float = 10.0) -> str:
        """Fetch content from HTTP/HTTPS URL, returns empty string on failure"""
        if not url or not (url.startswith("http://") or url.startswith("https://")):
            return ""
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                return response.text
        except Exception:
            return ""

    async def fetch_url_content(self, url: str, timeout: float = 10.0) -> str:
        """Fetch content from any URL (GCS or HTTP), returns empty string on failure"""
        if not url:
            return ""
        if url.startswith("gs://") or "storage.googleapis.com" in url:
            return await self.fetch_gcs_content(url, timeout)
        if url.startswith("http://") or url.startswith("https://"):
            return await self.fetch_http_content(url, timeout)
        return ""

    async def generate_signed_url(self, gs_url: str, expiration_hours: int = 12) -> Optional[str]:
        """Generate a V4 signed GET URL for a private GCS blob.

        Requires service-account credentials with a private key (the ADC fallback
        client cannot sign); returns None when signing is unavailable or the blob
        does not exist.
        """
        parsed = self.parse_gs_url(gs_url)
        if not parsed:
            return None
        bucket_name, blob_path = parsed
        client = self.get_client()
        if not client:
            return None

        def _sign_sync() -> Optional[str]:
            try:
                blob = client.bucket(bucket_name).blob(blob_path)
                if not blob.exists():
                    return None
                return blob.generate_signed_url(
                    version="v4",
                    expiration=timedelta(hours=expiration_hours),
                    method="GET",
                )
            except Exception as e:
                logger.warning(f"Error generating signed URL for {gs_url}: {e}")
                return None

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_GCS_EXECUTOR, _sign_sync)

    async def upload_content(self, bucket_name: str, blob_path: str, content: str, content_type: str = 'text/markdown') -> None:
        """Upload string content to a GCS blob"""
        client = self.get_client()
        if not client:
            raise RuntimeError("GCS client not available")

        def _upload_sync():
            blob = client.bucket(bucket_name).blob(blob_path)
            blob.upload_from_string(content, content_type=content_type)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_GCS_EXECUTOR, _upload_sync)

    async def upload_bytes(self, bucket_name: str, blob_path: str, data: bytes, content_type: str) -> None:
        """Upload raw bytes (e.g. an uploaded image/video) to a GCS blob."""
        client = self.get_client()
        if not client:
            raise RuntimeError("GCS client not available")

        def _upload_sync():
            blob = client.bucket(bucket_name).blob(blob_path)
            blob.upload_from_string(data, content_type=content_type)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_GCS_EXECUTOR, _upload_sync)

    async def delete_blob(self, bucket_name: str, blob_path: str) -> None:
        """Delete a GCS blob if it exists"""
        client = self.get_client()
        if not client:
            raise RuntimeError("GCS client not available")

        def _delete_sync():
            blob = client.bucket(bucket_name).blob(blob_path)
            if blob.exists():
                blob.delete()

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_GCS_EXECUTOR, _delete_sync)
