"""Media artifacts must be readable off the VPS.

The media tree is only mounted on the VPS. Every read went straight to that path,
so the agent-driven regen (which reads an episode's stored transcript) could only
ever run there. The same artifacts are published read-only over HTTPS, so a local
miss falls back to the public URL.
"""

from pathlib import Path

import pytest

from src.service import gcs_storage_service as g


@pytest.fixture
def svc(monkeypatch, tmp_path):
    s = g.GCSStorageService()
    monkeypatch.setattr(s, "path_for_url", lambda url: tmp_path / "not-mounted.json")
    return s


def _fake_urlopen(payload: bytes):
    class _Resp:
        def read(self):
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    return lambda url, timeout=None: _Resp()


def test_local_miss_falls_back_to_the_public_url(svc, monkeypatch):
    monkeypatch.setattr(g.urllib.request, "urlopen", _fake_urlopen(b'{"text": "hi"}'))
    url = "https://podcast-api.tinboker.com/media/graphfolio-articles/transcripts/h/e.json"
    assert svc.download_text_by_gcs_url(url) == '{"text": "hi"}'
    assert svc.download_transcript_by_gcs_url(url)["text"] == "hi"


def test_a_mounted_file_is_read_locally_not_fetched(monkeypatch, tmp_path):
    local = tmp_path / "e.json"
    local.write_text('{"text": "from disk"}', encoding="utf-8")
    s = g.GCSStorageService()
    monkeypatch.setattr(s, "path_for_url", lambda url: local)

    def _boom(*a, **k):
        raise AssertionError("must not fetch when the artifact is on disk")

    monkeypatch.setattr(g.urllib.request, "urlopen", _boom)
    assert s.download_text_by_gcs_url("https://x/media/b/e.json") == '{"text": "from disk"}'


def test_binary_download_also_falls_back(svc, monkeypatch, tmp_path):
    monkeypatch.setattr(g.urllib.request, "urlopen", _fake_urlopen(b"ID3audio"))
    out = svc.download_file_by_gcs_url("https://x/media/b/e.mp3", tmp_path / "out.mp3")
    assert Path(out).read_bytes() == b"ID3audio"
