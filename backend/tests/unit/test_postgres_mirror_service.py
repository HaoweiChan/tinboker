"""PostgresMirrorService — the Firestore-call → JSONB-SQL translation layer.

Every mapped FirestoreService method is asserted on the SQL text + bound params it
emits (session stubbed), because that translation is the whole risk surface: a wrong
operator silently returns the wrong episodes instead of failing.
"""
import json
from contextlib import contextmanager

import pytest

from src.services import postgres_mirror_service as pms
from src.services.postgres_mirror_service import (
    PostgresMirrorService,
    content_read_service,
    patch_episode_doc,
)


class _Result:
    def __init__(self, rows, scalar=None):
        self._rows, self._scalar = rows, scalar

    def first(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows

    def scalar(self):
        return self._scalar


class _Session:
    """Records (normalized SQL, params) per execute; replays canned rows."""

    def __init__(self, rows=None, scalar=None):
        self.calls, self.committed = [], False
        self._rows, self._scalar = rows or [], scalar

    def execute(self, stmt, params=None):
        self.calls.append((" ".join(str(stmt).split()), params or {}))
        return _Result(self._rows, self._scalar)

    def commit(self):
        self.committed = True


@pytest.fixture
def stub_session(monkeypatch):
    """Returns a factory: install(rows=..., scalar=...) -> the recording session."""

    def install(rows=None, scalar=None):
        session = _Session(rows, scalar)

        @contextmanager
        def _fake():
            yield session

        monkeypatch.setattr(pms, "mirror_session", _fake)
        return session

    return install


def _sql(session, i=0):
    return session.calls[i][0]


def _params(session, i=0):
    return session.calls[i][1]


# ── episodes ────────────────────────────────────────────────────────────


def test_get_document_selects_doc_by_pk_and_injects_id(stub_session):
    s = stub_session(rows=[({"podcast_name": "股癌"},)])
    out = PostgresMirrorService().get_document("episodes", "EP1")
    assert _sql(s) == "SELECT doc FROM firestore_mirror.episodes WHERE episode_id = :id"
    assert _params(s) == {"id": "EP1"}
    assert out == {"podcast_name": "股癌", "id": "EP1"}


def test_get_document_missing_returns_none(stub_session):
    stub_session(rows=[])
    assert PostgresMirrorService().get_document("episodes", "nope") is None


def test_get_document_unmapped_collection_raises(stub_session):
    stub_session()
    with pytest.raises(NotImplementedError, match="users"):
        PostgresMirrorService().get_document("users", "u1")


def test_get_documents_batch_uses_array_and_preserves_caller_order(stub_session):
    s = stub_session(rows=[("B", {"t": 2}), ("A", {"t": 1})])
    out = PostgresMirrorService().get_documents_batch("episodes", ["A", "B", "GONE"])
    assert "episode_id = ANY(CAST(:ids AS text[]))" in _sql(s)
    assert _params(s) == {"ids": '{"A","B","GONE"}'}
    assert [d["id"] for d in out] == ["A", "B"]  # request order, missing dropped


def test_get_documents_batch_empty_skips_sql(stub_session):
    s = stub_session()
    assert PostgresMirrorService().get_documents_batch("episodes", []) == []
    assert s.calls == []


def test_query_collection_equality_uses_promoted_column_with_order_and_limit(stub_session):
    s = stub_session(rows=[("E1", {"podcast_name": "股癌"})])
    out = PostgresMirrorService().query_collection(
        "episodes", [("podcast_name", "==", "股癌")], "created_time", "DESCENDING", 20,
    )
    assert _sql(s) == (
        "SELECT episode_id, doc FROM firestore_mirror.episodes "
        "WHERE podcast_name = :f0 ORDER BY created_time DESC NULLS LAST LIMIT :limit"
    )
    assert _params(s) == {"f0": "股癌", "limit": 20}
    assert out == [{"podcast_name": "股癌", "id": "E1"}]


def test_query_collection_array_contains_becomes_jsonb_exists(stub_session):
    s = stub_session(rows=[])
    PostgresMirrorService().query_collection(
        "episodes", [("sector_exposure_ids", "array-contains", "sector_ai")], None, None, 100,
    )
    assert "WHERE jsonb_exists(doc -> 'sector_exposure_ids', :f0)" in _sql(s)
    assert _params(s)["f0"] == "sector_ai"
    assert "ORDER BY" not in _sql(s)


def test_query_collection_unsupported_operator_fails_loud(stub_session):
    stub_session()
    with pytest.raises(NotImplementedError, match="operator"):
        PostgresMirrorService().query_collection("episodes", [("num_likes", ">", 3)])


def test_query_collection_rejects_injected_field_name(stub_session):
    stub_session()
    with pytest.raises(NotImplementedError):
        PostgresMirrorService().query_collection("episodes", [("a'; DROP TABLE x --", "==", 1)])


def test_stream_documents_projected_picks_only_requested_keys(stub_session):
    s = stub_session(rows=[("E1", {"podcast_name": "股癌"})])
    out = PostgresMirrorService().stream_documents_projected(
        "episodes", ["podcast_name", "related_tickers"],
    )
    sql = _sql(s)
    assert "jsonb_object_agg(k, e.doc -> k)" in sql
    assert "unnest(CAST(:fields AS text[]))" in sql
    assert "jsonb_exists(e.doc, k)" in sql
    assert _params(s) == {"fields": '{"podcast_name","related_tickers"}'}
    assert out == [{"podcast_name": "股癌", "id": "E1"}]


def test_get_all_documents_trending_tickers(stub_session):
    s = stub_session(rows=[("2330.TW", {"ticker": "2330"})])
    out = PostgresMirrorService().get_all_documents("trending_tickers")
    assert _sql(s) == "SELECT ticker, doc FROM firestore_mirror.trending_tickers"
    assert out == [{"ticker": "2330", "id": "2330.TW"}]


def test_get_all_documents_unmapped_collection_raises(stub_session):
    stub_session()
    with pytest.raises(NotImplementedError, match="users"):
        PostgresMirrorService().get_all_documents("users")


# ── derived inverted indices (docs/firestore-contract.md § 3.2) ─────────


def test_ticker_index_is_membership_on_related_tickers(stub_session):
    s = stub_session(rows=[("E1", 1730000000000)])
    out = PostgresMirrorService().get_subcollection_documents(
        "tickers", "NVDA", "episodes", order_by="created_time",
        direction="DESCENDING", limit=100,
    )
    assert _sql(s) == (
        "SELECT episode_id, (EXTRACT(EPOCH FROM created_time) * 1000)::bigint "
        "FROM firestore_mirror.episodes "
        "WHERE jsonb_exists(doc -> 'related_tickers', :parent) "
        "ORDER BY created_time DESC NULLS LAST LIMIT :limit"
    )
    assert _params(s) == {"parent": "NVDA", "limit": 100}
    assert out == [{"episode_id": "E1", "created_time": 1730000000000}]


def test_tag_index_normalizes_both_sides_of_the_slug(stub_session):
    s = stub_session(rows=[])
    PostgresMirrorService().get_subcollection_documents(
        "tags", "aisupplychain", "episodes", order_by="created_time", limit=50,
    )
    assert (
        "EXISTS (SELECT 1 FROM jsonb_array_elements_text(doc -> 'tags') AS t "
        "WHERE regexp_replace(lower(t), '[^a-z0-9]', '', 'g') = :parent)"
    ) in _sql(s)
    assert _params(s)["parent"] == "aisupplychain"


def test_index_rejects_unmapped_parent_collection(stub_session):
    stub_session()
    with pytest.raises(NotImplementedError):
        PostgresMirrorService().get_subcollection_documents("sectors", "x", "episodes")


def test_index_rejects_unsupported_order_by(stub_session):
    stub_session()
    with pytest.raises(NotImplementedError, match="order_by"):
        PostgresMirrorService().get_subcollection_documents(
            "tags", "ai", "episodes", order_by="num_likes",
        )


def test_count_subcollection_counts_same_predicate(stub_session):
    s = stub_session(scalar=7)
    assert PostgresMirrorService().count_subcollection_documents("tags", "ai", "episodes") == 7
    assert _sql(s).startswith("SELECT count(*) FROM firestore_mirror.episodes WHERE EXISTS")


def test_get_all_parent_documents_tags_returns_distinct_slugs(stub_session):
    s = stub_session(rows=[("ai",), ("earnings",), (None,)])
    out = PostgresMirrorService().get_all_parent_documents("tags")
    assert _sql(s) == (
        "SELECT DISTINCT regexp_replace(lower(t), '[^a-z0-9]', '', 'g') "
        "FROM firestore_mirror.episodes, jsonb_array_elements_text(doc -> 'tags') AS t"
    )
    assert out == ["ai", "earnings"]


# ── ticker_insights collection group ────────────────────────────────────


def test_collection_group_in_filter_maps_to_promoted_ticker_column(stub_session):
    s = stub_session(rows=[("EP1", "2330", {"bluf_thesis": "x"})])
    out = PostgresMirrorService().query_collection_group(
        "tickers", [("ticker", "in", ["2330", "2330.TW"])], None, None, None,
    )
    assert _sql(s) == (
        "SELECT episode_id, ticker, doc FROM firestore_mirror.ticker_insights "
        "WHERE ticker = ANY(CAST(:f0 AS text[]))"
    )
    assert _params(s) == {"f0": '{"2330","2330.TW"}'}
    assert out == [{"bluf_thesis": "x", "id": "2330", "_parent_id": "EP1"}]


def test_collection_group_podcaster_and_ordering(stub_session):
    s = stub_session(rows=[])
    PostgresMirrorService().query_collection_group(
        "tickers", [("podcaster", "==", "股癌")], "podcast_launch_time", "DESCENDING", 200,
    )
    assert "WHERE doc->>'podcaster' = :f0" in _sql(s)
    assert "ORDER BY doc->>'podcast_launch_time' DESC NULLS LAST LIMIT :limit" in _sql(s)
    assert _params(s) == {"f0": "股癌", "limit": 200}


def test_collection_group_unmapped_id_raises(stub_session):
    stub_session()
    with pytest.raises(NotImplementedError, match="notifications"):
        PostgresMirrorService().query_collection_group("notifications")


# ── writes ──────────────────────────────────────────────────────────────


def test_read_interface_refuses_writes():
    svc = PostgresMirrorService()
    with pytest.raises(NotImplementedError):
        svc.set_document("episodes", "EP1", {"a": 1}, True)
    with pytest.raises(NotImplementedError):
        svc.delete_document("episodes", "EP1")


def test_patch_episode_doc_merges_and_drops_like_firestore(stub_session, monkeypatch):
    """P4 replaced google.cloud.firestore.DELETE_FIELD with a local sentinel; the
    merge/remove semantics it stands for are unchanged."""
    from src.services.postgres_mirror_service import DELETE_FIELD

    monkeypatch.setattr(pms.settings, "use_postgres", True)
    existing = {
        "summary_content": "old",
        "modified_summary_url": "gs://x",
        "modified_at": 5,
        "related_tickers": ["2330"],
    }
    s = stub_session(rows=[(existing,)])
    assert patch_episode_doc("EP1", {
        "modified_summary_url": DELETE_FIELD,
        "modified_at": DELETE_FIELD,
        "summary_content": "new",
    }) is True
    # read-modify-write: locked SELECT, then a whole-doc UPDATE
    assert "SELECT doc FROM firestore_mirror.episodes WHERE episode_id = :id FOR UPDATE" in _sql(s, 0)
    sql, params = s.calls[1]
    assert "doc = CAST(:doc AS jsonb)" in sql
    # The promoted related_tickers column is JSONB (pipelines steps/postgres_episode.py
    # owns the DDL: `related_tickers jsonb`), so it must be assigned a plain jsonb
    # extraction. Unit tests can't execute real SQL, so pin the shape: an
    # ARRAY(SELECT jsonb_array_elements_text(...)) builds a text[] and type-errors
    # against that column on EVERY backend episode write.
    assert "related_tickers = CASE WHEN CAST(:doc AS jsonb) ? 'related_tickers' " \
           "THEN CAST(:doc AS jsonb)->'related_tickers' ELSE NULL END" in " ".join(sql.split())
    assert "ARRAY(" not in sql
    assert "jsonb_array_elements_text" not in sql
    assert json.loads(params["doc"]) == {"summary_content": "new", "related_tickers": ["2330"]}
    assert params["id"] == "EP1"
    assert s.committed


def test_patch_episode_doc_deep_merges_nested_maps(stub_session, monkeypatch):
    monkeypatch.setattr(pms.settings, "use_postgres", True)
    s = stub_session(rows=[({"social_thread": {"a": 1, "b": 2}},)])
    assert patch_episode_doc("EP1", {"social_thread": {"a": 9}}) is True
    # Firestore merge=True keeps sibling sub-keys; a shallow || would drop "b"
    assert json.loads(s.calls[1][1]["doc"]) == {"social_thread": {"a": 9, "b": 2}}


def test_patch_episode_doc_raises_on_missing_row(stub_session, monkeypatch):
    """P4: Postgres is the only content store, so an edit with nowhere to land must
    surface as a 500 rather than be logged and dropped."""
    monkeypatch.setattr(pms.settings, "use_postgres", True)
    s = stub_session(rows=[])
    with pytest.raises(RuntimeError, match="missing from firestore_mirror.episodes"):
        patch_episode_doc("EP_GONE", {"summary_content": "x"})
    assert len(s.calls) == 1  # SELECT only, no blind UPDATE
    assert not s.committed


def test_patch_episode_doc_noop_without_postgres(stub_session, monkeypatch):
    monkeypatch.setattr(pms.settings, "use_postgres", False)
    s = stub_session()
    assert patch_episode_doc("EP1", {"a": 1}) is False
    assert s.calls == []


# ── flag wiring ─────────────────────────────────────────────────────────


def test_content_read_service_follows_the_flag(monkeypatch):
    monkeypatch.setattr(pms.settings, "content_reads_from_postgres", False)
    from src.services.firestore_service import FirestoreService

    assert isinstance(content_read_service(), FirestoreService)
    monkeypatch.setattr(pms.settings, "content_reads_from_postgres", True)
    assert isinstance(content_read_service(), PostgresMirrorService)


def test_services_read_through_the_flag(monkeypatch):
    from src.services.firestore_service import FirestoreService
    from src.services.insight_service import InsightService
    from src.services.podcast import PodcastService

    monkeypatch.setattr(pms.settings, "content_reads_from_postgres", True)
    assert isinstance(PodcastService().firestore_service, PostgresMirrorService)
    assert isinstance(InsightService()._fs, PostgresMirrorService)

    monkeypatch.setattr(pms.settings, "content_reads_from_postgres", False)
    assert isinstance(PodcastService().firestore_service, FirestoreService)
    assert isinstance(InsightService()._fs, FirestoreService)


def test_content_reads_default_to_postgres():
    """P4 flipped the default: the pipelines no longer write Firestore, so the
    Firestore read path must not be what a fresh process picks."""
    from src.config import Settings

    assert Settings().content_reads_from_postgres is True


async def test_episode_write_goes_only_to_postgres_and_failures_surface(monkeypatch):
    """The Firestore half is gone (P4) — one write, and it must not be swallowed."""
    from src.services.podcast import PodcastService

    svc = object.__new__(PodcastService)
    mirrored = {}
    monkeypatch.setattr(
        "src.services.podcast.patch_episode_doc",
        lambda eid, updates: mirrored.update({"id": eid, "updates": updates}),
    )
    await svc._write_episode_fields("EP1", {"social_thread": {"post": "hi"}})
    assert mirrored == {"id": "EP1", "updates": {"social_thread": {"post": "hi"}}}

    def _boom(eid, updates):
        raise RuntimeError("content store down")

    monkeypatch.setattr("src.services.podcast.patch_episode_doc", _boom)
    with pytest.raises(RuntimeError, match="content store down"):
        await svc._write_episode_fields("EP1", {"a": 1})


# ── one live-Postgres check (skipped unless the mirror is reachable) ────


@pytest.mark.integration
def test_mirror_sql_runs_against_real_postgres():
    """The generated SQL is valid against a live firestore_mirror schema."""
    from sqlalchemy import text as _text

    try:
        with pms.mirror_session() as db:
            db.execute(_text(f"SELECT 1 FROM {pms.EPISODES} LIMIT 1")).fetchall()
    except Exception as e:
        pytest.skip(f"firestore_mirror Postgres not reachable: {e}")

    svc = PostgresMirrorService()
    rows = svc.query_collection("episodes", None, "created_time", "DESCENDING", 1)
    assert isinstance(rows, list)
    if not rows:
        pytest.skip("mirror is empty")
    ep = rows[0]
    assert svc.get_document("episodes", ep["id"])["id"] == ep["id"]
    assert [d["id"] for d in svc.get_documents_batch("episodes", [ep["id"]])] == [ep["id"]]
    assert svc.stream_documents_projected("episodes", ["podcast_name"])
    for ticker in (ep.get("related_tickers") or [])[:1]:
        refs = svc.get_subcollection_documents(
            "tickers", ticker, "episodes", "created_time", "DESCENDING", 5,
        )
        assert any(r["episode_id"] == ep["id"] for r in refs)
    svc.get_all_parent_documents("tags")
    svc.count_subcollection_documents("tags", "ai", "episodes")
