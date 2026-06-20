"""Tests for the agent-backed regeneration orchestrator.

These exercise the host-driven state machine + non-LLM glue WITHOUT touching
Firestore or any LLM: a working draft is injected directly and driven with canned
role outputs. They also assert prompt parity — the orchestrator renders the exact
messages each content_builder node would send — which guards the build_messages /
postprocess refactor against drift.
"""

import json

import pytest
from src.podcast.content_builder.nodes import (
    extractor,
    key_insights_extractor,
    marp_writer,
    ticker_extractor,
    writer,
)
from src.podcast.content_builder.nodes.markdown_transform import transform_to_markdown
from src.podcast.content_builder.nodes.marp_converter import convert_marp
from src.podcast.regen import orchestrator as orch


@pytest.fixture(autouse=True)
def _isolate_work_dir(tmp_path, monkeypatch):
    """Persist drafts under a tmp dir and start every test with a clean session map."""
    monkeypatch.setenv("TINBOKER_REGEN_WORK_DIR", str(tmp_path))
    orch._SESSIONS.clear()
    yield
    orch._SESSIONS.clear()


SENTENCES = [
    {"index": 0, "content": "歡迎收聽，今天聊台積電", "start": 0, "end": 3000},
    {"index": 1, "content": "台積電財報優於預期，營收成長", "start": 3000, "end": 6000},
    {"index": 2, "content": "半導體供應鏈展望樂觀", "start": 6000, "end": 9000},
]

WRITER_OUT = {
    "title": "台積電專題",
    "executive_summary": "摘要重點",
    "sections": [{
        "heading": "台積電前景",
        "content": "看好[台積電](#ticker:2330)在[半導體](#tag:Semiconductor)的成長",
        "start_time": 0,
    }],
    "conclusion": "結論",
}
TICKER_OUT = {"ticker_recommendations": [{
    "ticker": "2330", "sentiment": "BULLISH", "sentiment_score": 0.82,
    "time_horizon": "LONG_TERM", "bluf_thesis": "長線看好", "reasons": [], "risks": [],
}]}
MARP_OUT = {"title": "EP1", "slides": [{"heading": "台積電", "bullet_points": ["重點一", "重點二"], "start_time": 3000}]}


def _new_draft(episode_id="ep_test"):
    draft = {
        "episode_id": episode_id, "podcast_name": "股癌", "episode_title": "EP1",
        "source": "股癌", "created_time": None,
        "state": {"sentences": SENTENCES, "source": "股癌", "episode_title": "EP1", "transcript": "..."},
        "completed": [], "current_content": {}, "started_at_unix": 0,
    }
    orch._SESSIONS[episode_id] = draft
    return draft


def _drive_required(episode_id="ep_test"):
    orch.submit(episode_id, "extractor", {"events": [{"section_topic": "台積電財報分析", "start_index": 0, "end_index": 2}]})
    orch.submit(episode_id, "writer", WRITER_OUT)
    orch.submit(episode_id, "key_insights", {"key_insights": ["台積電財報優於預期", "半導體供應鏈樂觀"]})
    orch.submit(episode_id, "ticker_extractor", TICKER_OUT)


# --- Prompt parity ----------------------------------------------------------

def test_prompt_parity_matches_node_build_messages():
    """orchestrator._build_messages renders byte-identical messages to each node."""
    draft = _new_draft()
    st = draft["state"]
    assert orch._build_messages("extractor", st) == extractor.build_messages(st)

    # writer/ticker/marp need clustered_events — run the extractor glue first.
    orch.submit("ep_test", "extractor", {"events": [{"section_topic": "台積電", "start_index": 0, "end_index": 2}]})
    st = draft["state"]
    assert orch._build_messages("writer", st) == writer.build_messages(st)
    assert orch._build_messages("ticker_extractor", st) == ticker_extractor.build_messages(st)
    assert orch._build_messages("marp_writer", st) == marp_writer.build_messages(st)

    # key_insights needs markdown_report.
    orch.submit("ep_test", "writer", WRITER_OUT)
    st = draft["state"]
    assert orch._build_messages("key_insights", st) == key_insights_extractor.build_messages(st)


