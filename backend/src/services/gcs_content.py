"""Episode-artifact content store (VPS local disk since P5 — GCS decommission).

The class and method names are unchanged from the GCS era so callers keep working,
but nothing here talks to Google Cloud Storage any more: artifacts are read from and
written to the media directory Caddy serves publicly, using the same
``{root}/{bucket}/{blob_path}`` layout the pipelines writer uses
(docs/firestore-contract.md § 11.7).

Env:
    MEDIA_STORAGE_ROOT  default /srv/tinboker-media (bind-mounted into the container);
                        falls back to ``backend/.media`` when that path is absent, so
                        a dev checkout never needs the prod directory.
    MEDIA_PUBLIC_BASE   default https://podcast-api.tinboker.com/media
"""
import os
import re
import asyncio
import logging
import tempfile
from typing import Optional
from pathlib import Path
import httpx


logger = logging.getLogger(__name__)

DEFAULT_MEDIA_ROOT = "/srv/tinboker-media"
DEFAULT_PUBLIC_BASE = "https://podcast-api.tinboker.com/media"

# The only two directories under the media root. These are the *full* former bucket
# names — the live convention, matching what Caddy serves. (A stale Phase-E plan
# used short names, articles/ + web/; nothing ever served those. See
# docs/firestore-contract.md § 11.7.)
MEDIA_BUCKETS = frozenset({"graphfolio-articles", "podcast-data-web"})

_GCS_HTTPS_RE = re.compile(r"^https://storage\.googleapis\.com/([^/]+)/(.+)$")


def media_root() -> Path:
    """Root directory holding one subdirectory per legacy bucket name."""
    env = os.getenv("MEDIA_STORAGE_ROOT")
    if env:
        return Path(env).expanduser()
    default = Path(DEFAULT_MEDIA_ROOT)
    if default.is_dir():
        return default
    return Path(__file__).resolve().parents[2] / ".media"  # backend/.media


def public_base() -> str:
    """Public URL prefix Caddy serves the media root at (no trailing slash)."""
    return os.getenv("MEDIA_PUBLIC_BASE", DEFAULT_PUBLIC_BASE).rstrip("/")


