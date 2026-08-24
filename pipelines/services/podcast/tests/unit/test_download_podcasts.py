"""download_file's retry policy: a definitive 4xx is not worth three attempts.

Old back-catalogue episodes whose audio the host has deleted (SoundCloud 404s) were
costing three requests each on every scheduled ingest tick, forever.
"""

from __future__ import annotations

import pytest
import requests
from src.service.download_podcasts import download_file


def _raise_status(status: int):
    """A requests.get stand-in whose response raises HTTPError with `status`."""
    calls = []

    def _get(url, **kw):
        calls.append(url)
        resp = requests.Response()
        resp.status_code = status
        resp.url = url
        return resp

    return _get, calls


@pytest.mark.parametrize("status", [404, 403, 410])
def test_permanent_4xx_is_not_retried(monkeypatch, tmp_path, status):
    _get, calls = _raise_status(status)
    monkeypatch.setattr(requests, "get", _get)
    monkeypatch.setattr("src.service.download_podcasts.requests.get", _get)

    ok = download_file("https://host/gone.mp3", tmp_path / "x.mp3", "dead episode",
                       max_retries=3, check_existing=False)
    assert ok is False
    assert len(calls) == 1, f"HTTP {status} should not be retried, got {len(calls)} attempts"


@pytest.mark.parametrize("status", [429, 500, 503])
def test_transient_errors_still_retry(monkeypatch, tmp_path, status):
    _get, calls = _raise_status(status)
    monkeypatch.setattr("src.service.download_podcasts.requests.get", _get)
    monkeypatch.setattr("src.service.download_podcasts.time.sleep", lambda *_: None)

    ok = download_file("https://host/flaky.mp3", tmp_path / "y.mp3", "flaky episode",
                       max_retries=3, check_existing=False)
    assert ok is False
    assert len(calls) == 3, f"HTTP {status} should exhaust retries, got {len(calls)}"
