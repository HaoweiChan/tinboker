"""The markdown tokenizer, and the two renderers that consume it.

The golden test exists because vocus_lexical had no test at all: its only proof was a
live publish that rendered correctly on vocus.cc. Snapshotting that output first is what
makes it safe to pull the block/inline parsing out into a shared tokenizer — if the
refactor changes a single node, this fails.
"""
import json
import pathlib

from src.services.markdown_blocks import parse_blocks
from src.services.substack_prosemirror import markdown_to_prosemirror
from src.services.vocus_lexical import markdown_to_lexical

GOLDEN = json.loads(
    (pathlib.Path(__file__).parent.parent / "fixtures" / "lexical_golden.json").read_text(encoding="utf-8")
)


def test_lexical_output_is_unchanged_by_the_tokenizer_extraction():
    assert markdown_to_lexical(GOLDEN["markdown"]) == GOLDEN["lexical"]


def test_tokenizer_reads_every_block_kind():
    kinds = [b.kind for b in parse_blocks(GOLDEN["markdown"])]
    assert kinds == ["heading", "paragraph", "heading", "list", "list", "quote", "hr", "paragraph"]


def test_inline_marks_survive_into_spans():
    spans = parse_blocks("這是 **粗** 與 *斜* 與 [連](https://x.test)。")[0].spans
    assert [s.text for s in spans if s.bold] == ["粗"]
    assert [s.text for s in spans if s.italic] == ["斜"]
    assert [(s.text, s.href) for s in spans if s.href] == [("連", "https://x.test")]


def test_prosemirror_body_matches_what_substack_accepted():
    """Shapes verified against the live API: draft_body is a JSON *string* of a doc, and
    paragraphs carry attrs.textAlign. See substack_publisher for the rest of the contract."""
    doc = markdown_to_prosemirror("## 標題\n\n一段 **粗體**。\n\n- 甲\n- 乙\n")
    assert doc["type"] == "doc"
    assert doc["content"][0] == {
        "type": "heading",
        "attrs": {"level": 3, "textAlign": None},
        "content": [{"type": "text", "text": "標題"}],
    }
    para = doc["content"][1]
    assert para["attrs"] == {"textAlign": None}
    assert {"type": "text", "marks": [{"type": "strong"}], "text": "粗體"} in para["content"]
    assert doc["content"][2]["type"] == "bulletList"
    assert len(doc["content"][2]["content"]) == 2


def test_every_heading_shifts_down_one_level():
    """Both editors render the post title above the body, so the body must not contain an
    h1. The whole hierarchy shifts rather than only h1 collapsing, which keeps the
    relative structure intact. h6 stays h6 — there is nowhere further to go."""
    assert markdown_to_prosemirror("# 大標")["content"][0]["attrs"]["level"] == 2
    assert markdown_to_prosemirror("### 小標")["content"][0]["attrs"]["level"] == 4
    assert markdown_to_prosemirror("###### 最小")["content"][0]["attrs"]["level"] == 6
    assert markdown_to_lexical("# 大標")["root"]["children"][0]["tag"] == "h2"
    assert markdown_to_lexical("### 小標")["root"]["children"][0]["tag"] == "h4"


def test_empty_markdown_still_produces_a_valid_document():
    """Both APIs reject an empty content array."""
    assert markdown_to_prosemirror("")["content"]
    assert markdown_to_lexical("")["root"]["children"]


def test_a_pipe_table_becomes_one_list_item_per_row():
    md = (
        "| 節目 | 提及 | 命中 | 平均 |\n"
        "|---|---:|---:|---:|\n"
        "| 股癌 | 16 | 6/8 | +4.4% |\n"
        "| 財報狗 | 11 |  | -1.0% |\n"   # an empty cell is skipped, not printed as "命中 "
    )
    blocks = parse_blocks(md)
    assert [b.kind for b in blocks] == ["list"]
    rows = ["".join(s.text for s in item) for item in blocks[0].items]
    assert rows == ["股癌：提及 16、命中 6/8、平均 +4.4%", "財報狗：提及 11、平均 -1.0%"]


def test_a_table_renders_as_a_bullet_list_in_both_editors():
    md = "| a | b |\n|---|---|\n| **x** | 1 |\n\n後文"
    lex = markdown_to_lexical(md)["root"]["children"]
    assert [n["type"] for n in lex] == ["list", "paragraph"]
    assert lex[0]["children"][0]["children"][0]["format"] == 1  # bold survives inside the cell
    pm = markdown_to_prosemirror(md)["content"]
    assert [n["type"] for n in pm] == ["bulletList", "paragraph"]


def test_a_lone_pipe_line_is_still_a_paragraph():
    assert [b.kind for b in parse_blocks("| not a table |")] == ["paragraph"]
