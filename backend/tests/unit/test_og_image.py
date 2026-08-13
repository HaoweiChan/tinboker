"""The generated cover for syndicated copies."""
from src.services.og_image import ART_SIZE, WIDTH, _wrap, episode_cover_svg


def test_a_cjk_title_that_fits_wraps_without_an_ellipsis():
    lines = _wrap("主委的閃電風暴與資金輪動以及更多更多更多的內容還沒有結束", 14, 3)
    assert lines == ["主委的閃電風暴與資金輪動以及", "更多更多更多的內容還沒有結束"]
    assert not lines[-1].endswith("…")


def test_a_title_too_long_for_the_block_is_ellipsised_rather_than_overflowing():
    """Three lines is what the layout has room for; the rest has to go somewhere."""
    lines = _wrap("主" * 60, 14, 3)
    assert len(lines) == 3
    assert all(len(line) <= 14 for line in lines)
    assert lines[-1].endswith("…")


def test_latin_titles_break_on_spaces_not_mid_word():
    lines = _wrap("The Great Rotation Explained", 14, 3)
    assert not any(line.endswith("-") for line in lines)
    assert all(" " not in line[:1] for line in lines)


def test_markup_in_a_title_cannot_escape_into_the_svg():
    """Titles come from ingested feeds, so they are untrusted input on a public endpoint."""
    svg = episode_cover_svg('EP1 <script>alert(1)</script> & "quoted"')
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg
    assert "&amp;" in svg


def test_a_cover_without_artwork_is_still_a_valid_cover():
    """Artwork is fetched over the network and may simply not arrive; that degrades the
    image, it must not break it."""
    svg = episode_cover_svg("EP684", kicker="股癌")
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")
    assert "<image" not in svg
    assert "股癌" in svg


def test_artwork_is_embedded_and_clipped_when_supplied():
    svg = episode_cover_svg("EP684", kicker="股癌", cover_data_uri="data:image/jpeg;base64,AAAA")
    assert 'href="data:image/jpeg;base64,AAAA"' in svg
    assert "clip-path" in svg
    assert f'width="{ART_SIZE}"' in svg


def test_the_cover_carries_the_site_theme_and_canvas():
    """Hard-coded from frontend/src/index.css; if the theme moves these must move too."""
    svg = episode_cover_svg("EP684")
    assert f'width="{WIDTH}"' in svg
    assert "#fbac23" in svg   # --primary, terminal amber
    assert "#07090e" in svg   # --background


def test_the_font_family_named_is_one_that_exists_here():
    """cairosvg does no font fallback — it renders with the family named and turns every
    glyph that family lacks into a tofu box. Naming a CSS keyword stack
    ("system-ui, ..., sans-serif") produced Latin text and □□□ for the Chinese."""
    from src.services.og_image import cjk_font_family
    fam = cjk_font_family()
    assert fam and "system-ui" not in fam and "sans-serif" != fam
    assert f'font-family="{fam}"' in episode_cover_svg("測試標題")


def test_a_quote_in_the_font_name_cannot_break_out_of_the_attribute():
    from src.services.og_image import cjk_font_family
    svg = episode_cover_svg("測試")
    assert svg.count('font-family="') == 3
    assert cjk_font_family() in svg


def test_png_rasterisation_produces_a_real_png():
    """Skipped rather than faked where libcairo is absent: a green test on a machine that
    cannot rasterise would say nothing about the machine that has to."""
    import pytest
    try:
        from src.services.og_image import episode_cover_png
        png = episode_cover_png(episode_cover_svg("EP684 測試", kicker="股癌"))
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"cairo unavailable here: {str(e)[:60]}")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(png) > 5000


def test_emoji_get_their_own_font_run():
    """No CJK face has emoji glyphs and cairosvg does not fall back, so an emoji left in a
    CJK run renders as a box. Episode titles genuinely contain them ("EP684 | 🔦"), so
    they are switched to an emoji family rather than stripped."""
    from src.services.og_image import emoji_font_family
    svg = episode_cover_svg("EP684 | 🔦 主委的閃電風暴")
    assert f'<tspan font-family="{emoji_font_family()}">🔦</tspan>' in svg
    assert "主委的閃電風暴" in svg


def test_text_without_emoji_gains_no_extra_markup():
    svg = episode_cover_svg("EP684 主委的閃電風暴")
    from src.services.og_image import emoji_font_family
    assert emoji_font_family() not in svg


def test_a_run_of_several_emoji_stays_one_tspan():
    """Splitting a ZWJ sequence across tspans would break the glyph it composes."""
    from src.services.og_image import _runs, emoji_font_family
    out = _runs("看 🔦🚑 這裡", emoji_font_family())
    assert out.count("<tspan") == 1


def test_markup_inside_an_emoji_run_is_still_escaped():
    from src.services.og_image import _runs, emoji_font_family
    assert "<script>" not in _runs("🔦<script>x</script>", emoji_font_family())