def test_rendered_prompt_has_no_unsubstituted_vars():
    draft = _new_draft()
    p = orch._prompt_payload("extractor", draft["state"])
    assert p["system"] and p["user"]
    assert "{sentences}" not in p["user"] and "{source}" not in p["user"]
    assert "台積電" in p["user"]  # the sentences were substituted in


def test_writer_prompt_injects_tag_vocabulary():
    """C1: the curated slug vocabulary is injected so the model maps to known slugs."""
    draft = _new_draft()
    orch.submit("ep_test", "extractor", {"events": [{"section_topic": "台積電", "start_index": 0, "end_index": 2}]})
    p = orch._prompt_payload("writer", draft["state"])
    assert "{tag_vocabulary}" not in p["user"]      # placeholder substituted
    assert "Semiconductor = 半導體" in p["user"]     # a vocabulary entry is present


def test_ticker_marp_uses_ticker_insights_not_events():
    """The two marp steps share a prompt but feed different payloads."""
    draft = _new_draft()
    _drive_required()
    st = draft["state"]
    episode_msgs = orch._build_messages("marp_writer", st)
    ticker_msgs = orch._build_messages("ticker_marp_writer", st)
    assert episode_msgs != ticker_msgs
    assert "2330" in ticker_msgs[1]["content"]  # ticker payload flowed in


# --- Glue parity with the node functions ------------------------------------

def test_writer_glue_matches_transform_to_markdown():
    draft = _new_draft()
    orch.submit("ep_test", "extractor", {"events": [{"section_topic": "台積電", "start_index": 0, "end_index": 2}]})
    orch.submit("ep_test", "writer", WRITER_OUT)
    # Parity must feed transform the SAME clustered_events the glue produced — the
    # heading's (#time:..) anchor is derived from them, so omitting them here would
    # compare against an unanchored heading.
    expected = transform_to_markdown({
        "writer_output": WRITER_OUT,
        "clustered_events": draft["state"]["clustered_events"],
    })["markdown_report"]
    assert draft["state"]["markdown_report"] == expected
    # tags/tickers parsed from the markdown links
    assert draft["state"]["tags"] == ["semiconductor"]
    assert draft["state"]["related_tickers"] == ["2330"]


def test_marp_glue_matches_convert_marp():
    draft = _new_draft()
    orch.submit("ep_test", "extractor", {"events": [{"section_topic": "台積電", "start_index": 0, "end_index": 2}]})
    orch.submit("ep_test", "marp_writer", MARP_OUT)
    expected = convert_marp({"marp_slides": MARP_OUT})["marp_markdown"]
    assert draft["state"]["marp_markdown"] == expected


# --- State machine ----------------------------------------------------------

def test_prereq_enforced():
    _new_draft()
    with pytest.raises(orch.RegenError):
        orch.get_prompt("ep_test", "writer")  # before extractor
    with pytest.raises(orch.RegenError):
        orch.submit("ep_test", "key_insights", {"key_insights": []})  # before writer


def test_extractor_all_dropped_events_warns():
    """When the policy router (+ safety net) keeps nothing, the agent is warned to re-type."""
    _new_draft()
    res = orch.submit("ep_test", "extractor", {"events": [
        # sponsor is dropped by policy AND excluded from the empty-result safety net.
        {"section_topic": "業配廣告", "start_index": 0, "end_index": 2,
         "segment_type": "sponsor", "is_substantive": False},
    ]})
    assert res["warnings"]
    assert any("0 events kept" in w for w in res["warnings"])


def test_extractor_untyped_events_are_kept_no_warning():
    """An untyped event -> unknown -> kept, so no 'nothing kept' warning (floor behavior)."""
    _new_draft()
    res = orch.submit("ep_test", "extractor", {"events": [{"section_topic": "輝達佈局", "start_index": 0, "end_index": 2}]})
    assert not res["warnings"]


def test_ready_steps_progression():
    _new_draft()
    res = orch.submit("ep_test", "extractor", {"events": [{"section_topic": "台積電", "start_index": 0, "end_index": 2}]})
    assert set(res["ready_steps"]) == {"writer", "ticker_extractor", "marp_writer"}
    assert res["required_done"] is False


