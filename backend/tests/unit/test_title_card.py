"""Words-only cover: wraps by measured width, shrinks to fit, escapes the text."""

from src.services import title_card as tc


def test_wrap_breaks_at_punctuation_when_one_is_near_the_edge():
    lines = tc.wrap("記憶體全面漲價創高，為何各家節目結論卻走向分歧？", 72, 700)
    assert lines[0] == "記憶體全面漲價創高，" and "".join(lines) == "記憶體全面漲價創高，為何各家節目結論卻走向分歧？"
    assert not any(line[0] in tc._PUNCT for line in lines)


def test_card_shrinks_rather_than_overflowing_and_escapes():
    svg = tc.title_card_svg("A & B " * 20, kicker="聽播客週報 Pro 2026-W37")
    assert "&amp;" in svg and "聽播客週報 Pro 2026-W37" in svg and "A & B" not in svg
    assert svg.count("<text") <= tc._MAX_LINES + 3


def test_payload_round_trips_and_rejects_garbage():
    import pytest
    p = tc.encode("記憶體全面漲價創高，為何各家節目結論卻走向分歧？", "聽播客週報 Pro 2026-W37")
    assert "=" not in p and tc.decode(p) == ("記憶體全面漲價創高，為何各家節目結論卻走向分歧？", "聽播客週報 Pro 2026-W37")
    with pytest.raises(ValueError):
        tc.decode("bm90anNvbg")
