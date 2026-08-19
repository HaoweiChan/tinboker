"""A show pulled from the platform /api/sources must still have a usable episode limit.

Regression: ``_source_to_podcast`` always writes a "limit" key (copied from the optional
``max_episodes``), so for a source without one the key exists holding None and the old
``podcast.get("limit", 2)`` default never fired. The None reached
``_filter_unprocessed_episodes`` and raised ``'>=' not supported between instances of
'int' and 'NoneType'`` — every show, every scheduled run, for two days.
"""

from __future__ import annotations

from src.podcast import orchestrator as o


def test_platform_source_without_max_episodes_still_carries_a_limit_key():
    """The shape that caused it: the key is present and None, so get(..., 2) is useless."""
    mapped = o._source_to_podcast({"name": "股癌", "feed_url": "https://example.com/rss"})
    assert "limit" in mapped
    assert mapped["limit"] is None


def test_a_none_limit_falls_back_to_two_instead_of_raising(monkeypatch, tmp_path):
    """End to end through the real _process_single_podcast: the filter must receive an
    int. Before the fix this call raised inside _filter_unprocessed_episodes.

    _process_single_podcast catches and prints whatever fails after this point (the
    stub base_config has none of the attributes the later steps want), so the captured
    limit is the assertion that matters — it is None without the fix.
    """
    import src.service.feed_source as feed_source

    seen = {}

    def fake_filter(episodes, name, limit, service_container):
        seen["limit"] = limit
        return []

    monkeypatch.setattr(feed_source, "resolve_rss_url", lambda podcast: "https://x/rss")
    monkeypatch.setattr(feed_source, "fetch_feed_episodes", lambda podcast: [{"id": "e1"}])
    monkeypatch.setattr(o, "_filter_unprocessed_episodes", fake_filter)

    podcast = o._source_to_podcast({"name": "股癌", "feed_url": "https://example.com/rss"})
    o._process_single_podcast(
        podcast=podcast,
        config_file=tmp_path / "c.json",
        rerun_from=None,
        transcript_service="groq",
        use_file_mode=True,
        reuse_existing_transcript=False,
        fill_limit=True,
        base_config=object(),
        service_container=object(),
    )

    assert seen["limit"] == 2, "a None limit must fall back to the documented default"
