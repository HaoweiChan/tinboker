"""Guard migration tests; the PostgreSQL case needs an explicit disposable DB."""

import json
import os
import threading
import time

import psycopg
import pytest
from psycopg import sql as pg_sql

from scripts import mp3_retention_guards as guards


def _wait_blocked(dsn: str, pid: int) -> bool:
    """Prove the other backend reached PostgreSQL's lock wait before release."""
    deadline = time.monotonic() + 5
    with psycopg.connect(dsn, autocommit=True) as observer:
        while time.monotonic() < deadline:
            blockers = observer.execute(
                "SELECT pg_blocking_pids(%s)", (pid,)
            ).fetchone()[0]
            if blockers:
                return True
            time.sleep(0.02)
    return False


def test_public_origin_is_normalized_and_credential_free(monkeypatch):
    monkeypatch.setattr(guards, "public_base", lambda: "https://MEDIA.TEST:443/media")
    assert guards._public_origin() == ("https", "media.test", "/media")
    monkeypatch.setattr(guards, "public_base", lambda: "https://user:pass@media.test/media")
    with pytest.raises(ValueError):
        guards._public_origin()


def test_install_is_one_transaction_per_database():
    calls = []

    class Cursor:
        last_sql = ""

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params=None):
            calls.append((sql, params))
            self.last_sql = sql
            return self

        def fetchone(self):
            if "pg_get_userbyid" in self.last_sql:
                return (True,)
            return None

    class Connection:
        def transaction(self):
            calls.append(("BEGIN", None))
            return Cursor()

        def cursor(self):
            return Cursor()

    guards.install(Connection(), wiki=False, origin=("https", "media.test", "/media"))
    assert calls[0][0] == "BEGIN"
    assert calls[1][0].startswith("LOCK TABLE firestore_mirror.episodes")
    assert calls[3][0] == guards.COMMON_SQL
    assert any(params == ("https", "media.test", "/media") for _, params in calls)
    assert calls[-1][0] == guards.MIRROR_SQL
    assert "INSERT INTO mp3_retention.tombstones" not in " ".join(sql for sql, _ in calls)


def test_install_rejects_non_owner_before_schema_ddl():
    calls = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, statement, params=None):
            calls.append(statement)
            return self

        def fetchone(self):
            return (False,)

    class Connection:
        def transaction(self):
            return Cursor()

        def cursor(self):
            return Cursor()

    with pytest.raises(RuntimeError, match="must own"):
        guards.install(Connection(), wiki=False, origin=("https", "media.test", "/media"))
    assert guards.COMMON_SQL not in calls


