"""Publication-date MP3 retention never deletes or recreates old audio by accident."""

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from src.pipeline.config import PipelineConfig
from src.pipeline.episode_data import EpisodeData
from src.pipeline.steps.gcs_upload import upload_to_gcs
from src.pipeline.utils import required_artifact_urls, retain_episode_audio
from src.podcast.orchestrator import _filter_unprocessed_episodes

from scripts import prune_mp3


def _doc(episode_id, published_ms, url):
    return {
        "podcast_name": "Test Show",
        "released_at_ms": published_ms,
        "mp3_url": url,
        "mp3_public_url": url,
    }


def test_plan_only_includes_expired_referenced_mp3s(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setenv("MEDIA_PUBLIC_BASE", "https://media.test/media")
    digest = hashlib.sha256(b"Test Show").hexdigest()[:12]
    path = tmp_path / "graphfolio-articles" / "mp3" / digest / "old.mp3"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"audio")
    url = f"https://media.test/media/graphfolio-articles/mp3/{digest}/old.mp3"
    cutoff = 1_700_000_000_000
    old = _doc("old", cutoff - 1, url)
    def candidates(rows):
        return prune_mp3.plan(rows, cutoff)[0]

    assert candidates([("old", old)]) == [(path, ["old"], 5)]
    assert candidates([("old", {**old, "released_at_ms": None})]) == []
    assert candidates([("old", {**old, "released_at_ms": cutoff})]) == []
    assert candidates([("old", {**old, "podcast_name": "wrong"})]) == []
    assert candidates([("old", {**old, "mp3_public_url": "https://elsewhere/x.mp3"})]) == []
    assert candidates([("old", old), ("new", _doc("new", cutoff, url))]) == []
    assert candidates([("old", old), ("unknown", _doc("unknown", None, url))]) == []
    public_only = {**old, "mp3_url": ""}
    assert candidates([("old", public_only)]) == [(path, ["old"], 5)]
    assert candidates([("old", old), ("new", {**public_only, "released_at_ms": cutoff})]) == []
    assert candidates([("old", old), ("unknown", {**public_only, "released_at_ms": None})]) == []
    assert candidates([("old", {**old, "mp3_public_url": "broken"})]) == []
    # The malformed primary URL must not hide the valid public reference.
    malformed = {**old, "mp3_url": "gs://unsupported-bucket/x.mp3", "mp3_public_url": url}
    assert candidates([("old", old), ("other", malformed)]) == []
    legacy = "https://media.test/media/articles/mp3/old.mp3"
    assert candidates([("old", old), ("recent", _doc("recent", cutoff, legacy))]) == []
    for alias in (
        url + "#t=30",
        url.replace("/mp3/", "/%6dp3/"),
        url.replace("https://media.test/", "HTTPS://MEDIA.TEST:443/"),
        url.replace("https://media.test/", "https://user@media.test/"),
        url.replace("https://media.test/", "https://media.test./"),
        url.replace("https://media.test/", "http://media.test:00080/"),
        url.replace("https:", ""),
    ):
        assert candidates([("old", old), ("recent", _doc("recent", cutoff, alias))]) == []
        assert candidates([("old", old), ("undated", _doc("undated", None, alias))]) == []
    assert path.read_bytes() == b"audio"  # planning never mutates files
    path.unlink()
    assert prune_mp3.plan([("old", old)], cutoff) == ([], 1)


