"""The weekly podcast-mention recap card."""
import re

import pytest

from src.services.card_theme import DOWN, UP
from src.services.weekly_card import (
    MIN_MENTIONS, _fit, _fmt_week, movers_card_svg, short_name, theme_rows, ticker_rows,
)


def _row(ticker, name, n, prev, bull=0, bear=0, casts=3):
    return {"ticker": ticker, "name": name, "n": n, "prev": prev,
            "bull": bull, "bear": bear, "casts": casts}


def _data(rows=None):
    return {"title": "本週聲量竄升", "subtitle": "增幅最大的標的",
            "caption": "本週全市場提及 346 次",
            "week_start": "2026-08-31", "week_end": "2026-09-06",
            "rows": ticker_rows(rows if rows is not None else [
                _row("2454", "聯發科", 15, 8, bull=10, casts=6),
                _row("TSLA", "特斯拉", 8, 2, bull=2, casts=4),
                _row("DELL", "戴爾", 5, 0, bull=4, casts=3)])}


def test_thin_weeks_are_dropped_not_drawn():
    """A jump from 1 to 4 is noise; the card must not present it as a trend."""
    svg = movers_card_svg(_data([_row("AAA", "甲", 4, 1), _row("BBB", "乙", 9, 3)]))
    assert "乙" in svg and "甲" not in svg


def test_a_week_with_nothing_above_the_floor_is_an_error_not_an_empty_card():
    with pytest.raises(ValueError):
        movers_card_svg(_data([_row("AAA", "甲", MIN_MENTIONS - 1, 0)]))
    with pytest.raises(ValueError):
        movers_card_svg(_data([]))


def test_the_headline_carries_this_weeks_count_and_the_change_together():
    """Both numbers on the identity line, so the ranking reads down one edge."""
    svg = movers_card_svg(_data())
    assert "15 次" in svg and "+7" in svg


def test_the_change_outweighs_the_total_because_it_is_the_ranking_criterion():
    svg = movers_card_svg(_data())
    delta = next(ln for ln in svg.splitlines() if ">+7<" in ln)
    total = next(ln for ln in svg.splitlines() if ">15 次<" in ln)
    assert 'font-size="44"' in delta and 'font-size="22"' in total


def test_the_benchmark_marker_states_its_value_rather_than_being_decoration():
    """An unlabelled hairline reads as ornament; the bullet chart needs it to read as
    last week's number."""
    svg = movers_card_svg(_data())
    assert "上週 8" in svg and 'stroke-width="5"' in svg


def test_last_week_is_the_benchmark_line_not_a_segment_of_the_bar():
    """One channel, one meaning: bar length is this week; last week is a marker.

    The earlier version stacked last-week and sentiment into the bar, which read as
    though the segments summed to the week's total. They do not.
    """
    svg = movers_card_svg(_data())
    assert "上週 8" in svg      # stated by the marker, not repeated in the caption
    assert svg.count("<line") >= 3          # a marker per row with a previous week
    # the quantity bar carries no sentiment colour
    bars = [ln for ln in svg.splitlines() if "<rect" in ln and 'height="26"' in ln]
    assert bars and not any(UP in b or DOWN in b for b in bars)


def test_a_loud_week_with_no_bulls_still_shows_its_sentiment_split():
    """Lots of talk and nobody bullish is the story, so it cannot be rounded away."""
    svg = movers_card_svg(_data([_row("TSLA", "特斯拉", 16, 2, bull=0, bear=0)]))
    assert "多 0" in svg and "中性 16" in svg and "空 0" in svg


def test_a_ticker_that_was_silent_last_week_gets_no_benchmark_marker():
    """A marker at zero would sit on the axis and read as a bar of length zero."""
    only = movers_card_svg(_data([_row("DELL", "戴爾", 6, 0, bull=4)]))
    # "上週" alone would match the subtitle ("較上週增幅最大"); the marker label is
    # what must be absent, along with the tick it annotates.
    assert "上週 0" not in only
    assert only.count("<line") == 1      # the header rule, and no benchmark marker
    assert 'stroke-width="5"' not in only


def test_a_lowercase_alias_beats_a_long_legal_name():
    """SPCX is stored as "Space Exploration Technologies" with an alias of "SpaceX"."""
    assert short_name("", "Space Exploration Technologies", ["SpaceX"]) == "SpaceX"


def test_a_ticker_shaped_alias_is_not_mistaken_for_a_name():
    """GOOGL carries the alias "GOOG" — a second symbol, not something anyone says."""
    assert short_name("谷歌", "Alphabet", ["GOOG"]) == "谷歌"
    assert short_name("", "Alphabet", ["GOOG"]) == "Alphabet"


def test_the_chinese_name_wins_when_there_is_one():
    assert short_name("聯發科", "MediaTek", None) == "聯發科"


def test_the_trim_is_a_last_resort_not_the_normal_path():
    """With the short name on its own 18px line, nothing common should be ellipsised."""
    for name in ("SpaceX", "聯發科", "Dell Technologies", "Advanced Micro Devices",
                 "台灣積體電路製造"):
        assert _fit(name, 18, 280) == name


def test_the_week_label_uses_an_ascii_hyphen():
    """The CJK face has no en dash; an en dash here rasterises as a tofu box."""
    assert _fmt_week("2026-08-31", "2026-09-06") == "08/31 - 09/06"


def test_every_glyph_on_the_card_is_one_a_cjk_font_actually_has():
    svg = movers_card_svg(_data())
    allowed = set(chr(c) for c in range(0x20, 0x7F)) | {"·", "…", "\n"}
    exotic = {
        ch for chunk in re.findall(r">([^<>]+)<", svg) for ch in chunk
        if ch not in allowed and not (0x3000 <= ord(ch) <= 0x9FFF)
        and not (0xFF00 <= ord(ch) <= 0xFFEF)
    }
    assert not exotic, f"glyphs a CJK face may lack: {sorted(exotic)}"



def test_a_theme_row_spends_the_sentiment_line_on_member_tickers():
    """Sector mentions carry no sentiment — it is extracted per ticker — so the theme
    card shows who is in the theme instead. "矽光子與 CPO" means little on its own."""
    rows = theme_rows([{"exposure_id": "sector_liquid_cooling", "name": "液冷散熱",
                        "n": 6, "prev": 4, "casts": 5, "member_count": 8,
                        "members": [{"ticker": "3324", "name": "雙鴻"},
                                    {"ticker": "3017", "name": "奇鋐"}]}])
    assert rows[0]["sentiment"] is None
    assert "3324 雙鴻" in rows[0]["meta"] and "成分股 8 檔" in rows[0]["meta"]


def test_the_card_ranks_its_own_rows_because_the_title_promises_a_ranking():
    """A theme fixture straight out of json_agg arrived unsorted and rendered
    +6, +2, +2, +5 down the page under the word 竄升."""
    scrambled = [{"label": "A", "n": 6, "prev": 4, "meta": ""},     # +2
                 {"label": "B", "n": 10, "prev": 4, "meta": ""},    # +6
                 {"label": "C", "n": 5, "prev": 0, "meta": ""}]     # +5
    svg = movers_card_svg({"title": "t", "subtitle": "s", "caption": "c",
                           "week_start": "2026-08-31", "week_end": "2026-09-06",
                           "rows": scrambled})
    assert svg.index(">B<") < svg.index(">C<") < svg.index(">A<")
