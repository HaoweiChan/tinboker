#!/usr/bin/env python3
"""Local media storage for podcast episode artifacts (P5 — GCS decommission).

Every episode artifact (mp3, transcript JSON, summary/events/sentences/marp
markdown, SVG, ticker insights, social-card PNGs, PPTX) is written to the VPS
media directory that Caddy serves publicly, and the returned URL points at that
host. Nothing here talks to Google Cloud Storage any more.

The class and method names are unchanged from the GCS era on purpose — every
caller, script, test and the regen MCP keep working; only the backend moved.
``gs://`` is dead: ``generate_gcs_url`` returns the same public https URL as
``generate_public_url``, so ``*_url`` and ``*_public_url`` are identical
(docs/firestore-contract.md § 11.7).

The on-disk layout is byte-identical to the old bucket layout, so the files
copied out of ``graphfolio-articles`` and the files written here live uniformly::

    {MEDIA_STORAGE_ROOT}/{bucket}/{base_path?}/{type}/{podcast_hash12}/{id}.{ext}
    {MEDIA_PUBLIC_BASE}/{bucket}/{base_path?}/{type}/{podcast_hash12}/{id}.{ext}

Env:
    MEDIA_STORAGE_ROOT  default /srv/tinboker-media (prod); falls back to
                        ``pipelines/.media`` when that path does not exist, so a
                        dev checkout never needs the prod directory.
    MEDIA_PUBLIC_BASE   default https://podcast-api.tinboker.com/media
    GCS_BUCKET_NAME     kept as the *directory* name under the root, so existing
                        and new files share one tree. Default graphfolio-articles.
    GCS_BASE_PATH       optional path prefix inside that directory (unchanged).
"""

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from src.secrets_bootstrap import bootstrap

# Load secrets from GSM (idempotent — safe if already bootstrapped at entry point).
bootstrap()

DEFAULT_MEDIA_ROOT = "/srv/tinboker-media"
DEFAULT_PUBLIC_BASE = "https://podcast-api.tinboker.com/media"
DEFAULT_BUCKET = "graphfolio-articles"

# The only two directories under the media root. These are the *full* former bucket
# names — the live convention, matching what Caddy serves. (A stale Phase-E plan used
# short names, articles/ + web/; nothing ever served those, and the script that would
# have rewritten URLs to them is deleted. See docs/firestore-contract.md § 11.7.)
MEDIA_BUCKETS = frozenset({"graphfolio-articles", "podcast-data-web"})

_GCS_HTTPS_RE = re.compile(r"^https://storage\.googleapis\.com/([^/]+)/(.+)$")


def media_root() -> Path:
    """Root directory holding one subdirectory per legacy bucket name.

    Prod mounts ``/srv/tinboker-media``; dev checkouts don't have it, so fall back
    to a project-relative directory rather than hard-requiring the prod path.
    """
    env = os.getenv("MEDIA_STORAGE_ROOT")
    if env:
        return Path(env).expanduser()
    default = Path(DEFAULT_MEDIA_ROOT)
    if default.is_dir():
        return default
    # pipelines/.media — src/service/… → parents[4] is the workspace root.
    return Path(__file__).resolve().parents[4] / ".media"


def public_base() -> str:
    """Public URL prefix Caddy serves the media root at (no trailing slash)."""
    return os.getenv("MEDIA_PUBLIC_BASE", DEFAULT_PUBLIC_BASE).rstrip("/")


def resolve_media_path(bucket: str, blob_path: str) -> Path:
    """Absolute on-disk path for ``bucket/blob_path``, with both safety guards.

    Module-level and credential-free on purpose: working out where a file lives is
    pure arithmetic over the media root, and needing a GCS client for it means an ops
    script that only wants to read a summary has to authenticate to Google first.
    """
    if bucket not in MEDIA_BUCKETS:
        raise ValueError(
            f"Unknown media bucket {bucket!r} (expected one of {sorted(MEDIA_BUCKETS)})"
        )
    root = media_root().resolve()
    path = (root / bucket / blob_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"Media path escapes {root}: {bucket}/{blob_path}")
    return path