def test_unknown_step_rejected():
    _new_draft()
    with pytest.raises(orch.RegenError):
        orch.get_prompt("ep_test", "bogus_step")


def test_step_aliases_accepted():
    _new_draft()
    orch.submit("ep_test", "extractor", {"events": [{"section_topic": "台積電", "start_index": 0, "end_index": 2}]})
    # "tickers" -> ticker_extractor, "slides" -> marp_writer
    assert orch.get_prompt("ep_test", "tickers")["step"] == "ticker_extractor"
    assert orch.get_prompt("ep_test", "slides")["step"] == "marp_writer"


def test_submit_accepts_json_string():
    _new_draft()
    orch.submit("ep_test", "extractor", json.dumps({"events": [{"section_topic": "台積電", "start_index": 0, "end_index": 2}]}))
    assert "extractor" in orch._SESSIONS["ep_test"]["completed"]


# --- Assembly / field gating ------------------------------------------------

def test_assemble_only_includes_completed_steps():
    _new_draft()
    orch.submit("ep_test", "extractor", {"events": [{"section_topic": "台積電", "start_index": 0, "end_index": 2}]})
    orch.submit("ep_test", "writer", WRITER_OUT)
    prev = orch.preview("ep_test")
    fields = set(prev["will_write_fields"])
    assert {"summary_content", "tags", "related_tickers", "events_markdown"} <= fields
    # No key_insights / ticker / marp yet — they must NOT be in the write set.
    assert "key_insights" not in fields
    assert "marp_markdown" not in fields
    assert "ticker_marp_markdown" not in fields
    assert prev["ticker_insight_count"] == 0


def test_full_run_preview_has_everything():
    _new_draft()
    _drive_required()
    orch.submit("ep_test", "marp_writer", MARP_OUT)
    orch.submit("ep_test", "ticker_marp_writer", {"title": "T", "slides": [{"heading": "2330", "bullet_points": ["看多"], "start_time": 0}]})
    prev = orch.preview("ep_test")
    assert prev["key_insights"][:2] == ["台積電財報優於預期", "半導體供應鏈樂觀"]
    assert len(prev["key_insights"]) >= 3
    assert prev["related_tickers"] == ["2330"]
    assert prev["ticker_insight_count"] == 1
    assert prev["social_card_count"] >= 1  # cover + theme cards
    assert prev["marp_chars"] > 0 and prev["ticker_marp_chars"] > 0


def test_commit_with_nothing_submitted_errors():
    _new_draft("ep_empty")
    with pytest.raises(orch.RegenError):
        orch.commit("ep_empty")


# --- commit writes the served content path (GCS re-upload + authed cache bust) ----


class _Resp:
    """Minimal stand-in for an httpx.Response (status + body) for the cache-bust PATCH."""

    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


class _FakeFirestore:
    """Captures set_document writes so a commit can be asserted without Firestore."""

    def __init__(self):
        self.writes = []  # list of (collection, doc_id, data, merge)
        self.db = object()

    def set_document(self, collection, doc_id, data, merge=False):
        self.writes.append((collection, doc_id, dict(data), merge))

    def merged(self, doc_id):
        """The union of every merge write for ``doc_id`` (commit writes in parts)."""
        out = {}
        for collection, did, data, _ in self.writes:
            if collection == "episodes" and did == doc_id:
                out.update(data)
        return out


class _FakeGCS:
    """Records upload_episode_files calls and returns deterministic gs:// URLs for
    whatever content was provided (mirrors the real service's return shape)."""

    def __init__(self):
        self.calls = []

    def upload_episode_files(self, **kwargs):
        self.calls.append(kwargs)
        eid = kwargs["episode_id"]
        out = {}
        if kwargs.get("summary_content"):
            out["summary_url"] = f"gs://b/summaries/{eid}.md"
            out["summary_public_url"] = f"https://h/summaries/{eid}.md"
        if kwargs.get("events_markdown_content"):
            out["events_markdown_url"] = f"gs://b/events/{eid}.md"
            out["events_markdown_public_url"] = f"https://h/events/{eid}.md"
        if kwargs.get("marp_markdown_content"):
            out["marp_markdown_url"] = f"gs://b/marp/{eid}.md"
            out["marp_markdown_public_url"] = f"https://h/marp/{eid}.md"
        return out


