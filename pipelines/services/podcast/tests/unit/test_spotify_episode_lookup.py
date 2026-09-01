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


def test_null_external_urls_does_not_crash(monkeypatch):
    """Spotify returns an explicit null for these on unavailable episodes.

    `.get('external_urls', {})` hands back None in that case — the default is only used
    when the key is absent, not when its value is null — and the chained .get() raised,
    which get_spotify_metadata then swallowed as a bare "Error fetching Spotify
    metadata". Seen live on 游庭皓的財經皓角 during the backfill dry-run.
    """
    from src.spotify_podcast import metadata_helper as mh

    episode = {"id": "abc", "external_urls": None, "images": None,
               "release_date": "2026-08-24", "description": "d", "duration_ms": 1}

    monkeypatch.setenv("SPOTIFY_ID", "x")
    monkeypatch.setenv("SPOTIFY_SECRET", "y")
    monkeypatch.setattr(mh, "get_access_token", lambda *a, **k: "token")

    class _Parser:
        def __init__(self, *a, **k):
            pass

        def extract_show_id(self, link):
            return "show"

        def find_episode_by_title(self, show_id, title, limit=100):
            return episode

    monkeypatch.setattr(mh, "SpotifyPodcastParser", _Parser)

    meta = mh.get_spotify_metadata("https://open.spotify.com/show/x", "EP1", limit=100)

    assert meta is not None, "a null external_urls must not sink the whole fetch"
    assert meta["spotify_url"] is None
    assert meta["images"] == []
    assert meta["spotify_id"] == "abc"


def test_null_items_in_the_page_do_not_crash():
    """Spotify puts a literal null in `items` for market-unavailable episodes.

    Iterating those raised AttributeError, which get_spotify_metadata swallowed as a
    bare "Error fetching Spotify metadata" — the failure seen against
    游庭皓的財經皓角 (353 episodes) in the backfill dry-run.
    """
    class _NullyParser(_FakeParser):
        def get_episodes(self, show_id, limit=50, offset=0):
            page = super().get_episodes(show_id, limit=limit, offset=offset)
            # Every other entry comes back as null.
            page["items"] = [item if i % 2 else None for i, item in enumerate(page["items"])]
            return page

    p = _NullyParser([f"EP{i}" for i in range(120)])

    found = p.find_episode_by_title("show", "EP101", limit=200)

    assert found is not None and found["name"] == "EP101"


def test_null_items_do_not_break_pagination_offsets():
    class _AllNullFirstPage(_FakeParser):
        def get_episodes(self, show_id, limit=50, offset=0):
            page = super().get_episodes(show_id, limit=limit, offset=offset)
            if offset == 0:
                page["items"] = [None] * len(page["items"])
            return page

    p = _AllNullFirstPage([f"EP{i}" for i in range(120)])

    # EP60 sits on page 2; a first page of pure nulls must not stall the offset at 0.
    assert p.find_episode_by_title("show", "EP60", limit=200)["name"] == "EP60"
    assert 50 in p.offsets, f"offset never advanced past the null page: {p.offsets}"


def test_many_titles_cost_one_pagination_not_one_each():
    """The reason fetching and matching are separate functions.

    The first backfill called get_spotify_metadata per episode, which paged the whole
    show every time — roughly 27,000 requests for the backlog, and Spotify began
    returning 429 after about a hundred. Paging once per show and matching in memory is
    what makes the backfill runnable at all.
    """
    titles = [f"EP{i}" for i in range(120)]
    p = _FakeParser(titles)

    catalogue = p.get_all_episodes("show", limit=200)
    fetches_after_paging = len(p.offsets)

    found = [p.match_title(catalogue, t) for t in titles[:50]]

    assert all(f is not None for f in found), "in-memory matching must find them all"
    assert len(p.offsets) == fetches_after_paging, (
        f"match_title performed I/O: offsets grew to {p.offsets}"
    )
    assert fetches_after_paging <= 4, f"one show should be a handful of pages, got {p.offsets}"


def test_find_episode_by_title_still_works_through_the_split():
    # The single-title entry point is now a thin wrapper; keep it honest.
    p = _FakeParser([f"EP{i}" for i in range(120)])
    assert p.find_episode_by_title("show", "EP101", limit=200)["name"] == "EP101"


# These exercise the real get_episodes by faking `requests`, not by subclassing it.
# The earlier null-item tests replaced get_episodes wholesale, so they never reached the
# embed-URL loop inside it — which was still crashing on the same nulls.

class _Resp:
    def __init__(self, status=200, payload=None, retry_after=None):
        self.status_code = status
        self._payload = payload or {"items": [], "next": None}
        self.headers = {"Retry-After": retry_after} if retry_after else {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.exceptions.HTTPError(f"{self.status_code} Client Error")


def test_get_episodes_survives_null_items(monkeypatch):
    from src.spotify_podcast import parser as parser_mod

    payload = {"items": [None, {"id": "e1", "name": "EP1"}, None], "next": None}
    monkeypatch.setattr(parser_mod.requests, "get", lambda *a, **k: _Resp(200, payload))

    p = parser_mod.SpotifyPodcastParser(access_token="t")
    data = p.get_episodes("show")

    assert [e for e in data["items"] if e][0]["embed_url"].endswith("/e1")


def test_get_episodes_honours_retry_after_then_succeeds(monkeypatch):
    from src.spotify_podcast import parser as parser_mod

    calls = {"n": 0}
    slept = []

    def fake_get(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            return _Resp(429, retry_after="2")
        return _Resp(200, {"items": [{"id": "e1", "name": "EP1"}], "next": None})

    monkeypatch.setattr(parser_mod.requests, "get", fake_get)
    monkeypatch.setattr(parser_mod.time, "sleep", slept.append)

    p = parser_mod.SpotifyPodcastParser(access_token="t")
    data = p.get_episodes("show")

    assert data["items"][0]["id"] == "e1"
    assert slept == [2], f"should have waited exactly the Retry-After, waited {slept}"


def test_get_episodes_gives_up_and_says_how_long_to_wait(monkeypatch):
    from src.spotify_podcast import parser as parser_mod

    monkeypatch.setattr(parser_mod.requests, "get", lambda *a, **k: _Resp(429, retry_after="1"))
    monkeypatch.setattr(parser_mod.time, "sleep", lambda _s: None)

    p = parser_mod.SpotifyPodcastParser(access_token="t")
    try:
        p.get_episodes("show")
    except ValueError as e:
        assert "rate limited" in str(e), f"a throttle must not read as a miss: {e}"
        assert "retry in 1s" in str(e), f"the wait must be actionable: {e}"
    else:
        raise AssertionError("expected a ValueError naming the rate limit")


def test_a_quota_window_fails_fast_instead_of_sleeping_through_it(monkeypatch):
    """Spotify answered Retry-After: 2101 after the first backfill attempt.

    That is a quota window, not a burst. Sleeping through it would hang a batch job for
    35 minutes, and retrying anyway just spends more requests against a closed window —
    which is what kept the window open while I was probing every 5 minutes.
    """
    from src.spotify_podcast import parser as parser_mod

    slept = []
    monkeypatch.setattr(parser_mod.requests, "get", lambda *a, **k: _Resp(429, retry_after="2101"))
    monkeypatch.setattr(parser_mod.time, "sleep", slept.append)

    p = parser_mod.SpotifyPodcastParser(access_token="t")
    try:
        p.get_episodes("show")
    except ValueError as e:
        assert "retry in 2101s" in str(e), e
    else:
        raise AssertionError("expected a ValueError")
    assert slept == [], f"must not sleep through a quota window, slept {slept}"
