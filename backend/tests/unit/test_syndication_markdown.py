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


# ── Naming the podcaster on syndicated copies ────────────────────────────────

def test_podcast_short_name_drops_the_latin_prefix_readers_do_not_use():
    """Every 股癌 summary on vocus is filed under 股癌, never "Gooaye 股癌"."""
    from src.services.syndication_markdown import podcast_short_name
    assert podcast_short_name("Gooaye 股癌") == "股癌"
    assert podcast_short_name("股癌") == "股癌"
    assert podcast_short_name("寶博士 Blockchain Daily") == "寶博士"


def test_a_latin_only_podcast_keeps_its_whole_name():
    from src.services.syndication_markdown import podcast_short_name
    assert podcast_short_name("Acquired") == "Acquired"
    assert podcast_short_name("") == ""


def test_syndication_title_leads_with_the_podcast_and_says_it_is_a_summary():
    """A tag page is a wall of episode numbers; a bare "EP684" says neither whose episode
    it is nor that this is a write-up rather than a repost."""
    from src.services.syndication_markdown import syndication_title
    assert syndication_title("Gooaye 股癌", "EP684 | 🔦") == "股癌 EP684 | 🔦 摘要"


def test_neither_the_podcast_name_nor_the_suffix_is_doubled():
    from src.services.syndication_markdown import syndication_title
    assert syndication_title("Gooaye 股癌", "股癌 EP684") == "股癌 EP684 摘要"
    assert syndication_title("Gooaye 股癌", "股癌 EP684 摘要") == "股癌 EP684 摘要"


def test_attribution_names_the_podcast_when_known():
    from src.services.syndication_markdown import attribution_markdown
    assert "《股癌》" in attribution_markdown("EP1", "https://tinboker.com", "Gooaye 股癌")


def test_attribution_stays_generic_when_the_podcast_is_unknown():
    """Publishers may be called without it; the line must still read as a sentence."""
    from src.services.syndication_markdown import attribution_markdown
    line = attribution_markdown("EP1", "https://tinboker.com")
    assert "《》" not in line and "podcast" in line


# ── Excerpt for the platforms' 摘要 / subtitle field ──────────────────────────

_SUMMARY = """# 從Situational Awareness爆倉看AI股多空反轉：市場降槓桿與投資哲學的再思考

近期台股、韓股與美股經歷了劇烈的下跌與反彈，市場普遍認為這是一次全市場的降槓桿事件。核心導火線指向知名對沖基金的爆倉。

## 第一段標題 (#time:587074)

內文第二段。
"""


def test_excerpt_takes_the_lead_paragraph_not_the_heading():
    from src.services.syndication_markdown import syndication_excerpt
    x = syndication_excerpt(_SUMMARY)
    assert x.startswith("近期台股")
    assert "從Situational" not in x   # the h1 is the title, not the excerpt


def test_excerpt_is_plain_text_with_markers_resolved_away():
    from src.services.syndication_markdown import syndication_excerpt
    x = syndication_excerpt("看好 [台積電](#ticker:2330) 與 **記憶體** (#time:754000)。")
    assert x == "看好 台積電 與 記憶體。"


def test_excerpt_cuts_on_a_sentence_boundary_when_it_can():
    from src.services.syndication_markdown import syndication_excerpt
    body = "第一句話寫得夠長所以句點落在後半段這裡結束。" + "第二句非常長" * 30
    x = syndication_excerpt(body, limit=40)
    assert len(x) <= 40
    assert x.endswith("。")


def test_a_sentence_break_too_early_is_ignored_in_favour_of_using_the_space():
    """Cutting at a full stop 7 characters in would throw away most of the budget, so a
    break in the first half of the window does not count."""
    from src.services.syndication_markdown import syndication_excerpt
    x = syndication_excerpt("短句。" + "後面很長的內容" * 30, limit=40)
    assert x.endswith("…")
    assert len(x) > 10


def test_excerpt_ellipsises_when_no_sentence_break_is_near():
    from src.services.syndication_markdown import syndication_excerpt
    x = syndication_excerpt("無句點的超長段落" * 30, limit=40)
    assert len(x) <= 40
    assert x.endswith("…")


def test_a_summary_with_only_headings_yields_no_excerpt():
    """Better an empty field than a heading masquerading as a lead."""
    from src.services.syndication_markdown import syndication_excerpt
    assert syndication_excerpt("# 只有標題\n\n## 還是標題\n") == ""


# ── structured off-site copy (2026-09-13) ─────────────────────────────────────
from datetime import date  # noqa: E402

from src.services.syndication_markdown import (  # noqa: E402
    build_syndication_body,
    episode_label,
    hook_title,
    is_historic,
    strip_boilerplate,
)

