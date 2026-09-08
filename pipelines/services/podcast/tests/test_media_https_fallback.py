"""Media artifacts must be readable off the VPS.

The media tree is only mounted on the VPS. Every read went straight to that path,
so the agent-driven regen (which reads an episode's stored transcript) could only
ever run there. The same artifacts are published read-only over HTTPS, so a local
miss falls back to the public URL.
"""

from pathlib import Path

import pytest

from src.service import gcs_storage_service as g


BUCKET = "graphfolio-articles"


@pytest.fixture
def svc(monkeypatch, tmp_path):
    """A service whose media root is an empty directory — i.e. nothing is mounted."""
    monkeypatch.setattr(g, "media_root", lambda: tmp_path)
    monkeypatch.setenv("MEDIA_PUBLIC_BASE", "https://podcast-api.tinboker.com/media")
    return g.GCSStorageService()


def _fake_urlopen(payload: bytes):
    class _Resp:
        def read(self):
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    return lambda url, timeout=None: _Resp()


@pytest.mark.parametrize("url", [
    f"https://podcast-api.tinboker.com/media/{BUCKET}/transcripts/h/e.json",
    f"gs://{BUCKET}/transcripts/h/e.json",
    f"https://storage.googleapis.com/{BUCKET}/transcripts/h/e.json",
])
def test_local_miss_falls_back_to_the_public_url(svc, monkeypatch, url):
    """All three historical URL forms must resolve to the SAME public URL.

    Building the fallback by string-prefixing the input double-prefixed the bucket
    for the gs:// and storage.googleapis.com forms and 404'd; it has to be rebuilt
    from the split (bucket, blob).
    """
    seen = {}

    def _urlopen(u, timeout=None):
        seen["url"] = u
        return _fake_urlopen(b'{"text": "hi"}')(u, timeout)

    monkeypatch.setattr(g.urllib.request, "urlopen", _urlopen)
    assert svc.download_text_by_gcs_url(url) == '{"text": "hi"}'
    assert seen["url"] == (
        f"https://podcast-api.tinboker.com/media/{BUCKET}/transcripts/h/e.json"
    )
    assert svc.download_transcript_by_gcs_url(url)["text"] == "hi"


def test_a_mounted_file_is_read_locally_not_fetched(monkeypatch, tmp_path):
    local = tmp_path / BUCKET / "transcripts" / "h"
    local.mkdir(parents=True)
    (local / "e.json").write_text('{"text": "from disk"}', encoding="utf-8")
    monkeypatch.setattr(g, "media_root", lambda: tmp_path)

    def _boom(*a, **k):
        raise AssertionError("must not fetch when the artifact is on disk")

    monkeypatch.setattr(g.urllib.request, "urlopen", _boom)
    svc = g.GCSStorageService()
    url = f"gs://{BUCKET}/transcripts/h/e.json"
    assert svc.download_text_by_gcs_url(url) == '{"text": "from disk"}'


def test_binary_download_also_falls_back(svc, monkeypatch, tmp_path):
    monkeypatch.setattr(g.urllib.request, "urlopen", _fake_urlopen(b"ID3audio"))
    out = svc.download_file_by_gcs_url(f"gs://{BUCKET}/mp3/h/e.mp3", tmp_path / "out.mp3")
    assert Path(out).read_bytes() == b"ID3audio"
