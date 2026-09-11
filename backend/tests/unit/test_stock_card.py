"""The shareable stock card SVG."""
import re

import pytest

from src.services.stock_card import _volume_label, stock_card_svg


def _bars(n=120, start=100.0):
    """A rising series with one down day in the middle, so both candle colours appear."""
    out = []
    for i in range(n):
        close = start + i
        open_ = close - 1 if i != 5 else close + 1
        out.append({"date": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}",
                    "open": open_, "high": max(open_, close) + 2,
                    "low": min(open_, close) - 2, "close": close,
                    "volume": 1000 * (i + 1)})
    return out


def _stock(**over):
    base = {"ticker": "2330", "name": "台積電", "price": 219.0, "change": 1.0,
            "changePercent": 0.46, "pe": 28.52, "marketCap": 0, "chartData": _bars()}
    base.update(over)
    return base


def test_only_the_requested_window_is_drawn():
    """days= must slice the series; drawing all 120 bars on a 90-bar card is a lie.

    Asserted on the axis rather than a rect count, so it keeps testing the window when
    the panes change — the old count broke the moment a pane was added.
    """
    bars = _bars(120)
    svg = stock_card_svg(_stock(chartData=bars), [], days=90)
    assert bars[30]["date"] in svg      # first drawn session
    assert bars[0]["date"] not in svg   # trimmed off the front


def test_a_ticker_with_no_bars_is_an_error_not_an_empty_card():
    with pytest.raises(ValueError):
        stock_card_svg(_stock(chartData=[]), [])


def test_mentions_are_counted_but_never_plotted_against_the_price():
    """Measured: mention volume correlates -0.02 with the next day's return. Drawing a
    peak beside a candle invites a causal read the data does not support, so the card
    states the total and marks nothing."""
    bars = _bars(30)
    svg = stock_card_svg(_stock(chartData=bars),
                         [{"d": bars[10]["date"], "n": 3, "bull": 2, "bear": 1}], days=30)
    assert "共提及 3 次" in svg
    assert "<circle" not in svg


def test_mentions_outside_the_drawn_window_are_not_counted():
    svg = stock_card_svg(_stock(), [{"d": "2099-01-01", "n": 9, "bull": 9, "bear": 0}], days=30)
    assert "共提及 0 次" in svg


def test_a_ticker_nobody_mentioned_still_renders():
    svg = stock_card_svg(_stock(), [], days=30)
    assert "共提及 0 次" in svg


def test_tw_and_us_show_the_stat_their_provider_actually_populates():
    """FinMind gives TW a P/E and no market cap; Massive gives US the reverse."""
    tw = stock_card_svg(_stock(), [], days=30)
    assert "本益比" in tw and "市值" not in tw and "TWSE / FinMind" in tw

    us = stock_card_svg(_stock(ticker="NVDA", name="Nvidia Corp", pe=0.0,
                               marketCap=5_562_502_920_000), [], days=30)
    assert "市值" in us and "本益比" not in us and "Massive" in us


def test_volume_uses_the_unit_that_markets_readers_use():
    assert _volume_label(26_898_329, is_tw=True) == "26,898 張"
    assert _volume_label(135_352_420, is_tw=False) == "1.35 億股"
    assert _volume_label(4_500_000, is_tw=False) == "450 萬股"


def test_a_company_name_cannot_escape_into_the_svg():
    svg = stock_card_svg(_stock(name='<script>x</script>'), [], days=30)
    assert "<script>" not in svg and "&lt;script&gt;" in svg


def test_every_glyph_on_the_card_is_one_a_cjk_font_actually_has():
    """cairosvg does no font fallback, so an exotic glyph rasterises as a tofu box.

    This caught a "→" in the date range that rendered as □ on Heiti TC. The guard is a
    whitelist rather than a ban on that one arrow, because the next tempting symbol
    (—, ↑, ▲, €) would fail exactly the same way and silently.
    """
    svg = stock_card_svg(_stock(), [{"d": _bars(30)[5]["date"], "n": 1, "bull": 1, "bear": 0}], days=30)
    rendered = re.findall(r">([^<>]+)<", svg)
    allowed = set(chr(c) for c in range(0x20, 0x7F)) | {"·", "\n"}
    exotic = {
        ch for chunk in rendered for ch in chunk
        if ch not in allowed and not (0x3000 <= ord(ch) <= 0x9FFF)
        and not (0xFF00 <= ord(ch) <= 0xFFEF)
    }
    assert not exotic, f"glyphs a CJK face may lack: {sorted(exotic)}"
