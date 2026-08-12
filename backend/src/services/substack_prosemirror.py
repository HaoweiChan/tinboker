"""Neutral markdown blocks -> the ProseMirror document Substack stores in draft_body.

Shapes confirmed against the live API by reading a draft Substack's own editor created:
paragraphs and headings carry ``attrs.textAlign``, and draft_body is the JSON *string* of
this document (substack_publisher does that encoding).
"""
from __future__ import annotations

from typing import Any

from src.services.markdown_blocks import Block, Span, parse_blocks


def _text(span: Span) -> dict[str, Any]:
    marks: list[dict[str, Any]] = []
    if span.bold:
        marks.append({"type": "strong"})
    if span.italic:
        marks.append({"type": "em"})
    if span.href:
        marks.append({"type": "link", "attrs": {"href": span.href}})
    node: dict[str, Any] = {"type": "text", "text": span.text}
    if marks:
        node["marks"] = marks
    return node


def _inline(spans: list[Span]) -> list[dict[str, Any]]:
    # ProseMirror rejects an empty text node, so drop blank spans entirely.
    return [_text(s) for s in spans if s.text]


def _para(spans: list[Span]) -> dict[str, Any]:
    node: dict[str, Any] = {"type": "paragraph", "attrs": {"textAlign": None}}
    content = _inline(spans)
    if content:
        node["content"] = content
    return node


def _render(block: Block) -> dict[str, Any]:
    if block.kind == "hr":
        return {"type": "horizontal_rule"}
    if block.kind == "heading":
        # Shifted down one level for the same reason as vocus: Substack renders the
        # post title above the body, so the body must not contain an h1.
        return {
            "type": "heading",
            "attrs": {"level": min(block.level + 1, 6), "textAlign": None},
            "content": _inline(block.spans),
        }
    if block.kind == "list":
        items = [{"type": "listItem", "content": [_para(item)]} for item in block.items]
        return {"type": "orderedList" if block.ordered else "bulletList", "content": items}
    if block.kind == "quote":
        return {"type": "blockquote", "content": [_para(block.spans)]}
    return _para(block.spans)


def markdown_to_prosemirror(markdown: str) -> dict[str, Any]:
    content = [_render(b) for b in parse_blocks(markdown)]
    if not content:
        content = [_para([])]
    return {"type": "doc", "content": content}