def test_pending_report_counts_only_existing_regular_files(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setenv("MEDIA_PUBLIC_BASE", "https://media.test/media")
    digest = hashlib.sha256(b"Test Show").hexdigest()[:12]
    directory = tmp_path / "graphfolio-articles" / "mp3" / digest
    directory.mkdir(parents=True)
    path = directory / "old.mp3"
    path.write_bytes(b"audio")
    url = f"https://media.test/media/graphfolio-articles/mp3/{digest}/old.mp3"
    staged = _doc("old", 1_600_000_000_000, "")
    staged[prune_mp3.PENDING] = {"mp3_url": url, "mp3_public_url": url,
                                  "staged_at_ms": 1_700_000_000_000}
    assert prune_mp3.pending_report([("old", staged)]) == [(path, 5)]
    path.unlink()
    assert prune_mp3.pending_report([("old", staged)]) == []


def test_cross_store_audit_blocks_shared_and_ambiguous_references(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setenv("MEDIA_PUBLIC_BASE", "https://media.test/media")
    digest = hashlib.sha256(b"Test Show").hexdigest()[:12]
    path = tmp_path / "graphfolio-articles" / "mp3" / digest / "old.mp3"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"audio")
    url = f"https://media.test/media/graphfolio-articles/mp3/{digest}/old.mp3"
    cutoff = 1_700_000_000_000
    candidate = [(path, ["old"], 5)]

    def audit(content=(), wiki=()):
        return prune_mp3.audit_cross_store(candidate, list(content), list(wiki), cutoff)

    old_content = ("old", url, cutoff - 1)
    old_wiki = (1, {"date": "2020-01-01", "source_urls": {"mp3": url}})
    assert audit([old_content], [old_wiki]) == (candidate, {})
    assert audit([("old", url, cutoff)], [old_wiki])[1] == {"shared_or_dated_content": 1}
    assert audit([("other", url, cutoff - 1)], [old_wiki])[1] == {
        "shared_or_dated_content": 1
    }
    assert audit([old_content], [(1, {"date": "2024-01-01", "source_urls": {"mp3": url}})])[1] == {
        "recent_or_undated_wiki": 1
    }
    assert audit([old_content], [(1, {"source_urls": {"mp3": url}})])[0] == []
    legacy = "https://media.test/media/articles/mp3/old.mp3"
    assert audit([("old", legacy, cutoff - 1)], [old_wiki])[1] == {
        "ambiguous_legacy_url": 1
    }
    assert audit([("other", "https://[broken/other.mp3", None)], [old_wiki]) == (
        candidate, {}
    )
    assert audit([("other", "https://[broken/old.mp3", None)], [old_wiki])[1] == {
        "ambiguous_legacy_url": 1
    }
    assert path.exists()  # audit is read-only


def test_mutation_is_disabled_and_media_root_must_be_explicit(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["prune_mp3.py", "--apply"])
    with pytest.raises(SystemExit):
        prune_mp3.main()
    assert "--apply is disabled" in capsys.readouterr().err

    monkeypatch.setattr("sys.argv", ["prune_mp3.py"])
    monkeypatch.delenv("MEDIA_STORAGE_ROOT", raising=False)
    with pytest.raises(SystemExit):
        prune_mp3.main()
    assert "MEDIA_STORAGE_ROOT must explicitly point" in capsys.readouterr().err


def test_database_failure_does_not_print_credentials(tmp_path, monkeypatch, capsys):
    from src import secrets_bootstrap

    monkeypatch.setattr("sys.argv", ["prune_mp3.py"])
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setenv("EPISODE_DATABASE_URL", "postgresql://user:fake-secret@localhost/db")
    monkeypatch.setattr(secrets_bootstrap, "bootstrap", lambda: None)
    monkeypatch.setattr(prune_mp3, "libpq_url", lambda url: url)

    def fail(_url):
        raise RuntimeError("connection failed with fake-secret")

    monkeypatch.setattr(prune_mp3.psycopg, "connect", fail)
    with pytest.raises(SystemExit) as exc:
        prune_mp3.main()
    assert exc.value.code == 1
    assert "fake-secret" not in capsys.readouterr().err


def test_ingest_age_guard_skips_old_audio_and_requires_no_mp3(monkeypatch, tmp_path):
    monkeypatch.setenv("PODCAST_MP3_RETENTION_DAYS", "90")
    now = datetime.now(timezone.utc)
    old = {"title": "Old", "datePublished": (now - timedelta(days=91)).isoformat()}
    recent = {"title": "New", "datePublished": (now - timedelta(days=89)).isoformat()}
    assert not retain_episode_audio(old, True, now=now)
    assert retain_episode_audio(recent, True, now=now)
    assert retain_episode_audio({"title": "Undated"}, True, now=now)
    stored_old = {"title": "Stored", "released_at_ms": int((now - timedelta(days=91)).timestamp() * 1000)}
    assert not retain_episode_audio(stored_old, True, now=now)

    processed = SimpleNamespace(firebase_service=SimpleNamespace(
        get_episode_by_fields=lambda **kwargs: {
            "transcript_url": "t", "summary_url": "s", "summary_image_url": "i",
        },
    ))
    def required(episode):
        return required_artifact_urls(store_audio=retain_episode_audio(episode, True, now=now))
    assert _filter_unprocessed_episodes([old, recent], "Test Show", 2, processed, required) == [recent]

    captured = []

    class Storage:
        def upload_episode_files(self, **kwargs):
            captured.append(kwargs["mp3_path"])
            return {"transcript_url": "https://media.test/t.json"}

    config = PipelineConfig(config_file=Path("shows.json"), podcast_name="Test Show", podcast_link="x")
    services = SimpleNamespace(gcs_service=Storage(), firebase_service=None)
    mp3 = tmp_path / "download.mp3"
    mp3.write_bytes(b"audio")
    for api_data in (old, recent):
        data = EpisodeData(api_data=api_data, podcast_name="Test Show", language="en")
        data.episode_id = api_data["title"]
        data.mp3_path = mp3
        upload_to_gcs(config, services, data)
    assert captured == [None, mp3]


def test_episode_id_rerun_carries_persisted_release_time(monkeypatch):
    from src.podcast import firestore_reprocessor

    seen = []

    class Processor:
        def __init__(self, config, services):
            pass

        def process_episode(self, api_data):
            seen.append(api_data)
            return True

    monkeypatch.setattr(firestore_reprocessor, "EpisodeProcessor", Processor)
    config = PipelineConfig(config_file=Path("shows.json"), podcast_name="", podcast_link="")
    assert firestore_reprocessor.process_firestore_episode(
        {"podcast_name": "Test Show", "episode_title": "Old", "released_at_ms": 1_600_000_000_000},
        "old", config_file=Path("shows.json"), rerun_from=None, transcript_service="groq",
        use_file_mode=False, reuse_existing_transcript=False, base_config=config,
        service_container=SimpleNamespace(gcs_service=None), podcast_config_mapping={}, podcasts=[],
    )
    assert seen[0]["released_at_ms"] == 1_600_000_000_000
