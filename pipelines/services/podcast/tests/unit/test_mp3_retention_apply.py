"""Disposable PostgreSQL proof for two-database MP3 retirement semantics."""

import hashlib
import os
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.pq import TransactionStatus
from psycopg.types.json import Jsonb
from src.service.gcs_storage_service import GCSStorageService
from src.service.mp3_retention_lock import retired_marker_path

from scripts import mp3_retention_apply as apply
from scripts import mp3_retention_guards as guards


@contextmanager
def _two_disposable_databases(dsn: str):
    if "test" not in conninfo_to_dict(dsn).get("dbname", ""):
        raise RuntimeError("MP3 integration tests require a disposable test database")
    suffix = uuid4().hex[:10]
    names = (f"mp3_mirror_test_{suffix}", f"mp3_wiki_test_{suffix}")
    with psycopg.connect(dsn, autocommit=True) as admin:
        try:
            for name in names:
                admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
            yield tuple(make_conninfo(dsn, dbname=name) for name in names)
        finally:
            for name in names:
                admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(name)
                ))


def test_apply_rejects_non_autocommit_connections_before_any_query():
    def unexpected(_statement):
        raise AssertionError("must fail before a database query")

    bad = SimpleNamespace(
        autocommit=False,
        info=SimpleNamespace(transaction_status=TransactionStatus.IDLE),
        execute=unexpected,
    )
    with pytest.raises(RuntimeError, match="autocommit"):
        apply.apply_batch(bad, bad, 1_700_000_000_000, 25)


