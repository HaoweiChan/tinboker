"""A feed that never answers must cost one timeout, not the whole run."""
import io
import urllib.request

from news.pipeline.steps import fetch_feeds as ff

RSS = b"""<rss version="2.0"><channel><title>t</title>
<item><title>A</title><link>https://example.com/a</link></item></channel></rss>"""


def test_default_parse_downloads_with_a_deadline(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["timeout"] = timeout
        return io.BytesIO(RSS)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    parsed = ff._default_parse("https://example.com/rss")
    assert seen["timeout"] == ff.FEED_TIMEOUT_S
    assert parsed.entries[0].link == "https://example.com/a"


def test_a_feed_that_times_out_is_skipped(monkeypatch):
    def fake_urlopen(request, timeout=None):
        if "dead" in request.full_url:
            raise TimeoutError("The read operation timed out")
        return io.BytesIO(RSS)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    entries = ff.fetch_feeds([{"name": "dead", "url": "https://dead.example/rss"},
                              {"name": "ok", "url": "https://example.com/rss"}])
    assert [e.url for e in entries] == ["https://example.com/a"]
