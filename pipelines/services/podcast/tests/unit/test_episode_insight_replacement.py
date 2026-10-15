"""Invariant-gap: an explicit episode snapshot replaces exactly that episode, atomically."""
from copy import deepcopy

import pytest
from src.podcast.exporters import ticker_insights as exporter


class Database:
    def __init__(self, fail_insert=False):
        self.rows = {('target', 'OLD'): {'ticker': 'OLD'}, ('target', 'KEEP'): {'thesis': 'old'}, ('other', 'OLD'): {'thesis': 'untouched'}}
        self.fail_insert = fail_insert
        self.options = None

    def connect(self, url, **options):
        self.options = options
        return self

    def __enter__(self):
        self.before = deepcopy(self.rows)
        return self

    def __exit__(self, kind, value, traceback):
        if kind:
            self.rows = self.before

    def cursor(self):
        from contextlib import nullcontext
        return nullcontext(self)

    def execute(self, sql, params=None):
        if sql.lstrip().startswith('DELETE'):
            assert 'WHERE episode_id = %s' in sql
            self.rows = {key: val for key, val in self.rows.items() if key[0] != params[0]}
        elif sql.lstrip().startswith('INSERT'):
            if self.fail_insert:
                raise RuntimeError('insert failed')
            episode_id, ticker, doc = params
            self.rows[episode_id, ticker] = doc.obj


@pytest.mark.parametrize('docs', [{}, {'KEEP': {'ticker': 'KEEP', 'thesis': 'new'}}])
def test_episode_replacement_removes_orphans_and_preserves_other_episode(monkeypatch, docs):
    import psycopg
    db = Database()
    monkeypatch.setenv('EPISODE_DATABASE_URL', 'postgresql://test-only')
    monkeypatch.setattr(psycopg, 'connect', db.connect)
    assert exporter.replace_episode_insights_postgres('target', docs) == len(docs)
    assert db.rows == {('other', 'OLD'): {'thesis': 'untouched'}, **{('target', k): v for k, v in docs.items()}}
    assert db.options.get('autocommit', False) is False


def test_replacement_failure_rolls_back_deleted_rows(monkeypatch):
    import psycopg
    db = Database(fail_insert=True)
    before = deepcopy(db.rows)
    monkeypatch.setenv('EPISODE_DATABASE_URL', 'postgresql://test-only')
    monkeypatch.setattr(psycopg, 'connect', db.connect)
    with pytest.raises(RuntimeError, match='insert failed'):
        exporter.replace_episode_insights_postgres('target', {'NEW': {'ticker': 'NEW'}})
    assert db.rows == before


def test_replacement_rejects_missing_episode_scope():
    with pytest.raises(ValueError, match='episode_id'):
        exporter.replace_episode_insights_postgres('', {})