def test_apply_skips_grace_pending_without_locking_each_path(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setenv("MEDIA_PUBLIC_BASE", "https://media.test/media")
    digest = hashlib.sha256(b"Test Show").hexdigest()[:12]
    key = f"graphfolio-articles/mp3/{digest}/old.mp3"
    url = f"https://media.test/media/{key}"
    marker = {"media_key": key, "mp3_url": url, "mp3_public_url": url,
              "staged_at_ms": 1_700_000_000_000, "ready_at_ms": 1_700_000_000_000}
    rows = [("old", {"podcast_name": "Test Show", "released_at_ms": 1_600_000_000_000,
                     apply.PENDING: marker})]

    class Connection:
        autocommit = True
        info = SimpleNamespace(transaction_status=TransactionStatus.IDLE)

        def execute(self, _statement, _params=None):
            return SimpleNamespace(fetchone=lambda: (1,))

    monkeypatch.setattr(apply, "_ready", lambda *_args: None)
    monkeypatch.setattr(apply, "_rows", lambda *_args: (rows, [], []))
    monkeypatch.setattr(apply, "_now_ms", lambda *_args: 1_700_000_001_000)
    monkeypatch.setattr(apply, "finalize", lambda *_args: pytest.fail("grace path was locked"))
    monkeypatch.setattr(apply, "stage", lambda *_args: pytest.fail("grace path was restaged"))
    assert apply.apply_batch(Connection(), Connection(), 1_700_000_001_000, 25) == (0, 0, 1, 1)


@pytest.mark.skipif(
    not os.getenv("MP3_RETENTION_TEST_DATABASE_URL"),
    reason="requires an explicitly disposable PostgreSQL database",
)
def test_two_store_stage_crash_grace_age_correction_and_unlink(tmp_path, monkeypatch):
    """Each database has its own ledger, matching the deployed topology."""
    dsn = os.environ["MP3_RETENTION_TEST_DATABASE_URL"]
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))
    monkeypatch.setenv("MEDIA_PUBLIC_BASE", "https://media.test/media")
    monkeypatch.delenv("EPISODE_DATABASE_URL", raising=False)
    cutoff = 1_700_000_000_000
    digest = hashlib.sha256(b"Test Show").hexdigest()[:12]
    key = f"graphfolio-articles/mp3/{digest}/old.mp3"
    path = tmp_path / key
    path.parent.mkdir(parents=True)
    path.write_bytes(b"audio")
    url = f"https://media.test/media/{key}"

    with _two_disposable_databases(dsn) as (mirror_dsn, wiki_dsn):
        with psycopg.connect(mirror_dsn, autocommit=True) as setup_mirror, psycopg.connect(
            wiki_dsn, autocommit=True
        ) as setup_wiki:
            setup_mirror.execute("CREATE SCHEMA firestore_mirror")
            setup_mirror.execute(
                "CREATE TABLE firestore_mirror.episodes "
                "(episode_id text PRIMARY KEY, doc jsonb NOT NULL)"
            )
            setup_wiki.execute(
                "CREATE TABLE public.episodes "
                "(id text PRIMARY KEY, mp3_url text, released_at_ms bigint)"
            )
            setup_wiki.execute(
                "CREATE TABLE public.wiki_pages "
                "(id bigint PRIMARY KEY, frontmatter jsonb NOT NULL)"
            )
            guards.install(setup_mirror, wiki=False, origin=("https", "media.test", "/media"))
            guards.install(setup_wiki, wiki=True, origin=("https", "media.test", "/media"))
            setup_mirror.execute(
                "INSERT INTO firestore_mirror.episodes VALUES (%s, %s)",
                ("old", Jsonb({"podcast_name": "Test Show", "released_at_ms": cutoff - 1,
                                "mp3_url": url, "mp3_public_url": url})),
            )
            setup_wiki.execute(
                "INSERT INTO public.episodes VALUES (%s, %s, %s)",
                ("old", url, cutoff - 1),
            )
            setup_wiki.execute(
                "INSERT INTO public.wiki_pages VALUES (%s, %s)",
                (1, Jsonb({"date": "2020-01-01", "source_urls": {"mp3": url}})),
            )

        with psycopg.connect(mirror_dsn, autocommit=True) as mirror, psycopg.connect(
            wiki_dsn, autocommit=True
        ) as wiki:
            mirror.execute("SET statement_timeout = '5s'")
            wiki.execute("SET statement_timeout = '5s'")
            wiki.execute(
                "UPDATE mp3_retention.config SET public_authority = 'other.test' WHERE id = 1"
            )
            with pytest.raises(RuntimeError, match="media origin"):
                apply.stage(path, cutoff, mirror, wiki)
            assert mirror.execute(
                "SELECT doc->>'mp3_url' FROM firestore_mirror.episodes WHERE episode_id = 'old'"
            ).fetchone()[0] == url
            assert not mirror.execute(
                "SELECT 1 FROM mp3_retention.tombstones"
            ).fetchone()
            wiki.execute(
                "UPDATE mp3_retention.config SET public_authority = 'media.test' WHERE id = 1"
            )
            with pytest.raises(RuntimeError, match="simulated crash"):
                apply.stage(
                    path, cutoff, mirror, wiki,
                    after_mirror_commit=lambda: (_ for _ in ()).throw(
                        RuntimeError("simulated crash")
                    ),
                )
            mirror_doc = mirror.execute(
                "SELECT doc FROM firestore_mirror.episodes WHERE episode_id = 'old'"
            ).fetchone()[0]
            assert mirror_doc["mp3_url"] == ""
            assert "ready_at_ms" not in mirror_doc[apply.PENDING]
            assert wiki.execute(
                "SELECT mp3_url FROM public.episodes WHERE id = 'old'"
            ).fetchone()[0] == url
            assert path.read_bytes() == b"audio"

            assert apply.stage(path, cutoff, mirror, wiki)
            assert wiki.execute(
                "SELECT mp3_url FROM public.episodes WHERE id = 'old'"
            ).fetchone()[0] is None
            assert wiki.execute(
                "SELECT frontmatter #>> '{source_urls,mp3}' "
                "FROM public.wiki_pages WHERE id = 1"
            ).fetchone()[0] is None
            assert not apply.finalize(path, cutoff, mirror, wiki)

            wiki.execute(
                "UPDATE public.episodes SET released_at_ms = %s WHERE id = 'old'",
                (cutoff,),
            )
            assert not apply.finalize(path, cutoff, mirror, wiki, grace_ms=0)
            wiki.execute(
                "UPDATE public.episodes SET released_at_ms = %s WHERE id = 'old'",
                (cutoff - 1,),
            )
            wiki.execute(
                "UPDATE public.wiki_pages SET frontmatter = jsonb_set(" 
                "frontmatter, '{date}', to_jsonb('2024-01-01'::text)) WHERE id = 1"
            )
            assert not apply.finalize(path, cutoff, mirror, wiki, grace_ms=0)
            wiki.execute(
                "UPDATE public.wiki_pages SET frontmatter = jsonb_set(" 
                "frontmatter, '{date}', to_jsonb('2020-01-01'::text)) WHERE id = 1"
            )
            real_unlink = apply._unlink_mp3

            def unlink_then_crash(target):
                real_unlink(target)
                raise RuntimeError("simulated post-unlink crash")

            monkeypatch.setattr(apply, "_unlink_mp3", unlink_then_crash)
            with pytest.raises(RuntimeError, match="post-unlink crash"):
                apply.finalize(path, cutoff, mirror, wiki, grace_ms=0)
            assert not path.exists()
            assert mirror.execute(
                "SELECT doc ? %s FROM firestore_mirror.episodes WHERE episode_id = 'old'",
                (apply.PENDING,),
            ).fetchone()[0]
            monkeypatch.setattr(apply, "_unlink_mp3", real_unlink)
            assert apply.finalize(path, cutoff, mirror, wiki, grace_ms=0)
            assert not path.exists()
            assert retired_marker_path(tmp_path, key).is_file()
            assert not apply.finalize(path, cutoff, mirror, wiki, grace_ms=0)
            source = tmp_path / "source.mp3"
            source.write_bytes(b"audio")
            assert GCSStorageService().upload_file(
                source, "mp3", "Test Show", "old"
            ) == (False, None)