def media_path(bucket_name: str, blob_path: str) -> Path:
    """On-disk location of an artifact — the single gate for every read/write/delete.

    Two guards, both here so no caller can skip them:

    1. ``bucket_name`` must be one of the two real media directories. An unknown
       bucket is a bug or a poisoned doc field, never a reason to silently mkdir a
       tree nothing serves.
    2. The resolved path must stay inside the media root, which closes every
       ``../`` traversal primitive reachable from a stored URL.
    """
    if bucket_name not in MEDIA_BUCKETS:
        raise ValueError(
            f"Unknown media bucket {bucket_name!r} (expected one of {sorted(MEDIA_BUCKETS)})"
        )
    root = media_root().resolve()
    path = (root / bucket_name / blob_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Media path escapes {root}: {bucket_name}/{blob_path}")
    return path


def media_url(bucket_name: str, blob_path: str) -> str:
    """Public URL of an artifact."""
    return f"{public_base()}/{bucket_name}/{blob_path}"


def _atomic_write(dest: Path, data: bytes) -> None:
    """Write ``data`` to ``dest`` so readers never observe a partial file.

    Same-directory temp file + ``os.replace`` (atomic within one filesystem) — Caddy
    serves this tree while the API writes into it.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=f".{dest.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, dest)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class GCSContentService:
    """Reads and writes episode artifacts on the VPS media disk."""

    @staticmethod
    def parse_gs_url(gs_url: str) -> Optional[tuple[str, str]]:
        """Parse an artifact URL into ``(bucket_name, blob_path)``.

        Accepts the historical ``gs://`` and ``storage.googleapis.com`` forms as well
        as the current media-host URL, because episode docs written before the P5
        rewrite still carry the old shapes.
        """
        if not gs_url:
            return None
        gs_url = str(gs_url).split("?", 1)[0]
        if gs_url.startswith("gs://"):
            parts = gs_url[5:].split("/", 1)
            return (parts[0], parts[1]) if len(parts) == 2 else None
        match = _GCS_HTTPS_RE.match(gs_url)
        if match:
            return (match.group(1), match.group(2))
        prefix = public_base() + "/"
        if gs_url.startswith(prefix):
            parts = gs_url[len(prefix):].split("/", 1)
            return (parts[0], parts[1]) if len(parts) == 2 else None
        return None

    async def fetch_gcs_content(self, gs_url: str, timeout: float = 10.0) -> str:
        """Read an artifact off the media disk; "" when missing or unreadable.

        ``timeout`` stays in the signature for call-site compatibility — a local read
        has no network to time out on. Returning "" (never raising) is load-bearing:
        ``EpisodeTransformer`` treats an empty result as "fetch failed, keep the
        stored value and don't cache a half-hydrated episode".
        """
        parsed = self.parse_gs_url(gs_url)
        if not parsed:
            return ""

        def _read() -> str:
            try:
                return media_path(*parsed).read_bytes().decode("utf-8")
            except FileNotFoundError:
                return ""
            except Exception as e:  # noqa: BLE001 — a bad artifact (or a rejected
                # bucket/traversing path) must not 500 a page; log it and degrade.
                logger.warning("Error reading media file %s: %s", gs_url, e)
                return ""

        return await asyncio.to_thread(_read)

    async def fetch_http_content(self, url: str, timeout: float = 10.0) -> str:
        """Fetch content from an HTTP/HTTPS URL, returns empty string on failure"""
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
        """Fetch any artifact URL: local disk when it maps to the media store, else HTTP."""
        if not url:
            return ""
        if self.parse_gs_url(url):
            return await self.fetch_gcs_content(url, timeout)
        if url.startswith("http://") or url.startswith("https://"):
            return await self.fetch_http_content(url, timeout)
        return ""

    async def generate_signed_url(self, gs_url: str, expiration_hours: int = 12) -> Optional[str]:
        """The artifact's public media URL, or None when it isn't on disk.

        Signing died with GCS: the media host serves these files directly, so a stable
        public URL replaces the expiring signed one. ``expiration_hours`` is accepted
        and ignored so callers need no change.
        """
        parsed = self.parse_gs_url(gs_url)
        if not parsed:
            return None
        try:
            path = media_path(*parsed)
        except ValueError as e:  # rejected bucket / traversing path → no audio, not a 500
            logger.warning("Refusing to resolve %s: %s", gs_url, e)
            return None
        if not await asyncio.to_thread(path.is_file):
            return None
        return media_url(*parsed)

    async def upload_content(
        self, bucket_name: str, blob_path: str, content: str, content_type: str = 'text/markdown'
    ) -> None:
        """Write string content into the media store.

        ``content_type`` is unused — the media host infers it from the extension.
        """
        await asyncio.to_thread(
            _atomic_write, media_path(bucket_name, blob_path), content.encode("utf-8")
        )

    async def upload_bytes(self, bucket_name: str, blob_path: str, data: bytes, content_type: str) -> None:
        """Write raw bytes (e.g. an uploaded image/video) into the media store."""
        await asyncio.to_thread(_atomic_write, media_path(bucket_name, blob_path), data)

    async def upload_bytes_public(
        self, bucket_name: str, blob_path: str, data: bytes, content_type: str
    ) -> str:
        """Write bytes and return the stable public URL.

        Used for social-card PNGs that Threads/FB fetch directly and the admin page
        embeds. Everything under the media root is publicly served, so the old
        ``make_public`` ACL step is gone.
        """
        await self.upload_bytes(bucket_name, blob_path, data, content_type)
        return media_url(bucket_name, blob_path)

    async def delete_blob(self, bucket_name: str, blob_path: str) -> None:
        """Delete an artifact from the media store if it exists."""
        await asyncio.to_thread(media_path(bucket_name, blob_path).unlink, True)