SUMMARY = (
    "# 從摺疊機信仰到AI地緣政治：市場信任、供應鏈博弈與投資策略全解析\n\n"
    "本文深入剖析[蘋果](#ticker:AAPL)摺疊機的市場潛力，並探討AI模型商品化趨勢。\n\n"
    "## 市場信任與信仰之爭 (#time:776242)\n\n"
    "近期市場上出現一種現象：[輝達](#ticker:NVDA)即便利多頻傳，股價仍能維持強勢。\n\n"
    "## 摺疊機的中國考驗 (#time:1500000)\n\n"
    "定價策略出乎意料。"
)
INSIGHTS = ["蘋果摺疊機iPhone Duo定價僅略高於Pro Max，遠低預期，將大幅刺激銷量", "甲骨文AI資料中心建置遇地方政治瓶頸"]


@pytest.mark.parametrize("title,label", [
    ("EP696 | 🎖️", "EP696"),
    ("Ep170｜人類還有幾集可以逃QQ", "EP170"),
    ("2026/9/11(五)油價破百 債券失火!", "2026/9/11"),
    ("中、日高精密工具機大混戰 2026.08.18", "2026.08.18"),
    ("沒有任何編號的一集標題會被截短到十二個字", "沒有任何編號的一集標題會"),
])
def test_episode_label(title, label):
    assert episode_label(title) == label


def test_hook_title_leads_with_the_first_key_insight_and_ends_with_show_and_label():
    t = hook_title("Gooaye 股癌", "EP696 | 🎖️", INSIGHTS, SUMMARY)
    assert t == "蘋果摺疊機iPhone Duo定價僅略高於Pro Max，遠低預期｜股癌 EP696"
    assert hook_title("Gooaye 股癌", "EP696 | 🎖️", INSIGHTS, SUMMARY, historic=True).startswith("【歷史回顧】")


def test_hook_title_falls_back_to_the_h1_without_its_generic_tail_then_to_legacy():
    assert hook_title("Gooaye 股癌", "EP696 | 🎖️", [], SUMMARY) == "從摺疊機信仰到AI地緣政治｜股癌 EP696"
    assert hook_title("Gooaye 股癌", "EP696 | 🎖️", [], "") == "股癌 EP696 | 🎖️ 摘要"


def test_strip_boilerplate_drops_h1_and_the_announcing_lead_but_keeps_sections():
    out = strip_boilerplate(SUMMARY)
    assert not out.startswith("# ") and "本文深入剖析" not in out
    assert out.startswith("## 市場信任與信仰之爭")
    assert "定價策略出乎意料。" in out
    # a real first paragraph is not a lead and survives
    assert strip_boilerplate("# 標題\n\n輝達這季的毛利率創新高。\n\n## 下一段").startswith("輝達這季")


def test_is_historic_uses_thirty_days_and_treats_unknown_as_old():
    fresh = int(date(2026, 9, 10).strftime("%s")) * 1000
    assert is_historic(fresh, date(2026, 9, 13)) is False
    assert is_historic(fresh, date(2026, 11, 1)) is True
    assert is_historic(None, date(2026, 9, 13)) is True


def test_body_sections_in_order_with_dates_no_markers_and_historic_note():
    old = int(date(2022, 1, 10).strftime("%s")) * 1000
    md = build_syndication_body(
        episode_id="ep1", podcast_name="Gooaye 股癌", episode_title="EP696 | 🎖️", summary=SUMMARY,
        key_insights=INSIGHTS, released_at_ms=old, ticker_lines=["台積電（2330）看多：「先進封裝吃緊」"],
        spotify_url="https://open.spotify.com/episode/x", site_url=SITE, synced_on=date(2026, 9, 13),
    )
    order = [md.index(s) for s in ("原節目：股癌 EP696 | 🎖️（2022-01-10 播出）・整理：2026-09-13",
                                   "> 本篇是 2022 年 1 月 播出節目的整理", "## 30 秒讀完", "## 這集講到的股票",
                                   "## 精選段落", "## 市場信任與信仰之爭", "## 適用範圍", "## 下一步")]
    assert order == sorted(order)
    assert "- 蘋果摺疊機iPhone Duo定價僅略高於Pro Max" in md and "- 台積電（2330）看多" in md
    assert "#ticker:" not in md and "#time:" not in md and "本文深入剖析" not in md
    assert f"{SITE}/stock/NVDA" in md and f"{SITE}/episode/ep1" in md and "open.spotify.com" in md
    assert "(12:56)" in md  # the section timestamp survives as text


def test_body_is_empty_when_there_is_nothing_to_say():
    assert build_syndication_body(episode_id="e", podcast_name="x", episode_title="t", summary="",
                                  key_insights=[], released_at_ms=None, synced_on=date(2026, 9, 13)) == ""
