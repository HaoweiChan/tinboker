"""Slug generation utilities for wiki page filenames and IDs."""

import hashlib
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query-parameter name prefixes dropped during URL canonicalization (tracking junk).
_TRACKING_PREFIXES = ("utm_", "fbclid", "gclid", "mc_", "igshid", "ref", "spm")


def slugify(text: str) -> str:
    """Convert text to a URL/filename-safe slug.

    Handles CJK characters by keeping them as-is (no transliteration).
    """
    text = unicodedata.normalize("NFKC", text).strip().lower()
    text = re.sub(r"[^\w\s\u4e00-\u9fff\u3400-\u4dbf-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-")


def ticker_slug(ticker: str) -> str:
    """Normalize ticker symbol to a slug (lowercase)."""
    return ticker.strip().lower().replace(".", "-")


def episode_slug(podcast_name: str, episode_number: int | None, title: str) -> str:
    """Build a deterministic slug for an episode page."""
    base = slugify(podcast_name)
    if episode_number is not None:
        return f"{base}_ep{episode_number}"
    return f"{base}_{slugify(title)[:60]}"


def canonicalize_url(url: str) -> str:
    """Normalize a URL for stable dedup.

    Lowercases scheme/host, drops the fragment and tracking query params, and
    strips a trailing slash. Two URLs that differ only in tracking junk
    canonicalize to the same string, so :func:`news_slug` is stable.
    """
    parts = urlsplit(url.strip())
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not any(k.lower().startswith(p) for p in _TRACKING_PREFIXES)
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def news_slug(url: str) -> str:
    """Deterministic slug for a ``news_article`` page = hash of the canonical URL.

    Re-ingesting the same article URL always yields the same slug, so the
    repository ``upsert`` is naturally idempotent.
    """
    digest = hashlib.sha1(canonicalize_url(url).encode("utf-8")).hexdigest()
    return f"news-{digest[:16]}"