def _drive_summary_and_marp(episode_id="ep_test"):
    """extractor -> writer -> marp: yields summary_content, events_markdown, and
    marp_markdown in the payload WITHOUT the ticker subcollection (kept out so the
    test doesn't touch the ticker_insights exporter)."""
    orch.submit(episode_id, "extractor", {"events": [{"section_topic": "台積電", "start_index": 0, "end_index": 2}]})
    orch.submit(episode_id, "writer", WRITER_OUT)
    orch.submit(episode_id, "marp_writer", MARP_OUT)


def test_commit_reuploads_gcs_served_content_and_repoints_urls(monkeypatch):
    """The core fix: commit must overwrite the GCS blobs the backend hydrates from
    (marp/events/summary) and repoint the episode doc's *_url at the fresh upload —
    otherwise the page keeps serving the OLD marp."""
    _new_draft()
    _drive_summary_and_marp()

    fake_fs = _FakeFirestore()
    fake_gcs = _FakeGCS()
    monkeypatch.setattr(orch, "_firestore", lambda: fake_fs)
    monkeypatch.setattr(orch, "_gcs_storage_service", lambda: fake_gcs)
    monkeypatch.setattr("httpx.patch", lambda *a, **k: _Resp(200))
    monkeypatch.setenv("TINBOKER_PLATFORM_API_URL", "https://api.example.com")
    monkeypatch.setenv("TINBOKER_WRITE_TOKEN", "svc-token-123")

    report = orch.commit("ep_test")

    # 1. The served-from-GCS artifacts were re-uploaded, force-overwriting the blob.
    assert len(fake_gcs.calls) == 1
    call = fake_gcs.calls[0]
    assert call["skip_existing"] is False
    assert call["episode_id"] == "ep_test"
    assert call["marp_markdown_content"]      # the regenerated slides
    assert call["events_markdown_content"]
    assert call["summary_content"]

    # 2. The doc's *_url fields now point at the fresh upload (so hydration reads it).
    merged = fake_fs.merged("ep_test")
    assert merged["marp_markdown_url"] == "gs://b/marp/ep_test.md"
    assert merged["events_markdown_url"] == "gs://b/events/ep_test.md"
    assert merged["summary_url"] == "gs://b/summaries/ep_test.md"
    assert "marp_markdown_url" in report["gcs_content_uploaded"]


