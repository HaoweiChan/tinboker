"""P5: episode artifacts land on local disk under MEDIA_STORAGE_ROOT, not GCS."""

import hashlib
import os

import pytest
from src.service import gcs_storage_service as mod
from src.service.gcs_storage_service import GCSStorageService

PODCAST = "股癌 Gooaye"
EPISODE = "ep_test_1"
BUCKET = "graphfolio-articles"
BASE = "https://media.example.test/media"


@pytest.fixture
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setenv("MEDIA_PUBLIC_BASE", BASE)
    monkeypatch.setenv("GCS_BUCKET_NAME", BUCKET)
    monkeypatch.delenv("GCS_BASE_PATH", raising=False)
    return GCSStorageService()


def _hash(name: str) -> str:
    return hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]


def test_mp3_written_to_expected_path_and_url(svc, tmp_path):
    src = tmp_path / "episode.mp3"
    src.write_bytes(b"ID3fake-audio")

    urls = svc.upload_episode_files(episode_id=EPISODE, podcast_name=PODCAST, mp3_path=src)

    rel = f"mp3/{_hash(PODCAST)}/{EPISODE}.mp3"
    assert (tmp_path / BUCKET / rel).read_bytes() == b"ID3fake-audio"
    # gs:// is dead: both fields carry the same public https URL.
    assert urls["mp3_url"] == urls["mp3_public_url"] == f"{BASE}/{BUCKET}/{rel}"
    assert "storage.googleapis.com" not in urls["mp3_url"]


def test_markdown_artifact_written_to_expected_path_and_url(svc, tmp_path):
    urls = svc.upload_episode_files(
        episode_id=EPISODE, podcast_name=PODCAST, events_markdown_content="- 事件一\n",
    )

    rel = f"events/{_hash(PODCAST)}/{EPISODE}.md"
    assert (tmp_path / BUCKET / rel).read_text(encoding="utf-8") == "- 事件一\n"
    assert urls["events_markdown_url"] == f"{BASE}/{BUCKET}/{rel}"
    assert urls["events_markdown_public_url"] == urls["events_markdown_url"]


def test_base_path_prefix_is_preserved(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setenv("MEDIA_PUBLIC_BASE", BASE)
    monkeypatch.setenv("GCS_BUCKET_NAME", BUCKET)
    monkeypatch.setenv("GCS_BASE_PATH", "podcasts")

    s = GCSStorageService()
    ok, url = s.upload_file_from_string("x", "summaries", PODCAST, EPISODE, "md")

    rel = f"podcasts/summaries/{_hash(PODCAST)}/{EPISODE}.md"
    assert ok and url == f"{BASE}/{BUCKET}/{rel}"
    assert (tmp_path / BUCKET / rel).is_file()


def test_write_is_atomic_no_partial_file_on_failure(svc, tmp_path, monkeypatch):
    """A failed write leaves no artifact and no stray temp file behind."""
    real_replace = os.replace
    monkeypatch.setattr(
        mod.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full"))
    )
    ok, url = svc.upload_file_from_string("boom", "summaries", PODCAST, EPISODE, "md")
    monkeypatch.setattr(mod.os, "replace", real_replace)

    assert (ok, url) == (False, None)
    dest_dir = tmp_path / BUCKET / "summaries" / _hash(PODCAST)
    assert not (dest_dir / f"{EPISODE}.md").exists()
    assert list(dest_dir.iterdir()) == []  # temp file cleaned up


def test_overwrite_is_visible_atomically(svc, tmp_path):
    svc.upload_file_from_string("v1", "summaries", PODCAST, EPISODE, "md")
    ok, _ = svc.upload_file_from_string(
        "v2", "summaries", PODCAST, EPISODE, "md", skip_existing=False
    )
    dest = tmp_path / BUCKET / "summaries" / _hash(PODCAST) / f"{EPISODE}.md"
    assert ok and dest.read_text() == "v2"
    assert list(dest.parent.iterdir()) == [dest]


def test_skip_existing_leaves_prior_content(svc, tmp_path):
    svc.upload_file_from_string("v1", "summaries", PODCAST, EPISODE, "md")
    svc.upload_file_from_string("v2", "summaries", PODCAST, EPISODE, "md", skip_existing=True)
    dest = tmp_path / BUCKET / "summaries" / _hash(PODCAST) / f"{EPISODE}.md"
    assert dest.read_text() == "v1"


@pytest.mark.parametrize("url_for", [
    lambda rel: f"gs://{BUCKET}/{rel}",
    lambda rel: f"https://storage.googleapis.com/{BUCKET}/{rel}",
    lambda rel: f"{BASE}/{BUCKET}/{rel}",
])
def test_reads_resolve_legacy_and_new_urls_to_local_disk(svc, tmp_path, url_for):
    rel = f"summaries/{_hash(PODCAST)}/{EPISODE}.md"
    svc.upload_file_from_string("內容", "summaries", PODCAST, EPISODE, "md")

    assert svc.download_text_by_gcs_url(url_for(rel)) == "內容"
    assert svc.blob_exists(url_for(rel)) is True


def test_cross_bucket_read_uses_sibling_directory(svc, tmp_path):
    """Legacy episodes point at podcast-data-web; it lives beside our bucket dir."""
    legacy = tmp_path / "podcast-data-web" / "summaries" / "abc" / "old.md"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("legacy", encoding="utf-8")

    assert svc.download_text_by_gcs_url("gs://podcast-data-web/summaries/abc/old.md") == "legacy"


def test_transcript_json_round_trip(svc):
    data = {"text": "hello", "sentences": [{"index": 0, "content": "hello"}]}
    urls = svc.upload_episode_files(
        episode_id=EPISODE, podcast_name=PODCAST, transcript_data=data,
    )
    got = svc.download_transcript_by_gcs_url(urls["transcript_url"])
    assert got["text"] == "hello"
    assert got["sentences"] == data["sentences"]


def test_public_url_passthrough_for_full_urls(svc):
    """Callers that strip a gs:// prefix from an already-https URL must round-trip."""
    url = f"{BASE}/{BUCKET}/mp3/x/y.mp3"
    assert svc.generate_public_url(url) == url
    assert svc.generate_gcs_url("mp3/x/y.mp3") == svc.generate_public_url("mp3/x/y.mp3")


def test_default_root_falls_back_when_prod_path_absent(monkeypatch):
    """A dev checkout must not require /srv/tinboker-media to exist."""
    monkeypatch.delenv("MEDIA_STORAGE_ROOT", raising=False)
    monkeypatch.setattr(mod, "DEFAULT_MEDIA_ROOT", "/nonexistent-media-root-for-test")
    root = mod.media_root()
    assert root.name == ".media" and not str(root).startswith("/nonexistent")


def test_written_files_are_world_readable_so_caddy_can_serve_them(svc, tmp_path):
    """mkstemp defaults to 0600; Caddy is a different user and would 403 on those."""
    src = tmp_path / "episode.mp3"
    src.write_bytes(b"ID3fake-audio")

    svc.upload_episode_files(
        episode_id=EPISODE, podcast_name=PODCAST, mp3_path=src, summary_content="# 摘要"
    )

    copied = tmp_path / BUCKET / f"mp3/{_hash(PODCAST)}/{EPISODE}.mp3"
    written = tmp_path / BUCKET / f"summaries/{_hash(PODCAST)}/{EPISODE}.md"
    assert copied.stat().st_mode & 0o004, oct(copied.stat().st_mode)
    assert written.stat().st_mode & 0o004, oct(written.stat().st_mode)
