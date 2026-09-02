"""Auto-fit tier selection for theme cards (card_deck._theme_fit_suffix).

The deck is a fixed 1080² canvas; dense cards must shrink to FIT rather than clip or
overlap the watermark. These lock the tier thresholds + that the chosen class is
emitted into the slide markdown.
"""
from podcast.content_builder import card_deck as cd


def test_short_card_uses_default_tier():
    assert cd._theme_fit_suffix("短主題", ["一句話。", "第二句。", "第三句。"]) == ""


def test_denser_card_picks_smaller_tier():
    short = cd._theme_fit_suffix("標題", ["短重點一。", "短重點二。"])
    dense = cd._theme_fit_suffix("標題", ["很長的重點" * 12, "另一個很長的重點" * 12, "第三個很長的重點" * 12])
    assert short == ""
    assert dense in {"fit-s", "fit-xs", "fit-xxs"}
    # more text => not a larger tier than a short card
    assert cd._THEME_TIERS[[t[0] for t in cd._THEME_TIERS].index(dense)][1] <= 37


def test_fit_class_is_emitted_in_slide_markdown():
    card = {"kind": "theme", "title": "標題", "bullets": ["重點" * 60, "重點" * 60, "重點" * 60]}
    md = cd._theme_slide(card)
    assert md.startswith("<!-- _class: theme ")
    assert any(s in md for s in ("fit-s", "fit-xs", "fit-xxs"))


def test_tiers_match_css():
    # Every non-default tier must have a matching `section.theme.<suffix>` CSS rule,
    # or the chosen class would do nothing at render time.
    for suffix, *_ in cd._THEME_TIERS:
        if suffix:
            assert f"section.theme.{suffix} li" in cd.CARD_THEME_CSS


def test_cover_renders_show_name_and_episode_subtitle():
    md = cd._cover_slide(
        {"kind": "cover", "title": "股癌", "subtitle": "2026/6/27 蘋果漲價潮", "bullets": ["重點一", "重點二"]},
        show_name="財經一路發", date_str="2026.06.27",
    )
    assert "# 財經一路發" in md                              # H1 = deterministic show name
    assert '<div class="subtitle">2026/6/27 蘋果漲價潮</div>' in md  # episode title as subtitle
    assert "股癌" not in md                                  # never echo the hallucinated marp title


def test_cover_without_subtitle_omits_div():
    md = cd._cover_slide({"kind": "cover", "subtitle": "", "bullets": []}, show_name="某節目", date_str="")
    assert 'class="subtitle"' not in md


# --- Cover auto-fit -----------------------------------------------------------------
# The cover had no fit logic at all: the episode subtitle and the hook are both
# unbounded (feed title, three joined insights), so a long episode overflowed the
# 864px content box and the flex layout squeezed .subtitle until overflow:hidden
# sliced it through the middle of a glyph row. 55 of 83 recent covers did this.


def test_short_cover_stays_full_size():
    assert cd._cover_fit_suffix("股癌", "2026/6/27 蘋果漲價潮", "重點一，重點二。") == ""


def test_long_cover_shrinks():
    suffix = cd._cover_fit_suffix(
        "兆華與股惑仔",
        "EP1173｜華許說完讓升息機率大增，9月魔咒能破嗎？MSCI拉尾，Q4還有做夢行情！"
        "欣興賣不掉怎辦，盤點各利空該有的跌幅？ft.題材獵人 林漢偉",
        # the real hook: three key insights joined, as _cover_slide builds it
        "欣興電子遭搜索，財務面合理跌幅約20%，但若涉洗產地恐引發美方制裁與法人永久性賣壓，"
        "聯準會主席華許刻意不給前瞻指引，政策不確定性將持續壓抑科技股與成長股評價，"
        "MSCI意外調升台股三項權重，被動資金尾盤大舉進場，顯示國際資金對台股配置需求強勁。",
    )
    assert suffix in {"fit-s", "fit-xs", "fit-xxs"}


def test_cover_fit_is_monotonic_in_content_volume():
    order = [t[0] for t in cd._COVER_TIERS]
    small = cd._cover_fit_suffix("節目", "短標題", "短鉤子。")
    big = cd._cover_fit_suffix("節目", "長標題" * 30, "很長的鉤子" * 40)
    assert order.index(big) >= order.index(small)


def test_cover_fit_class_is_emitted_in_slide_markdown():
    card = {"kind": "cover", "subtitle": "長標題" * 30, "bullets": ["重點" * 40] * 3}
    md = cd._cover_slide(card, "兆華與股惑仔", "2026.08.31")
    assert md.startswith("<!-- _class: cover ")
    assert any(s in md for s in ("fit-s", "fit-xs", "fit-xxs"))


def test_cover_tiers_match_css():
    for suffix, *_ in cd._COVER_TIERS:
        if suffix:
            assert f"section.cover.{suffix} .subtitle" in cd.CARD_THEME_CSS


def test_cover_children_never_shrink():
    """The squeeze is what clipped mid-glyph; the tiers only work if it stays off."""
    assert "section.cover > * { flex: 0 0 auto; }" in cd.CARD_THEME_CSS


# --- Cover title provenance ----------------------------------------------------------


def test_cover_card_title_is_the_show_name_not_the_llm_deck_title():
    """marp_writer hallucinates a famous show; the stored card must not repeat it.

    13 of 83 recent covers had "股癌" stored as the title on episodes belonging to six
    other podcasts. The render always overrode it, so nothing user-facing broke — but a
    field named `title` that quietly lies is a trap for the next consumer.
    """
    from podcast.content_builder.nodes.social_cards_builder import cards_from_marp_slides

    cards = cards_from_marp_slides(
        {"title": "股癌 EP1172｜輝達破除魔咒", "slides": []},
        ["重點一"],
        "EP1172｜輝達破除魔咒，台股創反彈新高！",
        show_name="兆華與股惑仔",
    )
    assert cards[0]["kind"] == "cover"
    assert cards[0]["title"] == "兆華與股惑仔"
    assert "股癌" not in cards[0]["title"]


def test_cover_card_title_falls_back_to_episode_title_without_a_show_name():
    from podcast.content_builder.nodes.social_cards_builder import cards_from_marp_slides

    cards = cards_from_marp_slides({"title": "股癌 EP9", "slides": []}, [], "EP9 標題")
    assert cards[0]["title"] == "EP9 標題"