def test_commit_patch_carries_content_writer_token(monkeypatch):
    """Gap #2: the cache-bust PATCH must send the content-writer bearer token, or the
    admin-gated endpoint 403s and Redis/CDN stay stale."""
    _new_draft()
    _drive_summary_and_marp()
    monkeypatch.setattr(orch, "_firestore", lambda: _FakeFirestore())
    monkeypatch.setattr(orch, "_gcs_storage_service", lambda: _FakeGCS())
    monkeypatch.setenv("TINBOKER_PLATFORM_API_URL", "https://api.example.com")
    monkeypatch.setenv("TINBOKER_WRITE_TOKEN", "svc-token-123")

    captured = {}

    def fake_patch(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers or {}
        captured["json"] = json
        return _Resp(200)

    monkeypatch.setattr("httpx.patch", fake_patch)

    report = orch.commit("ep_test")

    assert captured["headers"].get("Authorization") == "Bearer svc-token-123"
    assert captured["url"].endswith("/api/podcast/股癌/episodes/ep_test")
    assert report.get("platform_notified") == 200
    assert not report["warnings"]


def test_commit_without_write_token_skips_patch_and_warns(monkeypatch):
    """No token -> do NOT fire an anonymous PATCH that 403s; warn and fall back to the
    manual (now auth-aware) commands."""
    _new_draft()
    _drive_summary_and_marp()
    monkeypatch.setattr(orch, "_firestore", lambda: _FakeFirestore())
    monkeypatch.setattr(orch, "_gcs_storage_service", lambda: _FakeGCS())
    monkeypatch.setenv("TINBOKER_PLATFORM_API_URL", "https://api.example.com")
    monkeypatch.delenv("TINBOKER_WRITE_TOKEN", raising=False)

    def fail_patch(*a, **k):
        raise AssertionError("must not PATCH without a content-writer token")

    monkeypatch.setattr("httpx.patch", fail_patch)

    report = orch.commit("ep_test")

    assert "platform_notified" not in report
    assert any("TINBOKER_WRITE_TOKEN" in w for w in report["warnings"])
    assert report.get("cache_stale_until_ttl") is True
    # The manual fallback PATCH must itself carry the auth header.
    assert any("Authorization: Bearer $TINBOKER_WRITE_TOKEN" in c
               for c in report["manual_invalidation"])


def test_discard_removes_session():
    _new_draft("ep_discard")
    res = orch.discard("ep_discard")
    assert res["discarded"] is True
    assert "ep_discard" not in orch._SESSIONS
    with pytest.raises(orch.RegenError):
        orch.get_prompt("ep_discard", "extractor")


# --- Lean responses + output schema (A1/A2/A3) ------------------------------

def test_prompt_payload_carries_schema_and_drops_messages():
    """Full prompt = system+user+output contract, NO redundant messages array."""
    draft = _new_draft()
    p = orch._prompt_payload("extractor", draft["state"])
    assert "messages" not in p                      # A1: redundant copy removed
    assert "output_schema" in p and "example" in p  # A3: machine-readable contract
    assert "events" in p["output_schema"]


def test_submit_next_is_lightweight_pointer():
    """submit's `next` carries the output contract but NOT the transcript body."""
    _new_draft()
    res = orch.submit("ep_test", "extractor", {"events": [{"section_topic": "台積電", "start_index": 0, "end_index": 2}]})
    nxt = res["next"]
    assert nxt["step"] == "writer"
    assert "output_schema" in nxt and "example" in nxt
    assert "system" not in nxt and "user" not in nxt  # A2: no heavy body echoed


# --- Submit-time validation (A4) --------------------------------------------

def test_submit_rejects_bad_extractor_shape():
    _new_draft()
    with pytest.raises(orch.RegenError, match="events"):
        orch.submit("ep_test", "extractor", {"sections": []})


def test_submit_rejects_bad_ticker_key():
    _new_draft()
    orch.submit("ep_test", "extractor", {"events": [{"section_topic": "台積電", "start_index": 0, "end_index": 2}]})
    with pytest.raises(orch.RegenError, match="ticker_recommendations"):
        orch.submit("ep_test", "ticker_extractor", {"tickers": []})  # wrong key


def test_submit_accepts_extractor_bare_list():
    """Validation mirrors postprocess tolerance (extractor accepts a bare list)."""
    _new_draft()
    res = orch.submit("ep_test", "extractor", [{"section_topic": "台積電", "start_index": 0, "end_index": 2}])
    assert "extractor" in res["completed"]


# --- Output parity: automated pipeline (run_pipeline) vs agent regen ---------

def _patch_canned_llm(monkeypatch):
    """Make run_pipeline's per-node invoke_json return the SAME canned role outputs
    we feed the regen orchestrator, so any divergence is a real contract drift."""
    canned = {
        "extractor": {"events": [{"section_topic": "台積電財報分析", "start_index": 0, "end_index": 2}]},
        "writer": WRITER_OUT,
        "key_insights_extractor": {"key_insights": ["台積電財報優於預期", "半導體供應鏈樂觀"]},
        "ticker_extractor": TICKER_OUT,
        "marp_writer": MARP_OUT,
        # run_pipeline also drives the social-copy node; the regen parity assertions
        # don't cover social output, but the canned map must answer every role the
        # pipeline calls or invoke_json KeyErrors mid-run.
        "social_copy_writer": {"post": "今天聊台積電", "comments": []},
    }

    def fake(role, messages=None, schema=None):
        return canned[role]

    for mod in (
        "extractor", "writer", "key_insights_extractor",
        "ticker_extractor", "marp_writer", "social_copy_writer",
    ):
        monkeypatch.setattr(f"src.podcast.content_builder.nodes.{mod}.invoke_json", fake)
    monkeypatch.setattr("src.podcast.content_builder.llm.invoke_json", fake)
    return canned


def test_episode_doc_parity_pipeline_vs_regen(monkeypatch):
    """For identical per-step outputs, run_pipeline and the regen orchestrator
    assemble identical episode-doc fields. Guards the two paths against drift
    (e.g. one changing tag derivation but not the other)."""
    canned = _patch_canned_llm(monkeypatch)

    from src.podcast.content_builder import run_pipeline
    pipe = run_pipeline(transcript="...", sentences=SENTENCES, source="股癌", episode_title="EP1")

    _new_draft()
    orch.submit("ep_test", "extractor", canned["extractor"])
    orch.submit("ep_test", "writer", canned["writer"])
    orch.submit("ep_test", "key_insights", canned["key_insights_extractor"])
    orch.submit("ep_test", "ticker_extractor", canned["ticker_extractor"])
    payload = orch._assemble(orch._SESSIONS["ep_test"])

    assert payload["summary_content"] == pipe["markdown_report"]
    assert payload["key_insights"] == pipe["key_insights"]
    assert payload["tags"] == pipe["tags"]
    assert payload["related_tickers"] == pipe["related_tickers"]
    assert payload["events_markdown"] == pipe["events_markdown"]
    assert payload["ticker_insights"] == pipe["ticker_insights"]
    assert payload["sector_exposures"] == pipe["sector_exposures"]
    assert payload["sector_exposure_ids"] == pipe["sector_exposure_ids"]
    # And the canonical tags are the ASCII slug parsed from the #tag: link.
    assert payload["tags"] == ["semiconductor"]
    assert payload["related_tickers"] == ["2330"]
    assert "sector_semiconductor" in payload["sector_exposure_ids"]


# --- Publish-date stamping (the /picks "走勢" forward-return reference date) ----
# The publish-time resolver itself is unit-tested in
# tests/unit/test_ticker_insights_exporter.py::test_episode_publish_time_*; these
# guard that commit() actually threads the captured value into the exporter.


class _FakeFS:
    """Minimal FirestoreService stand-in: records set_document calls, exposes .db."""

    def __init__(self):
        self.db = object()
        self.writes = []

    def set_document(self, *args, **kwargs):
        self.writes.append((args, kwargs))


def _capture_export(monkeypatch):
    """Patch the insight exporter so commit() can run without Firestore, capturing the
    ``podcast_launch_time`` it would stamp. Returns the capture dict."""
    captured: dict = {}

    def fake_build(*, raw_payload, episode_id, podcaster, podcast_launch_time):
        captured["podcast_launch_time"] = podcast_launch_time
        return {"2330": {"ticker": "2330"}}

    monkeypatch.setattr(orch, "_firestore", lambda: _FakeFS())
    monkeypatch.setattr(
        "src.podcast.exporters.ticker_insights.build_episode_insight_docs", fake_build
    )
    monkeypatch.setattr(
        "src.podcast.exporters.ticker_insights.write_episode_insights",
        lambda db, *, episode_id, docs: len(docs),
    )
    return captured


def test_commit_stamps_insights_with_real_publish_time(monkeypatch):
    """commit() stamps ticker_insights with the episode's true publish time
    (draft['podcast_launch_time']), NOT the ingest-time created_time."""
    draft = _new_draft()
    draft["created_time"] = "2026-06-17T20:22:12Z"   # ingest/regen time — the wrong ref
    draft["podcast_launch_time"] = 1700000000000      # real release (epoch ms)
    _drive_required()

    captured = _capture_export(monkeypatch)
    report = orch.commit("ep_test", notify_platform=False)

    assert captured["podcast_launch_time"] == 1700000000000
    assert report["ticker_insights_written"] == 1


def test_commit_falls_back_to_created_time_for_legacy_draft(monkeypatch):
    """A draft opened before podcast_launch_time existed still stamps via created_time
    rather than crashing or stamping None."""
    draft = _new_draft()
    draft["created_time"] = "2025-05-09T00:00:00Z"
    draft.pop("podcast_launch_time", None)
    _drive_required()

    captured = _capture_export(monkeypatch)
    orch.commit("ep_test", notify_platform=False)

    assert captured["podcast_launch_time"] == "2025-05-09T00:00:00Z"