@pytest.mark.skipif(
    not os.getenv("MP3_RETENTION_TEST_DATABASE_URL"),
    reason="requires an explicitly disposable PostgreSQL database",
)
def test_postgres_guards_aliases_and_late_writes():
    """Run with a throwaway DB; all DDL/data rolls back when this test exits."""
    class RollbackFixture(Exception):
        pass

    try:
        with psycopg.connect(os.environ["MP3_RETENTION_TEST_DATABASE_URL"]) as conn:
            with conn.transaction():
                conn.execute("CREATE SCHEMA IF NOT EXISTS firestore_mirror")
                conn.execute(
                    "CREATE TABLE firestore_mirror.episodes "
                    "(episode_id text PRIMARY KEY, doc jsonb NOT NULL)"
                )
                conn.execute("CREATE TABLE public.episodes (id text PRIMARY KEY, mp3_url text)")
                conn.execute(
                    "CREATE TABLE public.wiki_pages "
                    "(id bigint PRIMARY KEY, frontmatter jsonb NOT NULL)"
                )
                origin = ("https", "media.test", "/media")
                guards.install(conn, wiki=False, origin=origin)
                guards.install(conn, wiki=True, origin=origin)
                guards.install(conn, wiki=True, origin=origin)  # repeatable migration

                key = "graphfolio-articles/mp3/hash/old.mp3"
                canonical = "https://media.test/media/" + key
                aliases = (
                    canonical + "#t=30",
                    canonical + "?download=1",
                    canonical.replace("/mp3/", "/%6dp3/"),
                    canonical.replace("https://media.test/", "HTTPS://MEDIA.TEST:443/"),
                    canonical.replace("https://media.test/", "https://user@media.test/"),
                    canonical.replace("https://media.test/", "https://media.test./"),
                    canonical.replace("https://media.test/", "http://media.test/"),
                    canonical.replace("https://media.test/", "https://media.test:0443/"),
                    canonical.replace("https://media.test/", "http://media.test:00080/"),
                    canonical.replace("https:", ""),
                    "gs://" + key,
                    "https://storage.googleapis.com/" + key,
                )
                for alias in aliases:
                    assert conn.execute(
                        "SELECT mp3_retention.media_key(%s)", (alias,)
                    ).fetchone()[0] == key
                malformed = (
                    "https:" + chr(92) + "media.test" + chr(92) + "media" + chr(92) + key,
                    "https://media%2Etest/media/" + key,
                    canonical + "\n",
                    "https://media.test/media/graphfolio-articles/mp3/hash/%2e%2e/old.mp3",
                )
                for url in malformed:
                    with pytest.raises(psycopg.errors.RaiseException), conn.transaction():
                        conn.execute("SELECT mp3_retention.media_key(%s)", (url,))

                conn.execute(
                    "INSERT INTO firestore_mirror.episodes VALUES (%s, %s::jsonb)",
                    ("existing", json.dumps({"mp3_url": canonical})),
                )
                conn.execute("INSERT INTO public.episodes VALUES (%s, NULL)", ("empty",))
                conn.execute("INSERT INTO public.wiki_pages VALUES (%s, '{}'::jsonb)", (2,))
                conn.execute(
                    "INSERT INTO public.episodes VALUES (%s, %s)",
                    ("legacy-malformed", "https://media.test/media/bad%ZZ"),
                )  # empty ledger leaves existing ingest behavior unchanged
                conn.execute(
                    "INSERT INTO mp3_retention.tombstones (media_key) VALUES (%s)", (key,)
                )
                conn.execute(
                    "UPDATE firestore_mirror.episodes SET doc = doc || %s::jsonb "
                    "WHERE episode_id = 'existing'",
                    (json.dumps({"title": "updated"}),),
                )  # metadata-only updates remain possible

                statements = (
                    ("INSERT INTO firestore_mirror.episodes VALUES (%s, %s::jsonb)",
                     ("late-primary", json.dumps({"mp3_url": aliases[0]}))),
                    ("INSERT INTO firestore_mirror.episodes VALUES (%s, %s::jsonb)",
                     ("late", json.dumps({"mp3_public_url": aliases[0]}))),
                    ("INSERT INTO public.episodes VALUES (%s, %s)", ("late", aliases[2])),
                    ("INSERT INTO public.wiki_pages VALUES (%s, %s::jsonb)",
                     (1, json.dumps({"source_urls": {"mp3": aliases[3]}}))),
                    ("INSERT INTO public.episodes VALUES (%s, %s)", ("userinfo", aliases[4])),
                    ("INSERT INTO public.episodes VALUES (%s, %s)", ("trailing-dot", aliases[5])),
                    ("INSERT INTO public.episodes VALUES (%s, %s)", ("http", aliases[6])),
                    ("INSERT INTO public.episodes VALUES (%s, %s)", ("port-443", aliases[7])),
                    ("INSERT INTO public.episodes VALUES (%s, %s)", ("port-80", aliases[8])),
                    ("INSERT INTO public.episodes VALUES (%s, %s)", ("protocol-relative", aliases[9])),
                    ("UPDATE public.episodes SET mp3_url = %s WHERE id = 'empty'", (aliases[1],)),
                    ("UPDATE public.wiki_pages SET frontmatter = %s::jsonb WHERE id = 2",
                     (json.dumps({"source_urls": {"mp3": canonical}}),)),
                )
                for sql, params in statements:
                    with pytest.raises(psycopg.errors.RaiseException), conn.transaction():
                        conn.execute(sql, params)
                with pytest.raises(psycopg.errors.RaiseException), conn.transaction():
                    conn.execute("DELETE FROM mp3_retention.tombstones WHERE media_key = %s", (key,))
                with pytest.raises(psycopg.errors.RaiseException), conn.transaction():
                    conn.execute(
                        "UPDATE mp3_retention.tombstones SET media_key = %s WHERE media_key = %s",
                        ("other", key),
                    )
                with pytest.raises(psycopg.errors.RaiseException), conn.transaction():
                    conn.execute("TRUNCATE mp3_retention.tombstones")
                raise RollbackFixture()
    except RollbackFixture:
        pass


