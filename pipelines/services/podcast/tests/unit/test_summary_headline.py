"""The written headline has to reach the episode, and be worth using when it does.

Feed titles are unusable at both extremes — "EP689 | 🏐" names nothing and a 70-character
keyword dump buries the point — so social_copy_writer writes one headline that titles the
vocus/Substack copies, the cover and the Threads post. These lock the guards on what the
model returns and the wiring that carries it, the same four layers social_thread needed.
"""

from __future__ import annotations

from types import SimpleNamespace

from src.models.podcast_models import PodcastEpisode
from src.podcast.content_builder.nodes import social_copy_writer as scw

HEADLINE = "EP689｜記憶體估值成了零組件天花板"
_STATE = {"episode_title": "EP689 | 🏐"}


def _out(headline):
    return scw.postprocess({"headline": headline, "post": "p", "comments": []}, _STATE)


def test_a_written_headline_is_kept():
    assert _out(HEADLINE)["summary_headline"] == HEADLINE


def test_an_echo_of_the_feed_title_is_rejected():
    """Echoing "EP689 | 🏐" is the case the headline exists to fix, so it is not one."""
    assert _out("EP689 | 🏐")["summary_headline"] == ""
    assert _out("EP689｜🏐")["summary_headline"] == ""  # same string, different separator


def test_a_keyword_dump_is_rejected():
    assert _out("標" * (scw.MAX_HEADLINE_CHARS + 1))["summary_headline"] == ""
    assert _out("標" * scw.MAX_HEADLINE_CHARS)["summary_headline"] != ""


def test_a_missing_or_junk_headline_is_empty_not_none():
    """Empty is a valid answer — syndication_title then falls back to the feed title."""
    assert scw.postprocess({"post": "p"}, _STATE)["summary_headline"] == ""
    assert _out(None)["summary_headline"] == ""
    assert scw.postprocess({"headline": 42, "post": "p"}, _STATE)["summary_headline"] == ""


def test_the_thread_still_comes_out_alongside_it():
    out = _out(HEADLINE)
    assert out["social_thread"] == {"post": "p", "comments": []}


def test_create_episode_object_carries_it():
    from src.pipeline.utils import create_episode_object

    episode = create_episode_object(
        episode_data=SimpleNamespace(
            api_data={}, tickers=[], podcast_name="Gooaye 股癌", created_time=None
        ),
        gcs_urls={},
        spotify_metadata=None,
        summary_result={"summary_text": "x", "summary_headline": HEADLINE},
    )
    assert episode.summary_headline == HEADLINE


def _episode(**kw) -> PodcastEpisode:
    return PodcastEpisode(
        mp3_url="", transcript_url="", summary_url="", summary_image_url="", **kw
    )


def test_it_is_merge_safe_like_the_rest_of_the_generated_fields():
    """A run that wrote no headline must not blank the stored one."""
    assert "summary_headline" not in _episode(summary_headline=None).to_firestore_dict()
    assert "summary_headline" not in _episode(summary_headline="").to_firestore_dict()
    assert _episode(summary_headline=HEADLINE).to_firestore_dict()["summary_headline"] == HEADLINE


def test_from_firestore_dict_round_trips():
    assert PodcastEpisode.from_firestore_dict(
        {"summary_headline": HEADLINE}).summary_headline == HEADLINE
    assert PodcastEpisode.from_firestore_dict({}).summary_headline is None
