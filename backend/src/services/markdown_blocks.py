"""Markdown -> neutral blocks and inline spans.

Both syndication targets need the same reading of the same markdown and differ only in
the JSON they emit: vocus wants Lexical, Substack wants ProseMirror. Parsing it twice
would mean two parsers drifting apart on exactly the details summary quality rides on —
ticker/tag links and heading levels — so the parse lives here and the platform modules
are thin renderers over it.

Deliberately not a full CommonMark implementation: the input is our own generated summary
markdown, which uses a fixed and small subset. Reach for a real parser only if that stops
being true.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^\s*[-*+]\s+(.*)$")
_ORDERED = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")
_QUOTE = re.compile(r"^>\s?(.*)$")
_HR = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
_STRONG = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_EM = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)|(?<!_)_([^_]+)_(?!_)")


@dataclass(frozen=True)
class Span:
    """A run of text sharing one set of inline marks."""

    text: str
    bold: bool = False
    italic: bool = False
    href: str | None = None


@dataclass(frozen=True)
class Block:
    kind: str  # heading | paragraph | quote | list | hr
    spans: list[Span] = field(default_factory=list)
    level: int = 0  # heading only
    ordered: bool = False  # list only
    items: list[list[Span]] = field(default_factory=list)  # list only


def _emphasis(text: str, bold: bool = False, italic: bool = False) -> list[Span]:
    if not text:
        return []
    for pattern, flag in ((_STRONG, "bold"), (_EM, "italic")):
        m = pattern.search(text)
        if m:
            inner = m.group(1) if m.group(1) is not None else m.group(2)
            marks = {"bold": bold, "italic": italic} | {flag: True}
            return [
                *_emphasis(text[: m.start()], bold, italic),
                *_emphasis(inner, **marks),
                *_emphasis(text[m.end():], bold, italic),
            ]
    return [Span(text, bold, italic)]


def inline_spans(text: str) -> list[Span]:
    """Inline markdown -> spans. Links win over emphasis; emphasis nests inside a label."""
    spans: list[Span] = []
    pos = 0
    for m in _LINK.finditer(text):
        spans.extend(_emphasis(text[pos:m.start()]))
        label, url = m.group(1), m.group(2)
        inner = _emphasis(label) or [Span(url)]
        spans.extend(Span(s.text, s.bold, s.italic, url) for s in inner)
        pos = m.end()
    spans.extend(_emphasis(text[pos:]))
    return spans or [Span("")]


def parse_blocks(markdown: str) -> list[Block]:
    blocks: list[Block] = []
    lines = (markdown or "").replace("\r\n", "\n").split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        if not line.strip():
            i += 1
            continue

        if _HR.match(line):
            blocks.append(Block("hr"))
            i += 1
            continue

        m = _HEADING.match(line)
        if m:
            blocks.append(Block("heading", inline_spans(m.group(2).strip()),
                                level=min(max(len(m.group(1)), 1), 6)))
            i += 1
            continue

        if _BULLET.match(line) or _ORDERED.match(line):
            ordered = bool(_ORDERED.match(line))
            items: list[list[Span]] = []
            while i < len(lines):
                bm = _ORDERED.match(lines[i]) if ordered else _BULLET.match(lines[i])
                if not bm:
                    break
                items.append(inline_spans((bm.group(2) if ordered else bm.group(1)).strip()))
                i += 1
            blocks.append(Block("list", ordered=ordered, items=items))
            continue

        if _QUOTE.match(line):
            quoted: list[str] = []
            while i < len(lines) and _QUOTE.match(lines[i]):
                quoted.append(_QUOTE.match(lines[i]).group(1).strip())
                i += 1
            blocks.append(Block("quote", inline_spans(" ".join(quoted).strip())))
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
        blocks.append(Block("paragraph", inline_spans(" ".join(para))))

    return blocks