@pytest.mark.skipif(
    not os.getenv("MP3_RETENTION_TEST_DATABASE_URL"),
    reason="requires an explicitly disposable PostgreSQL database",
)
def test_non_superuser_table_owner_can_install_and_write():
    """The runtime owner can use INVOKER guards without PUBLIC table grants."""
    class RollbackFixture(Exception):
        pass

    role = "mp3_retention_test_owner"
    dsn = os.environ["MP3_RETENTION_TEST_DATABASE_URL"]
    try:
        with psycopg.connect(dsn) as conn:
            with conn.transaction():
                conn.execute(pg_sql.SQL("CREATE ROLE {} NOLOGIN").format(pg_sql.Identifier(role)))
                db_name = conn.execute("SELECT current_database()").fetchone()[0]
                conn.execute(
                    pg_sql.SQL("GRANT CREATE ON DATABASE {} TO {}").format(
                        pg_sql.Identifier(db_name), pg_sql.Identifier(role)
                    )
                )
                conn.execute(
                    pg_sql.SQL("GRANT CREATE ON SCHEMA public TO {}").format(pg_sql.Identifier(role))
                )
                conn.execute(pg_sql.SQL("SET ROLE {}").format(pg_sql.Identifier(role)))
                conn.execute("CREATE SCHEMA firestore_mirror")
                conn.execute(
                    "CREATE TABLE firestore_mirror.episodes "
                    "(episode_id text PRIMARY KEY, doc jsonb NOT NULL)"
                )
                conn.execute("CREATE TABLE public.episodes (id text PRIMARY KEY, mp3_url text)")
                conn.execute(
                    "CREATE TABLE public.wiki_pages "
                    "(id bigint PRIMARY KEY, frontmatter jsonb NOT NULL)"
                )
                origin = ("https", "media.test", "/media")
                guards.install(conn, wiki=False, origin=origin)
                guards.install(conn, wiki=True, origin=origin)
                key = "graphfolio-articles/mp3/hash/old.mp3"
                conn.execute(
                    "INSERT INTO mp3_retention.tombstones (media_key) VALUES (%s)", (key,)
                )
                with pytest.raises(psycopg.errors.RaiseException), conn.transaction():
                    conn.execute(
                        "INSERT INTO public.episodes VALUES (%s, %s)",
                        ("old", "https://media.test/media/" + key),
                    )
                conn.execute("INSERT INTO public.episodes VALUES ('new', NULL)")
                conn.execute("RESET ROLE")
                raise RollbackFixture()
    except RollbackFixture:
        pass


