"""Unit tests for ``src.podcast.exporters.postgres_mirror`` — the shared DDL +
upsert SQL for the ``firestore_mirror.ticker_insights`` / ``trending_tickers``
dual-write tables, and the regen commit's ``episodes.doc`` jsonb merge.

No live Postgres: a fake cursor records ``execute()`` calls so the SQL text and
bound params can be asserted directly.
"""

from __future__ import annotations

from psycopg.types.json import Jsonb
from src.podcast.exporters import postgres_mirror as pm


class _FakeCursor:
    def __init__(self, rowcount: int = 1):
        self.executed: list[tuple[str, tuple]] = []
        self.rowcount = rowcount

    def execute(self, sql, params=None):
        self.executed.append((sql, params))


# --- DDL shape (the backend reads these exact names) -------------------------

def test_ticker_insights_ddl_declares_composite_pk():
    assert "ticker_insights" in pm.DDL_TICKER_INSIGHTS
    assert "PRIMARY KEY (episode_id, ticker)" in pm.DDL_TICKER_INSIGHTS
    assert "doc" in pm.DDL_TICKER_INSIGHTS and "jsonb" in pm.DDL_TICKER_INSIGHTS


def test_trending_tickers_ddl_declares_ticker_pk():
    assert "trending_tickers" in pm.DDL_TRENDING_TICKERS
    assert "ticker     text PRIMARY KEY" in pm.DDL_TRENDING_TICKERS


def test_episodes_mirror_indexes_cover_tags_and_related_tickers_only():
    """No created_time expression index: doc->>'created_time' is an ISO string
    (not numeric), so a ::bigint cast would fail at index build / row insert.
    Ordering uses the promoted `created_time timestamptz` column instead."""
    ddl = pm.DDL_EPISODES_MIRROR_INDEXES
    assert "gin ((doc->'tags'))" in ddl
    assert "gin ((doc->'related_tickers'))" in ddl
    assert "created_time" not in ddl


# --- upsert_ticker_insights ---------------------------------------------------

def test_upsert_ticker_insights_executes_one_upsert_per_ticker():
    cur = _FakeCursor()
    docs = {"2330": {"ticker": "2330"}, "NVDA": {"ticker": "NVDA"}}

    n = pm.upsert_ticker_insights(cur, "ep_1", docs)

    assert n == 2
    assert len(cur.executed) == 2
    for sql, params in cur.executed:
        assert "INSERT INTO" in sql and "ticker_insights" in sql
        assert "ON CONFLICT (episode_id, ticker)" in sql
        episode_id, ticker, doc = params
        assert episode_id == "ep_1"
        assert ticker in docs
        assert isinstance(doc, Jsonb)
        assert doc.obj == docs[ticker]


# --- upsert_trending_tickers ---------------------------------------------------

def test_upsert_trending_tickers_executes_one_upsert_per_ticker():
    cur = _FakeCursor()
    docs = {"2330": {"ticker": "2330", "count_all_time": 3}}

    n = pm.upsert_trending_tickers(cur, docs)

    assert n == 1
    sql, params = cur.executed[0]
    assert "ON CONFLICT (ticker)" in sql
    ticker, doc = params
    assert ticker == "2330"
    assert isinstance(doc, Jsonb)
    assert doc.obj == docs["2330"]


# --- prune_trending_tickers ----------------------------------------------------

def test_prune_trending_tickers_deletes_tickers_not_in_keep_set():
    cur = _FakeCursor(rowcount=4)

    deleted = pm.prune_trending_tickers(cur, ["2330", "NVDA"])

    assert deleted == 4
    sql, params = cur.executed[0]
    assert "DELETE FROM" in sql and "trending_tickers" in sql
    assert params == (["2330", "NVDA"],)


# --- merge_episode_doc (regen drift fix) ---------------------------------------

def test_merge_episode_doc_returns_true_when_row_exists():
    cur = _FakeCursor(rowcount=1)
    fields = {"summary_content": "new content", "tags": ["ai"]}

    merged = pm.merge_episode_doc(cur, "ep_1", fields)

    assert merged is True
    sql, params = cur.executed[0]
    assert "UPDATE" in sql and "episodes" in sql
    assert "doc = doc ||" in sql
    doc_param, episode_id = params
    assert episode_id == "ep_1"
    assert isinstance(doc_param, Jsonb)
    assert doc_param.obj == fields


def test_merge_episode_doc_returns_false_when_row_missing():
    """rowcount 0 -> no matching episode_id -> never fabricate a partial doc."""
    cur = _FakeCursor(rowcount=0)

    merged = pm.merge_episode_doc(cur, "ep_missing", {"tags": ["ai"]})

    assert merged is False
