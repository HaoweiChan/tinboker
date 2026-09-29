"""The clip card and the ffmpeg compose — the constraints, not the pixels."""

from pathlib import Path

from src.podcast import clip_render as cr

ART = "data:image/jpeg;base64,AAAA"


def test_the_artwork_never_reaches_the_markdown():
    """markdown-it mangles a long data URI in an inline style, so the cover lives in the
    theme CSS. If this ever regresses the card renders with a broken-image icon."""
    md = cr.card_markdown("2026.09.22", "EP1189｜標題", "兆華與股惑仔")
    assert "data:image" not in md and "http" not in md
    assert "EP1189｜標題" in md and "兆華與股惑仔" in md

    css = cr.card_theme_css(ART)
    assert css.count(ART) == 2          # the blurred backdrop and the crisp cover


def test_the_veil_is_not_declared_on_the_marp_page_number():
    """``section::after`` is Marp's own pseudo-element; a veil there is silently dropped
    and the card renders unreadable over the blur."""
    css = cr.card_theme_css(ART)
    assert "section::after" not in css
    assert "section .veil" in css
    assert '<div class="veil">' in cr.card_markdown("d", "t", "s")


def test_the_card_css_and_the_overlay_agree_on_where_the_track_is():
    css = cr.card_theme_css(ART)
    assert f"left:{cr.TRACK_X}px; top:{cr.TRACK_Y}px" in css
    args = cr.ffmpeg_args(Path("card.png"), "http://a/x.mp3", 0, 20.0, Path("out.mp4"))
    assert f"overlay={cr.TRACK_X}:{cr.TRACK_Y}" in " ".join(args)


def test_the_progress_bar_is_an_alpha_ramp_over_the_clip_length():
    """drawbox's `t` is thickness and crop has no eval=frame, so neither can animate."""
    graph = " ".join(cr.ffmpeg_args(Path("c.png"), "a.mp3", 0, 25.0, Path("o.mp4")))
    assert "geq=" in graph and "drawbox" not in graph
    assert f"{cr.TRACK_W}*T/25.0" in graph


def test_the_elapsed_clock_counts_from_inside_the_episode():
    """Left clock = the position in the EPISODE, right = what is left of the clip."""
    graph = " ".join(cr.ffmpeg_args(Path("c.png"), "a.mp3", 1043945, 20.0, Path("o.mp4")))
    assert "1043.945+t" in graph
    assert "20.0-t" in graph


def test_output_is_capped_at_the_clip_length():
    args = cr.ffmpeg_args(Path("c.png"), "a.mp3", 0, 18.5, Path("o.mp4"))
    assert args[-2:] == ["18.500", "o.mp4"] and args[-3] == "-t"


def test_artwork_falls_back_to_the_show_cover(monkeypatch):
    monkeypatch.setattr(cr, "_fetch", lambda url, timeout=60: b"\xff\xd8bytes")
    assert cr.artwork_data_uri({"spotify_images": ["http://ep/a.jpg"]}).startswith("data:image")
    assert cr.artwork_data_uri({}, "http://show/b.jpg").startswith("data:image")
    assert cr.artwork_data_uri({}, None) is None


def test_a_fetch_failure_is_no_clip_rather_than_an_exception(monkeypatch):
    def boom(url, timeout=60):
        raise OSError("no network")
    monkeypatch.setattr(cr, "_fetch", boom)
    assert cr.artwork_data_uri({}, "http://show/b.jpg") is None


def test_render_clip_gives_up_quietly_without_a_cover_or_audio(monkeypatch):
    import types
    called = []
    # Replace the module reference, not subprocess.run itself — patching the real module
    # breaks every other importer in the process.
    monkeypatch.setattr(cr, "subprocess", types.SimpleNamespace(
        run=lambda *a, **k: called.append(a)))
    monkeypatch.setattr(cr, "artwork_data_uri", lambda *a, **k: None)
    assert cr.render_clip({"mp3_public_url": "http://a/x.mp3"},
                          {"start_ms": 0, "end_ms": 20000}) is None

    monkeypatch.setattr(cr, "artwork_data_uri", lambda *a, **k: ART)
    assert cr.render_clip({}, {"start_ms": 0, "end_ms": 20000}) is None
    assert called == [], "ffmpeg must not run when there is nothing to render"


def test_render_card_raises_when_the_service_returns_no_image(monkeypatch):
    class _Resp:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def read(self):
            return b'{"success": false, "images": []}'
    monkeypatch.setattr(cr.urllib.request, "urlopen", lambda *a, **k: _Resp())
    try:
        cr.render_card("md", "css")
    except RuntimeError as e:
        assert "no image" in str(e)
    else:
        raise AssertionError("a card that did not render must not pass silently")
