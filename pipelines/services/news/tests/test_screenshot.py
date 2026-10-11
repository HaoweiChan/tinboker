"""The screenshot step fails closed; the browser itself is exercised on the VPS."""
import pytest
from news import screenshot


@pytest.mark.parametrize("url,phrases", [("http://example.com/a", ["a quote"]), ("https://example.com/a", [])])
def test_bad_request_never_starts_a_browser(monkeypatch, url, phrases):
    monkeypatch.setattr(screenshot.subprocess, "Popen", lambda *a, **k: pytest.fail("browser started"))
    with pytest.raises(RuntimeError, match="bad_request"):
        screenshot.capture(url, phrases)


def test_missing_browser_is_a_named_failure(monkeypatch):
    monkeypatch.delenv("NEWS_SCREENSHOT_BROWSER", raising=False)
    monkeypatch.setattr(screenshot.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="no_browser"):
        screenshot.capture("https://example.com/a", ["a quote"])


def test_phrases_reach_the_page_as_data_not_code():
    script = screenshot._script(screenshot._LOCATE, ['quote with "quotes"\n and </script> `${x}`'])
    assert script.startswith('const PHRASES = ["quote with \\"quotes\\" and </script> `${x}`"];')
