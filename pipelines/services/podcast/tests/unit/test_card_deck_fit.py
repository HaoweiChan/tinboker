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