def path_for_media_url(url: str) -> Optional[Path]:
    """On-disk path for a gs:// / storage.googleapis.com / media URL, or ``None``."""
    parsed = split_media_url(url)
    return resolve_media_path(parsed[0], parsed[1]) if parsed else None


def split_media_url(url: str) -> Optional[Tuple[str, str]]:
    """``(bucket, blob_path)`` from a gs://, storage.googleapis.com or media URL.

    All three forms are accepted because episode docs still carry historical
    ``gs://`` values alongside the rewritten https ones.
    """
    if not url:
        return None
    url = str(url).split("?", 1)[0]
    if url.startswith("gs://"):
        bucket, _, blob = url[len("gs://"):].partition("/")
        return (bucket, blob) if bucket and blob else None
    m = _GCS_HTTPS_RE.match(url)
    if m:
        return m.group(1), m.group(2)
    prefix = public_base() + "/"
    if url.startswith(prefix):
        bucket, _, blob = url[len(prefix):].partition("/")
        return (bucket, blob) if bucket and blob else None
    return None


def _atomic_write(dest: Path, data: bytes) -> None:
    """Write ``data`` to ``dest`` so readers never observe a partial file.

    Same-directory temp file + ``os.replace`` (atomic within one filesystem) —
    Caddy serves this tree while the pipeline writes into it.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=f".{dest.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        # mkstemp creates 0600 and os.replace keeps it; Caddy runs as another
        # user and serves this tree, so 0600 files come back as 403.
        os.chmod(tmp, 0o644)
        os.replace(tmp, dest)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _atomic_copy(src: Path, dest: Path) -> None:
    """Copy ``src`` onto ``dest`` atomically (used for mp3s, which are large)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=f".{dest.name}.", suffix=".tmp")
    os.close(fd)
    try:
        shutil.copyfile(src, tmp)
        # mkstemp creates 0600 and os.replace keeps it; Caddy runs as another
        # user and serves this tree, so 0600 files come back as 403.
        os.chmod(tmp, 0o644)
        os.replace(tmp, dest)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class GCSStorageService:
    """Writes podcast episode files to the VPS media directory and returns URLs."""

    def __init__(self):
        self.bucket_name = os.getenv("GCS_BUCKET_NAME") or DEFAULT_BUCKET
        self.base_path = os.getenv("GCS_BASE_PATH", "").strip('/')
        self.media_root = media_root()
        self.public_base = public_base()
        self.root = self.media_root / self.bucket_name

    # ── paths & URLs ──────────────────────────────────────────────────────

    def _get_podcast_hash(self, podcast_name: str) -> str:
        """12-char hash of the podcast name, used as the directory component."""
        return hashlib.sha256(podcast_name.encode('utf-8')).hexdigest()[:12]

    def _get_file_path(self, file_type: str, podcast_name: str, episode_id: str, extension: str) -> str:
        """Blob path ``{base_path}/{type}/{podcast_hash}/{episode_id}.{ext}``.

        Unchanged from the GCS era — this is what keeps migrated and new files
        addressable by the same relative path.
        """
        parts = []
        if self.base_path:
            parts.append(self.base_path)
        parts.extend([file_type, self._get_podcast_hash(podcast_name), f"{episode_id}.{extension}"])
        return '/'.join(parts)

    def local_path(self, blob_path: str, bucket: Optional[str] = None) -> Path:
        """Absolute on-disk path for a blob path in ``bucket`` (default: ours).

        Delegates to :func:`resolve_media_path`, which holds both guards — the bucket
        allow-list and the escape-the-root check — so instance and module callers
        cannot drift apart.
        """
        return resolve_media_path(bucket or self.bucket_name, blob_path)

    def path_for_url(self, url: str) -> Optional[Path]:
        """On-disk path for a gs:// / storage.googleapis.com / media URL."""
        return path_for_media_url(url)

    def generate_gcs_url(self, blob_path: str) -> str:
        """The artifact's public URL. gs:// is dead — this is the https URL."""
        return self.generate_public_url(blob_path)

    def generate_public_url(self, blob_path: str) -> str:
        """Public https URL for a blob path.

        A full https URL is returned unchanged, so the historical
        ``url.replace("gs://<bucket>/", "")`` round-trips in callers stay correct.
        """
        if blob_path.startswith(("http://", "https://")):
            return blob_path
        return f"{self.public_base}/{self.bucket_name}/{blob_path}"

    def blob_exists(self, url: str) -> bool:
        """True when the artifact behind ``url`` is present on disk."""
        path = self.path_for_url(url)
        return bool(path and path.is_file())

    # ── writes ────────────────────────────────────────────────────────────

    def upload_file(
        self,
        local_file_path: Path,
        file_type: str,
        podcast_name: str,
        episode_id: str,
        extension: Optional[str] = None,
        skip_existing: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """Copy a local file into the media tree. Returns ``(ok, public_url)``."""
        try:
            if extension is None:
                extension = local_file_path.suffix.lstrip('.')
            blob_path = self._get_file_path(file_type, podcast_name, episode_id, extension)
            dest = self.local_path(blob_path)
            if skip_existing and dest.is_file() and dest.stat().st_size == local_file_path.stat().st_size:
                return (True, self.generate_public_url(blob_path))
            _atomic_copy(local_file_path, dest)
            return (True, self.generate_public_url(blob_path))
        except Exception as e:
            print(f"  ✗ Error writing {local_file_path.name} to media store: {e}")
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
        """Write string content into the media tree. Returns ``(ok, public_url)``."""
        return self._write(
            content.encode('utf-8'), file_type, podcast_name, episode_id, extension, skip_existing
        )

    def upload_file_from_base64(
        self,
        base64_content: str,
        file_type: str,
        podcast_name: str,
        episode_id: str,
        extension: str,
        skip_existing: bool = True,
        public: bool = False,
    ) -> Tuple[bool, Optional[str]]:
        """Write base64-decoded bytes into the media tree.

        ``public`` is accepted for call-site compatibility and ignored: everything
        under the media root is already served publicly by Caddy.
        """
        import base64 as b64

        try:
            data = b64.b64decode(base64_content)
        except Exception as e:
            print(f"  ✗ Error decoding {file_type} base64: {e}")
            return (False, None)
        return self._write(data, file_type, podcast_name, episode_id, extension, skip_existing)

    def _write(
        self, data: bytes, file_type: str, podcast_name: str,
        episode_id: str, extension: str, skip_existing: bool,
    ) -> Tuple[bool, Optional[str]]:
        try:
            blob_path = self._get_file_path(file_type, podcast_name, episode_id, extension)
            dest = self.local_path(blob_path)
            if not (skip_existing and dest.is_file()):
                _atomic_write(dest, data)
            return (True, self.generate_public_url(blob_path))
        except Exception as e:
            print(f"  ✗ Error writing {file_type} content to media store: {e}")
            return (False, None)

    # ── reads ─────────────────────────────────────────────────────────────

    def download_text_by_gcs_url(self, gcs_url: str, encoding: str = "utf-8") -> str:
        """Read a text artifact by URL (gs://, storage.googleapis.com or media)."""
        path = self.path_for_url(gcs_url)
        if not path:
            raise ValueError(f"Unrecognised media URL: {gcs_url}")
        try:
            return path.read_bytes().decode(encoding)
        except Exception as e:
            raise Exception(f"Failed to read media object {gcs_url} ({path}): {e}") from e

    def download_transcript_by_gcs_url(self, gcs_url: str, encoding: str = "utf-8") -> Dict[str, Any]:
        """Read a transcript artifact; auto-detects JSON vs plain text.

        Returns ``{'text', 'sentences', 'words'}`` ('words' is deprecated).
        """
        content = self.download_text_by_gcs_url(gcs_url, encoding)
        if not str(gcs_url).lower().split("?", 1)[0].endswith('.json'):
            return {'text': content, 'sentences': None, 'words': None}
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return {'text': content, 'sentences': None, 'words': None}
        if not isinstance(data, dict):
            return {'text': content, 'sentences': None, 'words': None}
        return {
            'text': data.get('text', ''),
            'sentences': data.get('sentences'),
            'words': data.get('words'),
        }

    def download_file_by_gcs_url(self, gcs_url: str, output_path: Path) -> Path:
        """Copy a binary artifact (e.g. an mp3) out of the media tree."""
        path = self.path_for_url(gcs_url)
        if not path:
            raise ValueError(f"Unrecognised media URL: {gcs_url}")
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, output_path)
            return output_path
        except Exception as e:
            raise Exception(f"Failed to read media file {gcs_url} ({path}): {e}") from e

    # ── the one call the pipeline actually makes ──────────────────────────

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
        ticker_insights_data: Optional[Dict] = None,
        ticker_marp_markdown_content: Optional[str] = None,
        skip_existing: bool = True
    ) -> Dict[str, Optional[str]]:
        """Write every supplied episode artifact and return its ``*_url`` fields.

        Both ``x_url`` and ``x_public_url`` get the same public https URL — readers
        prefer the public one and gs:// no longer exists.
        """
        keys = (
            'mp3', 'transcript', 'summary', 'summary_image', 'events_markdown',
            'sentences_markdown', 'pptx', 'marp_markdown', 'ticker_insights',
            'ticker_marp_markdown',
        )
        result: Dict[str, Optional[str]] = {}
        for k in keys:
            result[f'{k}_url'] = None
            result[f'{k}_public_url'] = None

        def _set(key: str, ok: bool, url: Optional[str]) -> None:
            if ok and url:
                result[f'{key}_url'] = result[f'{key}_public_url'] = url

        def _from_path(path: Path, file_type: str, ext: str) -> Tuple[bool, Optional[str]]:
            return self.upload_file(path, file_type, podcast_name, episode_id, ext, skip_existing)

        def _from_string(content: str, file_type: str, ext: str) -> Tuple[bool, Optional[str]]:
            return self.upload_file_from_string(
                content, file_type, podcast_name, episode_id, ext, skip_existing
            )

        if mp3_path and mp3_path.exists():
            _set('mp3', *_from_path(mp3_path, 'mp3', 'mp3'))

        # Priority: transcript_data (dict) > transcript_path > transcript_content
        if transcript_data is not None:
            if isinstance(transcript_data, dict) and 'sentences' not in transcript_data:
                transcript_data['sentences'] = None
            _set('transcript', *_from_string(
                json.dumps(transcript_data, ensure_ascii=False, indent=2), 'transcripts', 'json'
            ))
        elif transcript_path and transcript_path.exists():
            ext = 'json' if transcript_path.suffix.lower() == '.json' else 'txt'
            _set('transcript', *_from_path(transcript_path, 'transcripts', ext))
        elif transcript_content:
            _set('transcript', *_from_string(transcript_content, 'transcripts', 'txt'))

        if summary_path and summary_path.exists():
            _set('summary', *_from_path(summary_path, 'summaries', 'md'))
        elif summary_content:
            _set('summary', *_from_string(summary_content, 'summaries', 'md'))

        if svg_path and svg_path.exists():
            _set('summary_image', *_from_path(svg_path, 'images', 'svg'))
        elif svg_content:
            _set('summary_image', *_from_string(svg_content, 'images', 'svg'))

        if events_markdown_path and events_markdown_path.exists():
            _set('events_markdown', *_from_path(events_markdown_path, 'events', 'md'))
        elif events_markdown_content:
            _set('events_markdown', *_from_string(events_markdown_content, 'events', 'md'))

        if sentences_markdown_path and sentences_markdown_path.exists():
            _set('sentences_markdown', *_from_path(sentences_markdown_path, 'sentences', 'md'))
        elif sentences_markdown_content:
            _set('sentences_markdown', *_from_string(sentences_markdown_content, 'sentences', 'md'))

        if pptx_base64:
            _set('pptx', *self.upload_file_from_base64(
                pptx_base64, 'presentations', podcast_name, episode_id, 'pptx', skip_existing
            ))

        if marp_markdown_content:
            _set('marp_markdown', *_from_string(marp_markdown_content, 'marp', 'md'))

        if ticker_insights_data:
            _set('ticker_insights', *_from_string(
                json.dumps(ticker_insights_data, ensure_ascii=False, indent=2),
                'ticker_insights', 'json',
            ))

        if ticker_marp_markdown_content:
            _set('ticker_marp_markdown', *_from_string(
                ticker_marp_markdown_content, 'ticker_marp', 'md'
            ))

        return result
