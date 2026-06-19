"""Unit tests for the trending_tickers aggregation.

Covers spec § 5 invariants: rolling 30d/90d/all_time counts, sentiment_label
derived from the average score, podcaster/episode tallies, and ordering.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.podcast.exporters.trending_tickers import (
    aggregate_trending,
    delete_orphaned_bare_docs,
    market_collision_doc_ids,
    touched_ticker_markets,
    validate_trending_document,
    write_trending,
)

_NOW = datetime(2026, 5, 14, 0, 0, tzinfo=timezone.utc)


def _insight(
    ticker: str,
    score: float,
    days_ago: int,
    podcaster: str,
    episode_id: str,
    market: str | None = None,
):
    launch = _NOW - timedelta(days=days_ago)
    row = {
        "ticker": ticker,
        "sentiment_score": score,
        "podcaster": podcaster,
        "podcast_launch_time": launch.isoformat().replace("+00:00", "Z"),
        "episode_id": episode_id,
    }
    if market:
        row["market"] = market
    return row


def test_rolling_windows_count_correctly():
    rows = [
        _insight("NVDA", 0.85, days_ago=5, podcaster="股癌", episode_id="e1"),
        _insight("NVDA", 0.80, days_ago=40, podcaster="股癌", episode_id="e2"),
        _insight("NVDA", 0.75, days_ago=200, podcaster="M觀點", episode_id="e3"),
    ]
    docs = aggregate_trending(rows, now=_NOW)
    assert docs["NVDA"]["count_30d"] == 1
    assert docs["NVDA"]["count_90d"] == 2
    assert docs["NVDA"]["count_all_time"] == 3


def test_sentiment_label_uses_average_across_mentions():
    rows = [
        _insight("AMD", 0.95, days_ago=10, podcaster="股癌", episode_id="e1"),
        _insight("AMD", 0.65, days_ago=20, podcaster="股癌", episode_id="e2"),
    ]
    docs = aggregate_trending(rows, now=_NOW)
    # avg = 0.80 → STRONG_BULLISH per spec § 4.2
    assert docs["AMD"]["sentiment_label"] == "STRONG_BULLISH"
    assert docs["AMD"]["sentiment_score"] == 0.80


def test_top_podcasters_sorted_desc_by_count():
    rows = [
        _insight("TSM", 0.7, days_ago=1, podcaster="股癌", episode_id="e1"),
        _insight("TSM", 0.7, days_ago=2, podcaster="股癌", episode_id="e2"),
        _insight("TSM", 0.7, days_ago=3, podcaster="股癌", episode_id="e3"),
        _insight("TSM", 0.7, days_ago=4, podcaster="M觀點", episode_id="e4"),
        _insight("TSM", 0.7, days_ago=5, podcaster="財經一路發", episode_id="e5"),
    ]
    docs = aggregate_trending(rows, now=_NOW, top_n=3)
    podcasters = docs["TSM"]["top_podcasters"]
    assert podcasters[0] == {"name": "股癌", "count": 3}
    assert podcasters[1]["count"] == 1
    assert podcasters[2]["count"] == 1
    assert len(podcasters) == 3


def test_top_episodes_most_recent_first():
    rows = [
        _insight("MSFT", 0.7, days_ago=10, podcaster="股癌", episode_id="old"),
        _insight("MSFT", 0.7, days_ago=2, podcaster="股癌", episode_id="recent"),
        _insight("MSFT", 0.7, days_ago=5, podcaster="股癌", episode_id="middle"),
    ]
    docs = aggregate_trending(rows, now=_NOW, top_n=2)
    ids = [ep["episode_id"] for ep in docs["MSFT"]["top_episodes"]]
    assert ids == ["recent", "middle"]


def test_last_mentioned_is_max_launch_time():
    rows = [
        _insight("AAPL", 0.5, days_ago=30, podcaster="股癌", episode_id="e1"),
        _insight("AAPL", 0.5, days_ago=2, podcaster="股癌", episode_id="e2"),
    ]
    docs = aggregate_trending(rows, now=_NOW)
    expected = (_NOW - timedelta(days=2)).isoformat().replace("+00:00", "Z")
    assert docs["AAPL"]["last_mentioned"] == expected


def test_skips_rows_without_ticker():
    rows = [
        {"sentiment_score": 0.7, "podcaster": "x", "podcast_launch_time": _NOW.isoformat()},
        _insight("GOOG", 0.7, days_ago=1, podcaster="x", episode_id="e1"),
    ]
    docs = aggregate_trending(rows, now=_NOW)
    assert set(docs) == {"GOOG"}


def test_aggregates_by_ticker_and_market_metadata():
    rows = [
        _insight("TSM", 0.7, 1, "股癌", "us", market="US"),
        _insight("2330", 0.8, 1, "股癌", "tw", market="TW"),
    ]
    docs = aggregate_trending(rows, now=_NOW)
    assert docs["TSM"]["market"] == "US"
    assert docs["2330.TW"]["ticker"] == "2330"
    assert docs["2330.TW"]["market"] == "TW"


def test_collision_keeps_us_doc_id_exact_and_suffixes_non_us():
    rows = [
        _insight("ABC", 0.7, 1, "股癌", "us", market="US"),
        _insight("ABC", 0.6, 1, "股癌", "tw", market="TW"),
    ]
    docs = aggregate_trending(rows, now=_NOW)
    assert "ABC" in docs
    assert docs["ABC"]["market"] == "US"
    assert docs["ABC.TW"]["ticker"] == "ABC"
    assert docs["ABC.TW"]["market"] == "TW"


def test_non_us_doc_id_is_always_suffixed_even_without_collision():
    docs = aggregate_trending(
        [_insight("2330", 0.8, 1, "股癌", "tw", market="TW")],
        now=_NOW,
    )
    assert set(docs) == {"2330.TW"}


def test_market_validation_rejects_unknown_market_tokens():
    rows = [
        _insight("X1", 0.6, 1, "股癌", "unknown"),
    ]
    try:
        market_collision_doc_ids(rows)
    except ValueError as exc:
        assert "unknown market" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected collision validation failure")


def test_touched_ticker_markets_infers_legacy_market_shape():
    rows = [
        _insight("NVDA", 0.7, 1, "股癌", "e1"),
        _insight("2330", 0.6, 1, "股癌", "e2"),
    ]
    assert touched_ticker_markets(rows) == {("NVDA", "US"), ("2330", "TW")}


def test_invalid_trending_document_is_rejected_before_write():
    assert validate_trending_document("NVDA", {"ticker": "NVDA", "market": "US"})
    assert validate_trending_document("2330.TW", {"ticker": "2330", "market": "TW"})
    assert not validate_trending_document("2330", {"ticker": "2330", "market": "TW"})
    assert not validate_trending_document("X1", {"ticker": "X1"})


# --- Fake Firestore client ------------------------------------------------
# Minimal in-memory double for the trending_tickers collection: enough surface
# for write_trending (collection/document/batch.set/commit) and
# delete_orphaned_bare_docs (document.get + batch.delete).


class _FakeSnap:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _FakeDocRef:
    def __init__(self, store, doc_id):
        self._store = store
        self.id = doc_id

    def get(self):
        return _FakeSnap(self._store.get(self.id))


class _FakeCollection:
    def __init__(self, store):
        self._store = store

    def document(self, doc_id):
        return _FakeDocRef(self._store, doc_id)


class _FakeBatch:
    def __init__(self, store):
        self._store = store
        self._ops: list[tuple[str, str, dict | None]] = []

    def set(self, ref, doc):
        self._ops.append(("set", ref.id, doc))

    def delete(self, ref):
        self._ops.append(("delete", ref.id, None))

    def commit(self):
        for op, doc_id, doc in self._ops:
            if op == "set":
                self._store[doc_id] = doc
            elif op == "delete":
                self._store.pop(doc_id, None)
        self._ops = []


class _FakeFirestore:
    def __init__(self, initial=None):
        self.store: dict[str, dict] = dict(initial or {})

    def collection(self, name):
        assert name == "trending_tickers"
        return _FakeCollection(self.store)

    def batch(self):
        return _FakeBatch(self.store)


def _trending_doc(ticker, market):
    return {"ticker": ticker, "market": market, "count_all_time": 1}


def test_cleanup_removes_legacy_bare_doc_for_non_us_ticker():
    # Legacy "trending_tickers/2330" (pre-#229, no market field) coexists with the
    # new "2330.TW"; cleanup should drop the bare doc and keep the suffixed one.
    fb = _FakeFirestore(
        {
            "2330": {"ticker": "2330", "count_all_time": 3},  # legacy, no market
            "2330.TW": _trending_doc("2330", "TW"),
        }
    )
    removed = delete_orphaned_bare_docs(fb, {"2330.TW": _trending_doc("2330", "TW")})
    assert removed == 1
    assert set(fb.store) == {"2330.TW"}


def test_cleanup_removes_bare_doc_even_when_market_field_is_tw():
    # A bare doc that somehow carries market=TW is still stale under the new scheme.
    fb = _FakeFirestore(
        {
            "2330": _trending_doc("2330", "TW"),
            "2330.TW": _trending_doc("2330", "TW"),
        }
    )
    removed = delete_orphaned_bare_docs(fb, {"2330.TW": _trending_doc("2330", "TW")})
    assert removed == 1
    assert set(fb.store) == {"2330.TW"}


def test_cleanup_keeps_us_doc_on_token_collision():
    # A token listed in both markets: US lives at the bare id, TW at the suffix.
    # Cleanup must NOT delete the live US doc.
    fb = _FakeFirestore(
        {
            "ABC": _trending_doc("ABC", "US"),
            "ABC.TW": _trending_doc("ABC", "TW"),
        }
    )
    removed = delete_orphaned_bare_docs(
        fb,
        {
            "ABC": _trending_doc("ABC", "US"),
            "ABC.TW": _trending_doc("ABC", "TW"),
        },
    )
    assert removed == 0
    assert set(fb.store) == {"ABC", "ABC.TW"}


def test_cleanup_noop_when_no_bare_doc_exists():
    fb = _FakeFirestore({"2330.TW": _trending_doc("2330", "TW")})
    removed = delete_orphaned_bare_docs(fb, {"2330.TW": _trending_doc("2330", "TW")})
    assert removed == 0
    assert set(fb.store) == {"2330.TW"}


def test_cleanup_ignores_us_only_writes():
    # US docs live at the bare id; an unrelated bare doc must not be touched.
    fb = _FakeFirestore({"NVDA": _trending_doc("NVDA", "US")})
    removed = delete_orphaned_bare_docs(fb, {"NVDA": _trending_doc("NVDA", "US")})
    assert removed == 0
    assert set(fb.store) == {"NVDA"}


def test_cleanup_empty_docs_is_noop():
    fb = _FakeFirestore({"2330": {"ticker": "2330"}})
    assert delete_orphaned_bare_docs(fb, {}) == 0
    assert set(fb.store) == {"2330"}


def test_write_then_cleanup_resolves_double_listing():
    # End-to-end: a legacy bare "2330" exists; aggregate a TW insight, write it
    # (lands at "2330.TW"), then cleanup removes the bare orphan — single listing.
    fb = _FakeFirestore({"2330": {"ticker": "2330", "count_all_time": 5}})
    docs = aggregate_trending(
        [_insight("2330", 0.8, 1, "股癌", "e1", market="TW")], now=_NOW
    )
    assert set(docs) == {"2330.TW"}

    written = write_trending(fb, docs)
    assert written == 1
    removed = delete_orphaned_bare_docs(fb, docs)
    assert removed == 1
    # Only the suffixed doc survives — no more 2330 / 2330.TW double-list.
    assert set(fb.store) == {"2330.TW"}
