"""Convert summary markdown into a Lexical editor state, which is what 方格子 stores.

vocus's editor is Lexical, and its API takes the article body as a serialized editor
state (``lexicalObj.root.children[]``) — not HTML and not markdown. So syndicating there
means building that tree ourselves.

Scope is deliberately the subset the content pipeline actually emits (see
``pipelines/.../nodes/markdown_transform.py``): ``#``/``##``/``###`` headings, paragraphs,
bullet and ordered lists, blockquotes, horizontal rules, and inline bold / italic / links.
No tables, no images, no code blocks — the pipeline does not write them, and a converter
for constructs that never arrive is a liability, not a feature. Anything unrecognised
falls through as paragraph text rather than being dropped, so a future pipeline change
degrades to plain prose instead of losing content silently.

⚠️ Unverified against a live vocus round-trip: these are standard Lexical node shapes.
If vocus registered custom nodes, it may drop what it does not recognise. Publish one
draft and open it in their editor before trusting this with real articles.
"""

from __future__ import annotations

import re
from typing import Any

# Lexical's inline format bitmask.
FORMAT_BOLD = 1
FORMAT_ITALIC = 2

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^\s*[-*+]\s+(.*)$")
_ORDERED = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")
_QUOTE = re.compile(r"^>\s?(.*)$")
_HR = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")

# Inline: links first (their label may itself contain emphasis), then emphasis.
_LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
_STRONG = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_EM = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)|(?<!_)_([^_]+)_(?!_)")


def _text_node(text: str, fmt: int = 0) -> dict[str, Any]:
    return {
        "detail": 0,
        "format": fmt,
        "mode": "normal",
        "style": "",
        "text": text,
        "type": "text",
        "version": 1,
    }


def _block(node_type: str, children: list[dict], **extra: Any) -> dict[str, Any]:
    return {
        "children": children,
        "direction": "ltr",
        "format": "",
        "indent": 0,
        "type": node_type,
        "version": 1,
        **extra,
    }


def _emphasis_nodes(text: str, base_fmt: int = 0) -> list[dict]:
    """Split a run of plain text into bold/italic text nodes."""
    if not text:
        return []
    m = _STRONG.search(text)
    if m:
        inner = m.group(1) if m.group(1) is not None else m.group(2)
        return [
            *_emphasis_nodes(text[: m.start()], base_fmt),
            *_emphasis_nodes(inner, base_fmt | FORMAT_BOLD),
            *_emphasis_nodes(text[m.end():], base_fmt),
        ]
    m = _EM.search(text)
    if m:
        inner = m.group(1) if m.group(1) is not None else m.group(2)
        return [
            *_emphasis_nodes(text[: m.start()], base_fmt),
            *_emphasis_nodes(inner, base_fmt | FORMAT_ITALIC),
            *_emphasis_nodes(text[m.end():], base_fmt),
        ]
    return [_text_node(text, base_fmt)]


def inline_nodes(text: str) -> list[dict]:
    """Markdown inline syntax -> Lexical text and link nodes."""
    nodes: list[dict] = []
    pos = 0
    for m in _LINK.finditer(text):
        nodes.extend(_emphasis_nodes(text[pos:m.start()]))
        label, url = m.group(1), m.group(2)
        nodes.append(
            _block(
                "link",
                _emphasis_nodes(label) or [_text_node(url)],
                rel="noreferrer",
                target="_blank",
                title=None,
                url=url,
            )
        )
        pos = m.end()
    nodes.extend(_emphasis_nodes(text[pos:]))
    return nodes or [_text_node("")]


def _list_block(items: list[str], ordered: bool) -> dict[str, Any]:
    children = [
        _block("listitem", inline_nodes(item), value=i + 1)
        for i, item in enumerate(items)
    ]
    return _block(
        "list",
        children,
        listType="number" if ordered else "bullet",
        start=1,
        tag="ol" if ordered else "ul",
    )


def markdown_to_lexical(markdown: str) -> dict[str, Any]:
    """Build the ``{"root": ...}`` editor state vocus's API expects."""
    blocks: list[dict] = []
    lines = (markdown or "").replace("\r\n", "\n").split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        if not line.strip():
            i += 1
            continue

        if _HR.match(line):
            blocks.append({"type": "horizontalrule", "version": 1})
            i += 1
            continue

        m = _HEADING.match(line)
        if m:
            # h1 becomes h2: the article title is already rendered by vocus above the
            # body, so a second h1 inside it would be a duplicate top-level heading.
            level = min(max(len(m.group(1)), 1), 6)
            tag = f"h{min(level + 1, 6)}"
            blocks.append(_block("heading", inline_nodes(m.group(2).strip()), tag=tag))
            i += 1
            continue

        if _BULLET.match(line) or _ORDERED.match(line):
            ordered = bool(_ORDERED.match(line))
            items: list[str] = []
            while i < len(lines):
                bm = _ORDERED.match(lines[i]) if ordered else _BULLET.match(lines[i])
                if not bm:
                    break
                items.append((bm.group(2) if ordered else bm.group(1)).strip())
                i += 1
            blocks.append(_list_block(items, ordered))
            continue

        if _QUOTE.match(line):
            quoted: list[str] = []
            while i < len(lines) and _QUOTE.match(lines[i]):
                quoted.append(_QUOTE.match(lines[i]).group(1).strip())
                i += 1
            blocks.append(_block("quote", inline_nodes(" ".join(quoted).strip())))
            continue

        # Paragraph: consume until a blank line or the start of another block.
        para: list[str] = []
        while i < len(lines) and lines[i].strip():
            nxt = lines[i]
            if para and (_HEADING.match(nxt) or _BULLET.match(nxt) or _ORDERED.match(nxt)
                         or _QUOTE.match(nxt) or _HR.match(nxt)):
                break
            para.append(nxt.strip())
            i += 1
        blocks.append(_block("paragraph", inline_nodes(" ".join(para)), textFormat=0))

    if not blocks:
        blocks = [_block("paragraph", [_text_node("")], textFormat=0)]

    return {"root": _block("root", blocks)}
