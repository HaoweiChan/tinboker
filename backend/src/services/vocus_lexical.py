"""Neutral markdown blocks -> the Lexical editor state vocus's API stores.

Node shapes here are load-bearing and were confirmed by a live publish that rendered
correctly on vocus.cc; tests/unit/test_markdown_blocks.py pins the exact output.
"""
from __future__ import annotations

from typing import Any

from src.services.markdown_blocks import Block, Span, parse_blocks

FORMAT_BOLD = 1
FORMAT_ITALIC = 2


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


def _span_node(span: Span) -> dict[str, Any]:
    fmt = (FORMAT_BOLD if span.bold else 0) | (FORMAT_ITALIC if span.italic else 0)
    return _text_node(span.text, fmt)


def _inline_nodes(spans: list[Span]) -> list[dict]:
    """Spans -> text nodes, with consecutive same-href spans folded into one link node."""
    nodes: list[dict] = []
    run: list[Span] = []

    def flush() -> None:
        if run:
            nodes.append(_block("link", [_span_node(s) for s in run],
                                rel="noreferrer", target="_blank", title=None, url=run[0].href))
            run.clear()

    for span in spans:
        if span.href:
            if run and run[0].href != span.href:
                flush()
            run.append(span)
            continue
        flush()
        nodes.append(_span_node(span))
    flush()
    return nodes or [_text_node("")]


def _render(block: Block) -> dict[str, Any]:
    if block.kind == "hr":
        return {"type": "horizontalrule", "version": 1}
    if block.kind == "heading":
        # Every heading shifts down one level, not just h1: vocus renders the article
        # title above the body, so the body must not contain an h1, and shifting the
        # whole hierarchy keeps the relative structure instead of flattening it.
        return _block("heading", _inline_nodes(block.spans), tag=f"h{min(block.level + 1, 6)}")
    if block.kind == "list":
        children = [_block("listitem", _inline_nodes(item), value=i + 1)
                    for i, item in enumerate(block.items)]
        return _block("list", children, listType="number" if block.ordered else "bullet",
                      start=1, tag="ol" if block.ordered else "ul")
    if block.kind == "quote":
        return _block("quote", _inline_nodes(block.spans))
    return _block("paragraph", _inline_nodes(block.spans), textFormat=0)


def markdown_to_lexical(markdown: str) -> dict[str, Any]:
    """Build the ``{"root": ...}`` editor state vocus's API expects."""
    blocks = [_render(b) for b in parse_blocks(markdown)]
    if not blocks:
        blocks = [_block("paragraph", [_text_node("")], textFormat=0)]
    return {"root": _block("root", blocks)}
