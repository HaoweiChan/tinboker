"""P5: the backend writes episode artifacts to local disk, not GCS."""

import os

import pytest

from src.services import gcs_content as mod
from src.services.gcs_content import GCSContentService

BUCKET = "graphfolio-articles"
BASE = "https://media.example.test/media"


@pytest.fixture
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setenv("MEDIA_PUBLIC_BASE", BASE)
    return GCSContentService()


@pytest.mark.asyncio
async def test_upload_content_lands_on_disk_with_public_url(svc, tmp_path):
    await svc.upload_content(BUCKET, "股癌/modified_summary/ep1_summary.md", "# 新摘要")

    dest = tmp_path / BUCKET / "股癌" / "modified_summary" / "ep1_summary.md"
    assert dest.read_text(encoding="utf-8") == "# 新摘要"
    assert await svc.fetch_url_content(
        f"{BASE}/{BUCKET}/股癌/modified_summary/ep1_summary.md"
    ) == "# 新摘要"


@pytest.mark.asyncio
async def test_upload_bytes_public_returns_media_url_not_gcs(svc, tmp_path):
    url = await svc.upload_bytes_public(BUCKET, "social_cards/ep1/0.png", b"\x89PNG", "image/png")

    assert url == f"{BASE}/{BUCKET}/social_cards/ep1/0.png"
    assert "storage.googleapis.com" not in url
    assert (tmp_path / BUCKET / "social_cards" / "ep1" / "0.png").read_bytes() == b"\x89PNG"


@pytest.mark.asyncio
async def test_write_is_atomic_no_partial_or_temp_file_on_failure(svc, tmp_path, monkeypatch):
    real_replace = os.replace
    monkeypatch.setattr(
        mod.os, "replace", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full"))
    )
    with pytest.raises(OSError):
        await svc.upload_content(BUCKET, "a/b.md", "boom")
    monkeypatch.setattr(mod.os, "replace", real_replace)

    d = tmp_path / BUCKET / "a"
    assert not (d / "b.md").exists()
    assert list(d.iterdir()) == []  # temp file cleaned up


@pytest.mark.asyncio
async def test_delete_blob_removes_file_and_tolerates_missing(svc, tmp_path):
    await svc.upload_content(BUCKET, "a/b.md", "x")
    await svc.delete_blob(BUCKET, "a/b.md")
    assert not (tmp_path / BUCKET / "a" / "b.md").exists()
    await svc.delete_blob(BUCKET, "a/b.md")  # idempotent


@pytest.mark.parametrize("url_for", [
    lambda b, p: f"gs://{b}/{p}",
    lambda b, p: f"https://storage.googleapis.com/{b}/{p}",
    lambda b, p: f"{BASE}/{b}/{p}",
])
@pytest.mark.asyncio
async def test_reads_resolve_legacy_and_new_urls(svc, url_for):
    """Docs written before the P5 URL rewrite still carry gs:// — must still read."""
    await svc.upload_content(BUCKET, "summaries/x.md", "內容")
    assert await svc.fetch_gcs_content(url_for(BUCKET, "summaries/x.md")) == "內容"


@pytest.mark.asyncio
async def test_missing_artifact_reads_empty_not_raises(svc):
    """EpisodeTransformer relies on "" meaning "fetch failed, keep stored value"."""
    assert await svc.fetch_gcs_content(f"gs://{BUCKET}/nope.md") == ""
    assert await svc.generate_signed_url(f"gs://{BUCKET}/nope.md") is None


@pytest.mark.asyncio
async def test_signed_url_is_now_the_public_media_url(svc):
    await svc.upload_bytes(BUCKET, "mp3/abc/ep1.mp3", b"audio", "audio/mpeg")
    assert await svc.generate_signed_url(f"gs://{BUCKET}/mp3/abc/ep1.mp3") == (
        f"{BASE}/{BUCKET}/mp3/abc/ep1.mp3"
    )


