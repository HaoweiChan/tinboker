"""One written headline names the episode on every off-site copy.

Feed titles fail at both ends: "EP689 | 🏐" names nothing, and a 70-character keyword
dump pushes the 摘要 suffix past where anyone reads. The pipeline writes a headline; the
publishers, the cover and the Threads post all have to use the same one, or the episode
appears under a different name depending on where a reader meets it.
"""

from src.services.syndication_markdown import syndication_title
from src.services.threads_publisher import _finalize_post_text, compose_post, headline_line

HEADLINE = "EP689｜記憶體估值成了零組件天花板"
FEED_TITLE = "EP689 | 🏐"


def test_the_headline_wins_over_the_feed_title():
    assert syndication_title("Gooaye 股癌", FEED_TITLE, HEADLINE) == f"股癌 {HEADLINE} 摘要"


def test_no_headline_keeps_the_behaviour_that_shipped_before():
    assert syndication_title("Gooaye 股癌", FEED_TITLE, None) == "股癌 EP689 | 🏐 摘要"
    assert syndication_title("Gooaye 股癌", FEED_TITLE, "   ") == "股癌 EP689 | 🏐 摘要"


def test_the_show_name_is_still_added_once():
    """The headline carries no show name of its own — syndication_title composes it."""
    assert syndication_title("Gooaye 股癌", FEED_TITLE, "股癌 EP689｜記憶體") == "股癌 EP689｜記憶體 摘要"


def test_threads_post_opens_with_the_headline_as_its_own_line():
    out = _finalize_post_text({"summary_headline": HEADLINE}, "記憶體這件事我本來沒在追", "")
    assert out.startswith(f"{HEADLINE}\n\n"), "a title line, not glued to the first sentence"
    assert out.endswith("記憶體這件事我本來沒在追")


def test_a_post_that_already_opens_with_it_is_not_prefixed_twice():
    body = f"{HEADLINE}\n\n內文"
    assert _finalize_post_text({"summary_headline": HEADLINE}, body, "") == body


def test_without_a_headline_the_post_is_unchanged():
    assert _finalize_post_text({}, "內文", "") == "內文"
    assert headline_line({}) == ""


def test_the_headline_survives_a_body_that_would_overflow():
    """It is reserved before the body, so clamping trims the copy and not the title."""
    out = _finalize_post_text({"summary_headline": HEADLINE}, "字" * 5000, "⬇️ 7 個重點整理")
    assert out.startswith(HEADLINE)
    assert out.endswith("⬇️ 7 個重點整理")


def test_the_mechanical_fallback_names_the_episode_the_same_way():
    """No social_thread — the composed header must still use the headline."""
    episode = {"id": "e1", "podcast_name": "Gooaye 股癌", "episode_title": FEED_TITLE,
               "summary_headline": HEADLINE, "key_insights": []}
    assert HEADLINE in compose_post(episode, with_link=False)["text"]
