"""Boot-time DDL must not hang startup behind another session's lock (prod 502,
2026-10-01): it gives up after lock_timeout, and only a column that is really missing
stops the boot."""

from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError, ProgrammingError

from src.database import postgres

COLUMN = ("tag_registry", "kind", "VARCHAR(20) NOT NULL DEFAULT 'tag'")


class _PgError(Exception):
    def __init__(self, pgcode: str):
        self.pgcode = pgcode


@pytest.fixture
def fake_engine(monkeypatch):
    """An engine whose connection records SQL and fails statements containing `fail_on`."""
    engine = MagicMock()
    engine.executed = []
    engine.fail_on = None
    engine.error = OperationalError("stmt", {}, _PgError("55P03"))

    def execute(clause):
        sql = str(clause)
        engine.executed.append(sql)
        if engine.fail_on and engine.fail_on in sql:
            raise engine.error

    @contextmanager
    def begin():
        conn = MagicMock()
        conn.execute.side_effect = execute
        yield conn

    engine.begin = begin
    monkeypatch.setattr(postgres, "engine", engine)
    return engine


def test_boot_ddl_sets_lock_timeout_before_the_statement(fake_engine):
    assert postgres._boot_ddl("ALTER TABLE t ADD COLUMN c TEXT") is True
    assert fake_engine.executed == [
        f"SET LOCAL lock_timeout = '{postgres._BOOT_DDL_LOCK_TIMEOUT}'",
        "ALTER TABLE t ADD COLUMN c TEXT",
    ]


def test_boot_ddl_lock_timeout_warns_and_returns_false(fake_engine, caplog):
    fake_engine.fail_on = "ALTER TABLE"
    with caplog.at_level("WARNING"):
        assert postgres._boot_ddl("ALTER TABLE t ADD COLUMN c TEXT") is False
    assert "Boot DDL skipped" in caplog.text


def test_boot_ddl_other_errors_propagate(fake_engine):
    fake_engine.fail_on = "ALTER TABLE"
    fake_engine.error = ProgrammingError("stmt", {}, _PgError("42601"))
    with pytest.raises(ProgrammingError):
        postgres._boot_ddl("ALTER TABLE t ADD COLUMN c TEXT")


def test_no_alter_issued_when_columns_exist(fake_engine, monkeypatch):
    monkeypatch.setattr(postgres, "_pg_missing_columns", lambda columns: [])
    postgres._ensure_pg_columns()
    assert fake_engine.executed == []


def test_lock_timeout_on_missing_column_fails_loudly(fake_engine, monkeypatch):
    fake_engine.fail_on = "ALTER TABLE"
    monkeypatch.setattr(postgres, "_pg_missing_columns", lambda columns: [COLUMN])
    with pytest.raises(RuntimeError, match="tag_registry.kind is missing"):
        postgres._ensure_pg_columns()


def test_lock_timeout_continues_when_column_appeared_meanwhile(fake_engine, monkeypatch):
    fake_engine.fail_on = "ALTER TABLE"
    answers = iter([[COLUMN], []])  # missing at boot; present on the re-check
    monkeypatch.setattr(postgres, "_pg_missing_columns", lambda columns: next(answers))
    postgres._ensure_pg_columns()
    assert any("ALTER TABLE tag_registry" in sql for sql in fake_engine.executed)
