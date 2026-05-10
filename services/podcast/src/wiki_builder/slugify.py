"""Slug generation utilities for wiki page filenames and IDs."""

import re
import unicodedata


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
