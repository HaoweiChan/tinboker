"""Derive ``WikiLink`` edges from a page's body and frontmatter.

Links are a *projection* of page content, never a separate input. On every
upsert the repository calls :func:`extract_links` and rewrites the edge rows for
that source page, so the link table is always consistent with page content.
"""

from __future__ import annotations

import re
from typing import Any

from .models import DIR_TO_KIND, WikiLink
from .slugify import slugify, ticker_slug

# [[prefix/target]] or [[prefix/target|label]]
_LINK_RE = re.compile(r"\[\[([A-Za-z_-]+)/([^\]|]+?)(?:\|[^\]]*)?\]\]")
# trailing "— context" / "- context" after a link on the same line
_CONTEXT_RE = re.compile(r"^\s*[—\-–:]\s*(.+?)\s*$")


def extract_links(
    src_kind: str,
    src_slug: str,
    body: str,
    frontmatter: dict[str, Any] | None = None,
) -> list[WikiLink]:
    """Return the de-duplicated outgoing links for a page."""
    frontmatter = frontmatter or {}
    found: dict[tuple[str, str], WikiLink] = {}

    for line in body.splitlines():
        for m in _LINK_RE.finditer(line):
            dst_kind = DIR_TO_KIND.get(m.group(1).lower())
            if not dst_kind:
                continue
            dst_slug = m.group(2).strip()
            if not dst_slug:
                continue
            context = ""
            cm = _CONTEXT_RE.match(line[m.end():])
            if cm:
                context = cm.group(1).strip()
            key = (dst_kind, dst_slug)
            if key not in found:
                found[key] = WikiLink(src_kind, src_slug, dst_kind, dst_slug, context)

    # Episode + news_article frontmatter carries the canonical ticker / tag membership.
    if src_kind in ("episode", "news_article"):
        for ticker in frontmatter.get("tickers", []) or []:
            key = ("entity", ticker_slug(str(ticker)))
            found.setdefault(key, WikiLink(src_kind, src_slug, *key, ""))
        for tag in frontmatter.get("tags", []) or []:
            key = ("topic", slugify(str(tag)))
            found.setdefault(key, WikiLink(src_kind, src_slug, *key, ""))

    return list(found.values())
