"""Unit tests for the ``tags/{slug}/episodes`` fan-out inversion added to
``scripts/dump_firestore_to_postgres.py`` (backfills ``episodes.doc['tags']`` in the
Postgres mirror only — Firestore itself is never written by this script).
"""

from __future__ import annotations

from scripts.dump_firestore_to_postgres import _invert_tag_fanout


def test_invert_tag_fanout_groups_and_sorts_slugs_per_episode():
    pairs = [
        ("ai", "ep_1"),
        ("supplychain", "ep_1"),
        ("ai", "ep_2"),
    ]

    result = _invert_tag_fanout(pairs)

    assert result == {"ep_1": ["ai", "supplychain"], "ep_2": ["ai"]}


def test_invert_tag_fanout_dedupes_duplicate_pairs():
    """A tag fan-out doc re-read twice (or a slug appearing under two aliases that
    normalize the same) must not produce a duplicate entry."""
    pairs = [("ai", "ep_1"), ("ai", "ep_1")]

    result = _invert_tag_fanout(pairs)

    assert result == {"ep_1": ["ai"]}


def test_invert_tag_fanout_empty_input():
    assert _invert_tag_fanout([]) == {}
