"""Marker rewriting + Lexical conversion for off-site syndication.

The marker cases here deliberately mirror ``frontend/scripts/validate-syndication.ts``.
Both implementations parse the same grammar, so if one is changed without the other, one
of the two checks fails.
"""

import pytest

from src.services.syndication_markdown import (
    format_timestamp,
    rewrite_markers,
    to_syndication_markdown,
)
from src.services.vocus_lexical import FORMAT_BOLD, markdown_to_lexical

SITE = "https://tinboker.com"


def rw(md: str) -> str:
    return rewrite_markers(md, SITE)


# ── markers ──────────────────────────────────────────────────────────────────
# Note the missing spaces around links: the CJK spacing cleanup strips the pipeline's
# ASCII padding when both sides are Chinese, exactly as the on-site renderer does.

def test_ticker_marker_becomes_absolute_url():
    assert rw("看好 [台積電](#ticker:2330) 的表現") == f"看好[台積電]({SITE}/stock/2330)的表現"


def test_ticker_symbol_is_uppercased():
    assert rw("[輝達](#ticker:nvda) 財報") == f"[輝達]({SITE}/stock/NVDA)財報"


def test_tag_marker_becomes_absolute_url():
    assert rw("屬於 [半導體](#tag:semiconductor) 類股") == f"屬於[半導體]({SITE}/topics/semiconductor)類股"


def test_bare_timestamp_flattens_to_text():
    assert rw("這段講得好 (#time:754000)") == "這段講得好 (12:34)"
    assert rw("開場 (#time:0)") == "開場 (0:00)"


def test_linked_timestamp_keeps_label_loses_dead_href():
    assert rw("已連結 [12:34](#time:754000) 的段落") == "已連結 12:34 的段落"


def test_placeholder_markers_are_dropped_not_rendered_as_zero():
    # Sub-second values are the legacy writer-LLM's ordinals, not real offsets.
    assert rw("假標記 (#time:3)") == "假標記"
    assert rw("假連結 [1](#time:3) 收掉") == "假連結收掉"


def test_no_in_house_marker_survives_into_a_public_post():
    sample = "\n".join([
        "# 本集重點",
        "",
        "[台積電](#ticker:2330) 在 [半導體](#tag:semiconductor) 的地位 (#time:754000)。",
        "",
        "- 重點一 [聯發科](#ticker:2454)",
    ])
    out = to_syndication_markdown(sample, "ep677", SITE)
    for marker in ("#ticker:", "#tag:", "#time:"):
        assert marker not in out, f"{marker} leaked into the syndicated copy"
    assert f"{SITE}/episode/ep677" in out
    assert "# 本集重點" in out


@pytest.mark.parametrize("ms,expected", [(0, "0:00"), (59_000, "0:59"), (3_600_000, "1:00:00"), (3_754_000, "1:02:34")])
def test_timestamp_formatting(ms, expected):
    assert format_timestamp(ms) == expected


def test_blank_summary_yields_nothing_not_a_lone_attribution_line():
    assert rw("") == ""
    assert to_syndication_markdown("   ", "ep1", SITE) == ""


# ── Lexical conversion ───────────────────────────────────────────────────────

def _kids(state):
    return state["root"]["children"]


def test_headings_shift_down_one_level():
    # vocus renders the article title itself, so a body h1 would duplicate it.
    kids = _kids(markdown_to_lexical("# 標題\n\n## 章節\n\n### 小節"))
    assert [(k["type"], k["tag"]) for k in kids] == [("heading", "h2"), ("heading", "h3"), ("heading", "h4")]


def test_paragraph_and_bold():
    kids = _kids(markdown_to_lexical("這是 **重點** 內容"))
    assert kids[0]["type"] == "paragraph"
    bolded = [c for c in kids[0]["children"] if c.get("format") == FORMAT_BOLD]
    assert [b["text"] for b in bolded] == ["重點"]


def test_links_become_link_nodes_carrying_the_url():
    kids = _kids(markdown_to_lexical(f"看 [台積電]({SITE}/stock/2330) 表現"))
    links = [c for c in kids[0]["children"] if c["type"] == "link"]
    assert len(links) == 1
    assert links[0]["url"] == f"{SITE}/stock/2330"
    assert links[0]["children"][0]["text"] == "台積電"


def test_bullet_and_ordered_lists():
    bullets = _kids(markdown_to_lexical("- 一\n- 二"))[0]
    assert bullets["type"] == "list" and bullets["listType"] == "bullet"
    assert len(bullets["children"]) == 2

    ordered = _kids(markdown_to_lexical("1. 一\n2. 二"))[0]
    assert ordered["listType"] == "number"
    assert [c["value"] for c in ordered["children"]] == [1, 2]


def test_quote_and_horizontal_rule():
    kids = _kids(markdown_to_lexical("> 引用一句\n\n---"))
    assert kids[0]["type"] == "quote"
    assert kids[1]["type"] == "horizontalrule"


def test_a_block_start_terminates_the_preceding_paragraph():
    kids = _kids(markdown_to_lexical("一段話\n## 接著是標題"))
    assert [k["type"] for k in kids] == ["paragraph", "heading"]


def test_empty_markdown_still_produces_a_valid_root():
    state = markdown_to_lexical("")
    assert state["root"]["type"] == "root"
    assert _kids(state)[0]["type"] == "paragraph"


def test_full_pipeline_shape_survives_end_to_end():
    md = to_syndication_markdown(
        "# 本集重點\n\n看好 [台積電](#ticker:2330) (#time:754000)。\n\n- 一\n- 二",
        "ep677",
        SITE,
    )
    kids = _kids(markdown_to_lexical(md))
    types = [k["type"] for k in kids]
    assert "heading" in types and "list" in types
    # The attribution line's episode permalink must arrive as a real link node.
    urls = [c["url"] for k in kids for c in k.get("children", []) if c.get("type") == "link"]
    assert f"{SITE}/episode/ep677" in urls
