"""The two pieces of the Spotify backfill that can silently corrupt data.

`build_updates` must never write a null over an existing value — a partial Spotify
response blanking a good spotify_url is worse than leaving the row alone. And the row
selection must skip episodes that already have a link unless --overwrite is passed.
"""

import json

import pytest
import sqlalchemy as sa
from scripts.backfill_spotify_metadata import build_updates, load_show_links, select_episodes


def test_build_updates_drops_missing_fields():
    updates = build_updates({"spotify_url": "https://open.spotify.com/episode/x",
                             "release_date": "2026-08-01",
                             "description": None,
                             "duration_ms": None,
                             "images": []})
    assert updates == {"spotify_url": "https://open.spotify.com/episode/x",
                       "spotify_release_date": "2026-08-01"}
    assert "spotify_description" not in updates, "None must not be written over a real value"
    assert "spotify_images" not in updates, "empty image list must not blank the column"


def test_build_updates_maps_the_renamed_keys():
    # get_spotify_metadata returns embed_url / release_date, the columns are prefixed.
    updates = build_updates({"embed_url": "https://open.spotify.com/embed/x",
                             "release_date": "2026-08-01",
                             "images": ["https://img/1.jpg"]})
    assert updates["spotify_embed_url"] == "https://open.spotify.com/embed/x"
    assert updates["spotify_release_date"] == "2026-08-01"
    assert updates["spotify_images"] == ["https://img/1.jpg"]


def test_build_updates_empty_metadata_writes_nothing():
    assert build_updates({}) == {}


def test_load_show_links_keeps_only_configured_links(tmp_path):
    cfg = tmp_path / "shows.json"
    cfg.write_text(json.dumps([
        {"name": "有連結", "spotify_show_link": "https://open.spotify.com/show/a"},
        {"name": "沒連結"},
    ]), encoding="utf-8")

    links = load_show_links(cfg)

    assert links == {"有連結": "https://open.spotify.com/show/a"}


@pytest.fixture()
def conn():
    engine = sa.create_engine("sqlite://")
    with engine.connect() as c:
        c.execute(sa.text(
            "CREATE TABLE episodes (id TEXT, podcast_name TEXT, episode_title TEXT,"
            " spotify_url TEXT, created_time INTEGER)"
        ))
        for i, (pod, url) in enumerate([
            ("A", None), ("A", ""), ("A", "https://open.spotify.com/episode/has"), ("B", None),
        ]):
            c.execute(sa.text(
                "INSERT INTO episodes VALUES (:id, :p, :t, :u, :ct)"
            ), {"id": f"e{i}", "p": pod, "t": f"EP{i}", "u": url, "ct": i})
        yield c


def test_select_skips_episodes_that_already_have_a_link(conn):
    rows = select_episodes(conn, podcast=None, limit=None, overwrite=False)
    ids = {r.id for r in rows}
    assert ids == {"e0", "e1", "e3"}, "an episode with a spotify_url must not be reprocessed"


def test_select_overwrite_includes_everything(conn):
    rows = select_episodes(conn, podcast=None, limit=None, overwrite=True)
    assert len(rows) == 4


def test_select_can_restrict_to_one_show(conn):
    rows = select_episodes(conn, podcast="B", limit=None, overwrite=False)
    assert [r.id for r in rows] == ["e3"]
