"""The two pieces of the Spotify backfill that can silently corrupt data.

`build_updates` must never write a null over an existing value — a partial Spotify
response blanking a good spotify_url is worse than leaving the row alone. And the row
selection must skip episodes that already have a link unless --overwrite is passed.
"""

import json

from scripts.backfill_spotify_metadata import _TABLE, build_updates, load_show_links, select_sql


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


# Selection is asserted through the generated SQL rather than a live query: the real
# store is a JSONB `doc` column in Postgres, which SQLite cannot model, and standing up
# Postgres in unit tests to check one predicate is not worth it. This catches the things
# that actually broke — wrong table, wrong column, missing filter — and would not catch
# a Postgres-specific syntax error. The dry-run is what covers that.

def test_targets_the_mirror_table_not_the_typed_one():
    sql, _ = select_sql(podcast=None, limit=None, overwrite=False)
    assert _TABLE == "firestore_mirror.episodes"
    assert f"FROM {_TABLE}" in sql
    assert "FROM episodes" not in sql, "the typed episodes table does not exist in this DB"


def test_skips_episodes_that_already_have_a_link():
    sql, params = select_sql(podcast=None, limit=None, overwrite=False)
    assert "coalesce(doc->>'spotify_url', '') = ''" in sql
    assert params == {}


def test_overwrite_drops_the_filter():
    sql, _ = select_sql(podcast=None, limit=None, overwrite=True)
    assert "spotify_url" not in sql.split("FROM")[1], "overwrite must not filter on the link"


def test_restricting_to_one_show_is_parameterised():
    sql, params = select_sql(podcast="Gooaye 股癌", limit=5, overwrite=False)
    assert "podcast_name = :podcast" in sql
    assert params["podcast"] == "Gooaye 股癌"
    assert params["limit"] == 5
    assert "Gooaye" not in sql, "show name must be bound, not interpolated"


def test_load_show_links_merges_several_configs(tmp_path):
    # The English shows live in podcasts_en.json and are 278 of the episodes missing a
    # link; reading only the TW config skipped every one of them.
    tw = tmp_path / "tw.json"
    en = tmp_path / "en.json"
    tw.write_text(json.dumps([{"name": "財報狗", "spotify_show_link": "https://open.spotify.com/show/tw"}]),
                  encoding="utf-8")
    en.write_text(json.dumps([{"name": "The Long View", "spotify_show_link": "https://open.spotify.com/show/en"}]),
                  encoding="utf-8")

    links = load_show_links(tw, en)

    assert set(links) == {"財報狗", "The Long View"}


def test_load_show_links_tolerates_a_missing_config(tmp_path):
    present = tmp_path / "tw.json"
    present.write_text(json.dumps([{"name": "A", "spotify_show_link": "https://open.spotify.com/show/a"}]),
                       encoding="utf-8")

    assert load_show_links(present, tmp_path / "nope.json") == {
        "A": "https://open.spotify.com/show/a"
    }


def test_shipped_configs_point_at_shows_not_episodes():
    """A /episode/ URL in spotify_show_link fails silently.

    "Exchanges at Goldman Sachs" carried one, so its catalogue never paged and all 59
    of its episodes kept the re-hosted player the AdSense replicated-content fix was
    meant to remove. The backfill reports it as "unusable show link" and moves on, so
    nothing is corrupted and nothing is fixed — the only signal is a line in a run
    nobody reads. Assert on the shipped files instead.
    """
    from pathlib import Path

    service_root = Path(__file__).resolve().parents[2]
    for name in ("podcasts_tw.json", "podcasts_en.json"):
        config = service_root / name
        for show in json.loads(config.read_text(encoding="utf-8")):
            link = show.get("spotify_show_link")
            if not link:
                continue  # deliberately unlinked shows carry a _spotify_note instead
            assert "/show/" in link, f"{name}: {show.get('name')} -> {link}"