@pytest.mark.skipif(
    not os.getenv("MP3_RETENTION_TEST_DATABASE_URL"),
    reason="requires an explicitly disposable PostgreSQL database",
)
def test_postgres_table_lock_orders_tombstone_and_writers():
    """A writer on either side of the retirement table lock is serialized."""
    dsn = os.environ["MP3_RETENTION_TEST_DATABASE_URL"]
    with psycopg.connect(dsn) as conn:
        conn.execute("CREATE SCHEMA IF NOT EXISTS firestore_mirror")
        conn.execute(
            "CREATE TABLE firestore_mirror.episodes "
            "(episode_id text PRIMARY KEY, doc jsonb NOT NULL)"
        )
        guards.install(conn, wiki=False, origin=("https", "media.test", "/media"))

    key = "graphfolio-articles/mp3/hash/old.mp3"
    url = "https://media.test/media/" + key
    early = psycopg.connect(dsn)
    try:
        early.execute(
            "INSERT INTO firestore_mirror.episodes VALUES (%s, %s::jsonb)",
            ("early", json.dumps({"mp3_url": url})),
        )
        entered = threading.Event()
        finished = threading.Event()
        retire_pid = []
        errors = []

        def retire():
            try:
                with psycopg.connect(dsn) as conn:
                    retire_pid.append(conn.execute("SELECT pg_backend_pid()").fetchone()[0])
                    entered.set()
                    conn.execute("LOCK TABLE firestore_mirror.episodes IN SHARE ROW EXCLUSIVE MODE")
                    conn.execute(
                        "INSERT INTO mp3_retention.tombstones (media_key) VALUES (%s)", (key,)
                    )
                    conn.execute(
                        "UPDATE firestore_mirror.episodes SET doc = doc - 'mp3_url' "
                        "WHERE episode_id = 'early'"
                    )
            except Exception as exc:  # surfaced in the test thread
                errors.append(exc)
            finally:
                finished.set()

        worker = threading.Thread(target=retire)
        worker.start()
        assert entered.wait(2)
        assert _wait_blocked(dsn, retire_pid[0])  # early writer's lock wins first
        early.commit()
        worker.join(timeout=5)
        assert finished.is_set() and not errors
        with psycopg.connect(dsn) as conn:
            with pytest.raises(psycopg.errors.RaiseException), conn.transaction():
                conn.execute(
                    "INSERT INTO firestore_mirror.episodes VALUES (%s, %s::jsonb)",
                    ("late", json.dumps({"mp3_url": url + "#t=30"})),
                )

        # Reset only the disposable test ledger so the next race crosses its
        # first empty -> nonempty transition, not merely a second tombstone.
        with psycopg.connect(dsn) as reset:
            reset.execute("DROP SCHEMA mp3_retention CASCADE")
            guards.install(reset, wiki=False, origin=("https", "media.test", "/media"))

        second_key = "graphfolio-articles/mp3/hash/second.mp3"
        second_url = "https://media.test/media/" + second_key
        started = threading.Event()
        attempted = threading.Event()
        writer_pid = []
        writer_errors = []

        def late_writer():
            try:
                with psycopg.connect(dsn) as conn:
                    writer_pid.append(conn.execute("SELECT pg_backend_pid()").fetchone()[0])
                    started.set()
                    conn.execute(
                        "INSERT INTO firestore_mirror.episodes VALUES (%s, %s::jsonb)",
                        ("second", json.dumps({"mp3_public_url": second_url})),
                    )
            except Exception as exc:  # surfaced in the test thread
                writer_errors.append(exc)
            finally:
                attempted.set()

        with psycopg.connect(dsn) as retiring:
            retiring.execute("LOCK TABLE firestore_mirror.episodes IN SHARE ROW EXCLUSIVE MODE")
            retiring.execute(
                "INSERT INTO mp3_retention.tombstones (media_key) VALUES (%s)", (second_key,)
            )
            writer = threading.Thread(target=late_writer)
            writer.start()
            assert started.wait(2)
            assert _wait_blocked(dsn, writer_pid[0])  # retirement lock wins first
        writer.join(timeout=5)
        assert attempted.is_set()
        assert len(writer_errors) == 1 and isinstance(
            writer_errors[0], psycopg.errors.RaiseException
        )
    finally:
        early.close()
        with psycopg.connect(dsn) as conn:
            conn.execute("DROP SCHEMA IF EXISTS mp3_retention CASCADE")
            conn.execute("DROP TABLE IF EXISTS firestore_mirror.episodes")
            conn.execute("DROP SCHEMA IF EXISTS firestore_mirror")
