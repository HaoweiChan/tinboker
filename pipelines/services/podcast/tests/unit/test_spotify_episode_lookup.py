"""find_episode_by_title: paging, and exact-beats-partial across pages.

The old implementation hand-unrolled two pages, so an episode outside the newest 100
was unreachable — on a daily show that is roughly four months, which is why most of the
back catalogue carried no spotify_url. It also returned a partial match from page 1
without ever fetching page 2, so a loose match could beat an exact one.
"""

from src.spotify_podcast.parser import SpotifyPodcastParser


class _FakeParser(SpotifyPodcastParser):
    """Serves canned pages and records the offsets asked for."""

    def __init__(self, titles, page_size=50):
        self.access_token = "fake"  # skip auth
        self._titles = titles
        self._page_size = page_size
        self.offsets = []

    def get_episodes(self, show_id, limit=50, offset=0):
        self.offsets.append(offset)
        page = self._titles[offset:offset + min(limit, self._page_size)]
        return {
            "items": [{"name": t, "id": f"id-{t}"} for t in page],
            "next": "more" if offset + len(page) < len(self._titles) else None,
        }


def test_finds_an_episode_past_the_first_two_pages():
    # 300 episodes; the wanted one sits at index 250 — unreachable before this fix.
    titles = [f"EP{i}" for i in range(300)]
    p = _FakeParser(titles)

    found = p.find_episode_by_title("show", "EP250", limit=300)

    assert found is not None, "episode beyond the first pages was not found"
    assert found["name"] == "EP250"
    assert len(p.offsets) > 2, f"expected real paging, only asked for {p.offsets}"


def test_never_reads_beyond_the_limit():
    titles = [f"EP{i}" for i in range(300)]
    p = _FakeParser(titles)

    assert p.find_episode_by_title("show", "EP250", limit=100) is None
    # 100 episodes = two 50-item pages, and it must stop there.
    assert max(p.offsets) < 100


def test_exact_match_wins_over_a_partial_on_an_earlier_page():
    # Page 1 holds a title that *contains* the search string; page 2 holds the exact one.
    titles = ["EP100 重播 加長版"] + [f"filler{i}" for i in range(60)] + ["EP100 重播"]
    p = _FakeParser(titles)

    found = p.find_episode_by_title("show", "EP100 重播", limit=200)

    assert found["name"] == "EP100 重播"


def test_short_titles_do_not_partial_match():
    # "EP1" is a substring of half the catalogue; attaching the wrong episode's URL is
    # worse than attaching none.
    p = _FakeParser(["EP1170 完整版", "EP1171 完整版"])

    assert p.find_episode_by_title("show", "EP1", limit=100) is None


def test_no_episodes_is_not_an_error():
    p = _FakeParser([])
    assert p.find_episode_by_title("show", "EP1170", limit=100) is None


def test_blank_search_title_returns_none_without_calling_the_api():
    p = _FakeParser(["EP1"])
    assert p.find_episode_by_title("show", "   ", limit=100) is None
    assert p.offsets == []
