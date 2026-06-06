"""Step 3 — hybrid article extraction.

Per the design plan: trafilatura full-page extract into paragraphs (each with a
stable sha1 hash); fall back to the RSS ``content:encoded`` / ``summary`` when
the page is unreachable or yields nothing. Both the page fetch and the
trafilatura call are injectable so tests run offline.
"""

from __future__ import annotations

import hashlib
import html as _html
import re
from typing import Callable

from ..article import Article, Paragraph

_SECTION_SPLIT = re.compile(r"\n\s*\n+")
_MIN_PARAGRAPH_LEN = 20  # drop nav scraps / one-word lines


def paragraph_hash(text: str) -> str:
    """Stable sha1 (16 hex chars) of a paragraph's normalized text."""
    return hashlib.sha1(text.strip().encode("utf-8")).hexdigest()[:16]


def split_paragraphs(text: str) -> list[Paragraph]:
    """Split extracted plain text into indexed, hashed paragraphs."""
    if not text:
        return []
    paragraphs: list[Paragraph] = []
    for chunk in _SECTION_SPLIT.split(text.strip()):
        cleaned = " ".join(chunk.split())
        if len(cleaned) < _MIN_PARAGRAPH_LEN:
            continue
        paragraphs.append(
            Paragraph(index=len(paragraphs), hash=paragraph_hash(cleaned), text=cleaned)
        )
    return paragraphs


def strip_html(markup: str) -> str:
    """Minimal HTML→text for the RSS fallback (RSS bodies are small + simple)."""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", markup, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return _html.unescape(text)


def _default_fetch(url: str) -> str | None:
    import trafilatura

    return trafilatura.fetch_url(url)


def _default_extract(downloaded: str) -> str | None:
    import trafilatura

    return trafilatura.extract(downloaded, include_comments=False, include_tables=False)


def extract(
    article: Article,
    *,
    fetch: Callable[[str], str | None] | None = None,
    extractor: Callable[[str], str | None] | None = None,
) -> Article:
    """Populate ``article.paragraphs`` and ``article.content_hash`` in place."""
    fetch = fetch or _default_fetch
    extractor = extractor or _default_extract
    main_text = ""
    try:
        downloaded = fetch(article.url)
    except Exception as exc:  # noqa: BLE001 — network failure → RSS fallback below
        print(f"  ⚠ page fetch failed ({article.url}): {exc}")
        downloaded = None

    if downloaded:
        try:
            main_text = extractor(downloaded) or ""
        except Exception as exc:  # noqa: BLE001 — extractor failure → RSS fallback below
            print(f"  ⚠ extraction failed ({article.url}): {exc}")
            main_text = ""

    if not main_text.strip():
        rss_body = article.rss_content or article.rss_summary
        main_text = strip_html(rss_body) if rss_body else ""

    article.paragraphs = split_paragraphs(main_text)
    joined = "\n".join(p.text for p in article.paragraphs)
    article.content_hash = hashlib.sha1(joined.encode("utf-8")).hexdigest()
    return article
