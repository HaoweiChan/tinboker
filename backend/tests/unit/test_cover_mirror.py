"""Podcast cover art is mirrored onto our media host, not linked off Spotify's CDN.

One pass covers ingest (row has no cover yet) and backfill (row still points at the
CDN); og.py then reads the mirrored file off local disk instead of over the network.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import ContentSource
from src.services import content_source_service as mod
from src.services.content_source_service import ContentSourceService

BASE = "https://media.example.test/media"
SPOTIFY_CDN = "https://image-cdn-fa.spotifycdn.com/image/abc123"
JPEG = b"\xff\xd8\xff\xe0" + b"tinboker" * 8


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setenv("MEDIA_PUBLIC_BASE", BASE)
    engine = create_engine("sqlite:///:memory:")
    ContentSource.__table__.create(bind=engine)
    db = sessionmaker(bind=engine)()
    yield db
    db.close()


def _podcast(session, name, cover=None, spotify="https://open.spotify.com/show/xyz"):
    src = ContentSource(
        source_type="podcast", name=name, slug=name.lower(), feed_url="https://feed.test/rss",
        spotify_url=spotify, cover_image_url=cover,
    )
    session.add(src)
    session.commit()
    return src


def _stub_network(monkeypatch, image=(JPEG, "image/jpeg"), thumb=SPOTIFY_CDN):
    """Record every URL fetched, so "no network at all" is an assertable outcome."""
    fetched = []
    monkeypatch.setattr(mod, "_oembed_thumbnail", lambda url, timeout: thumb)

    def _fetch(url, timeout):
        fetched.append(url)
        return image

    monkeypatch.setattr(mod, "_fetch_image", _fetch)
    return fetched


def test_a_row_with_no_cover_resolves_via_oembed_and_lands_on_our_disk(session, tmp_path, monkeypatch):
    _stub_network(monkeypatch)
    src = _podcast(session, "股癌")

    assert ContentSourceService(session).mirror_podcast_covers() == 1
    assert src.cover_image_url == f"{BASE}/graphfolio-articles/covers/{src.id}.jpg"
    assert (tmp_path / "graphfolio-articles" / "covers" / f"{src.id}.jpg").read_bytes() == JPEG


def test_an_existing_spotify_link_is_re_hosted_rather_than_left_pointing_off_site(session, monkeypatch):
    fetched = _stub_network(monkeypatch)
    src = _podcast(session, "M觀點", cover=SPOTIFY_CDN)

    assert ContentSourceService(session).mirror_podcast_covers() == 1
    assert fetched == [SPOTIFY_CDN]  # the stored URL, not a fresh oEmbed lookup
    assert src.cover_image_url.startswith(BASE)


def test_a_non_spotify_cover_is_mirrored_too(session, monkeypatch):
    """Some seeded rows carry SoundOn URLs; the stored URL is used as-is."""
    soundon = "https://files.soundon.fm/1635818543881-b02d557d.jpeg"
    fetched = _stub_network(monkeypatch, thumb="")
    src = _podcast(session, "兆華與股惑仔", cover=soundon, spotify=None)

    assert ContentSourceService(session).mirror_podcast_covers() == 1
    assert fetched == [soundon]
    assert src.cover_image_url.startswith(BASE)


def test_a_row_with_neither_a_cover_nor_a_spotify_link_is_left_alone(session, monkeypatch):
    fetched = _stub_network(monkeypatch, thumb="")
    src = _podcast(session, "無圖", spotify=None)

    assert ContentSourceService(session).mirror_podcast_covers() == 0
    assert fetched == []
    assert src.cover_image_url is None


def test_re_running_touches_nothing_and_makes_no_request(session, monkeypatch):
    """It runs on every boot, so the mirrored steady state has to cost zero."""
    _stub_network(monkeypatch)
    _podcast(session, "股癌")
    svc = ContentSourceService(session)
    svc.mirror_podcast_covers()

    fetched = _stub_network(monkeypatch)
    assert svc.mirror_podcast_covers() == 0
    assert fetched == []


def test_artwork_the_media_host_would_serve_as_script_is_refused(session, monkeypatch):
    """SVG on the media origin is a scriptable document; the row keeps its old value."""
    _stub_network(monkeypatch, image=(b"<svg onload=alert(1)>", "image/svg+xml"))
    src = _podcast(session, "隱者", cover=SPOTIFY_CDN)

    assert ContentSourceService(session).mirror_podcast_covers() == 0
    assert src.cover_image_url == SPOTIFY_CDN


def test_an_oversized_response_is_refused_rather_than_stored_truncated(session, monkeypatch):
    _stub_network(monkeypatch, image=(b"x" * (mod._COVER_MAX_BYTES + 1), "image/jpeg"))
    src = _podcast(session, "巨大")

    assert ContentSourceService(session).mirror_podcast_covers() == 0
    assert src.cover_image_url is None


def test_one_unreachable_show_does_not_abort_the_pass(session, monkeypatch):
    monkeypatch.setattr(mod, "_oembed_thumbnail", lambda url, timeout: SPOTIFY_CDN)
    calls = []

    def _flaky(url, timeout):
        calls.append(url)
        if len(calls) == 1:
            raise OSError("connection reset")
        return JPEG, "image/jpeg"

    monkeypatch.setattr(mod, "_fetch_image", _flaky)
    first = _podcast(session, "壞掉的")
    second = _podcast(session, "好的")

    assert ContentSourceService(session).mirror_podcast_covers() == 1
    assert first.cover_image_url is None
    assert second.cover_image_url.startswith(BASE)


@pytest.mark.asyncio
async def test_og_reads_a_mirrored_cover_off_disk_without_any_http_call(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setenv("MEDIA_PUBLIC_BASE", BASE)
    from src.routers import og

    dest = tmp_path / "graphfolio-articles" / "covers" / "7.jpg"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(JPEG)

    def _no_http(*a, **kw):
        raise AssertionError("mirrored covers must not be fetched over HTTP")

    monkeypatch.setattr(og.httpx, "AsyncClient", _no_http)
    data, ctype = await og._cover_bytes(f"{BASE}/graphfolio-articles/covers/7.jpg")
    assert data == JPEG
    assert ctype == "image/jpeg"


@pytest.mark.asyncio
async def test_a_missing_mirrored_file_degrades_to_no_artwork_not_a_500(tmp_path, monkeypatch):
    """The syndication crawlers hit this endpoint; a gap in the mirror is not an error."""
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setenv("MEDIA_PUBLIC_BASE", BASE)
    from src.routers import og

    async def _covers():
        return {"股癌": f"{BASE}/graphfolio-articles/covers/404.jpg"}

    monkeypatch.setattr(og.podcast_service, "_podcast_cover_map", _covers)
    monkeypatch.setattr(og, "cache_get", lambda key: _none())
    monkeypatch.setattr(og, "cache_set", lambda *a, **kw: _none())

    assert await og._cover_data_uri("股癌") == ""


async def _none():
    return None