def test_default_root_falls_back_when_prod_path_absent(monkeypatch):
    """A dev checkout must not require /srv/tinboker-media to exist."""
    monkeypatch.delenv("MEDIA_STORAGE_ROOT", raising=False)
    monkeypatch.setattr(mod, "DEFAULT_MEDIA_ROOT", "/nonexistent-media-root-for-test")
    root = mod.media_root()
    assert root.name == ".media" and not str(root).startswith("/nonexistent")


@pytest.mark.asyncio
async def test_save_modified_summary_writes_locally_and_updates_doc(svc, tmp_path, monkeypatch):
    """End-to-end for the one backend write in the episode path."""
    from src.services.podcast import PodcastService

    episode = {"podcast_name": "股癌", "summary_url": f"{BASE}/{BUCKET}/summaries/h/ep1.md"}
    writes: dict = {}

    service = PodcastService.__new__(PodcastService)
    service.gcs = svc
    service.firestore_service = type("FS", (), {"get_document": staticmethod(lambda c, i: episode)})()
    service._write_episode_fields = lambda eid, updates: writes.update(updates) or _noop()
    service._invalidate_episode_cache = lambda *a: _noop()
    service.get_episode_by_id = lambda *a, **k: _noop()

    await service.save_modified_summary("股癌", "ep1", "# 編輯後", modified_by="admin")

    blob = "股癌/modified_summary/ep1_summary.md"
    assert (tmp_path / BUCKET / blob).read_text(encoding="utf-8") == "# 編輯後"
    assert writes["modified_summary_url"] == f"{BASE}/{BUCKET}/{blob}"
    assert not writes["modified_summary_url"].startswith("gs://")
    assert writes["modified_by"] == "admin"


async def _noop():
    return None


# ── P5 review follow-ups: bucket allow-list, traversal containment, upload ext ──

@pytest.mark.parametrize("bad_bucket", ["articles", "web", "tinboker-podcast-data"])
@pytest.mark.asyncio
async def test_unknown_bucket_is_rejected_never_silently_created(svc, tmp_path, bad_bucket):
    """Short-form dirs (articles/, web/) are the stale Phase-E naming — nothing
    serves them, so writing there would be silent data loss."""
    with pytest.raises(ValueError, match="Unknown media bucket"):
        mod.media_path(bad_bucket, "x.md")
    with pytest.raises(ValueError):
        await svc.upload_content(bad_bucket, "x.md", "x")
    assert not (tmp_path / bad_bucket).exists()


@pytest.mark.asyncio
async def test_unknown_bucket_degrades_on_read_paths(svc):
    """A poisoned or legacy doc URL must not 500 an episode page."""
    assert await svc.fetch_gcs_content("gs://some-other-bucket/x.md") == ""
    assert await svc.generate_signed_url("gs://some-other-bucket/x.md") is None


@pytest.mark.parametrize("blob", ["../../etc/passwd", "a/../../../outside.md"])
def test_path_traversal_is_contained(svc, blob):
    with pytest.raises(ValueError, match="escapes"):
        mod.media_path(BUCKET, blob)


@pytest.mark.asyncio
async def test_delete_blob_goes_through_the_guard(svc):
    with pytest.raises(ValueError, match="escapes"):
        await svc.delete_blob(BUCKET, "../../../tmp/victim")
    with pytest.raises(ValueError, match="Unknown media bucket"):
        await svc.delete_blob("articles", "x.md")


def test_promo_upload_extension_comes_from_ctype_not_filename():
    """Stored-XSS guard: a client filename of x.html must not decide how the media
    origin serves the bytes back (Caddy infers Content-Type from the extension)."""
    from src.routers.social import _safe_extension

    assert _safe_extension("image/png") == ".png"
    assert _safe_extension("image/jpeg") == ".jpg"
    assert _safe_extension("video/mp4") == ".mp4"


@pytest.mark.parametrize("ctype", ["image/svg+xml", "text/html", "image/x-nonsense"])
def test_promo_upload_rejects_scriptable_or_unknown_types(ctype):
    from fastapi import HTTPException

    from src.routers.social import _safe_extension

    with pytest.raises(HTTPException) as e:
        _safe_extension(ctype)
    assert e.value.status_code == 415
