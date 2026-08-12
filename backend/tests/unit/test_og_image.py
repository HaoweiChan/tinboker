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
