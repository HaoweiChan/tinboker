"""Reading vocus / Substack view counters.

Both APIs are undocumented and neither field name could be confirmed against a live
account, so what these tests pin is the behaviour that makes a wrong guess *visible*:
a number is reported only when it was actually found, and a miss says which keys the
platform really sent instead of rendering a zero.
"""
import httpx
import pytest

from src.services import vocus_publisher as vp
from src.services import substack_insights_service as sis
from src.services import vocus_insights_service as vis
from src.services.insight_fields import pick_int, sample_keys, sum_int


def _mock_transport(monkeypatch, handler):
    """Route every AsyncClient the service builds internally to `handler`."""
    real_client = httpx.AsyncClient  # captured before the patch, or factory recurses

    def factory(*_args, **_kwargs):
        return real_client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(httpx, "AsyncClient", factory)


def _live_token(monkeypatch):
    monkeypatch.setattr(vp, "token_status", lambda *_a, **_k: {
        "configured": True, "expired": False, "expires_at": 9e9,
        "seconds_left": 999999, "expiring_soon": False,
    })


def _vocus_service():
    return vis.VocusInsightsService(vp.VocusClient(token="t", user_id="u", salon_id="s"))


def _substack_service():
    return sis.SubstackInsightsService(
        sis.SubstackClient(sid="s%3Aabc", subdomain="tinboker", user_id=7)
    )


# ── field resolution ────────────────────────────────────────────────────────
def test_the_first_candidate_key_present_wins():
    value, key = pick_int({"viewCount": 12}, ("readCount", "viewCount"))
    assert (value, key) == (12, "viewCount")


def test_a_dotted_candidate_reaches_a_nested_counter():
    assert pick_int({"stats": {"views": 7}}, ("views", "stats.views")) == (7, "stats.views")


def test_a_string_count_is_still_a_count():
    """These APIs mix ints and strings in the same field across endpoints."""
    assert pick_int({"readCount": "1,204"}, ("readCount",)) == (1204, "readCount")


def test_sum_reports_how_many_objects_actually_carried_the_field():
    """Zero-with-no-matches is a wrong key; zero-with-matches is a quiet week."""
    total, key, matched = sum_int([{"readCount": 3}, {"other": 9}], ("readCount",))
    assert (total, key, matched) == (3, "readCount", 1)


def test_sample_keys_reports_names_not_values():
    assert sample_keys([{"_id": "a", "readTotal": 5}]) == ["_id", "readTotal"]


# ── vocus ───────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_vocus_totals_reads_across_published_articles(monkeypatch):
    _live_token(monkeypatch)
    _mock_transport(monkeypatch, lambda _r: httpx.Response(200, json=[
        {"_id": "a1", "title": "一", "readCount": 120, "likeCount": 3},
        {"_id": "a2", "title": "二", "readCount": 80, "likeCount": 1},
    ]))

    summary = await _vocus_service().account_summary()

    assert summary["available"] is True
    assert (summary["reads"], summary["articles"], summary["likes"]) == (200, 2, 4)
    # Which field the number came from travels with the number.
    assert summary["field_map"]["reads"] == "readCount"
    assert summary["lifetime"] is True


@pytest.mark.asyncio
async def test_vocus_articles_without_a_read_field_report_the_keys_not_a_zero(monkeypatch):
    """The whole point: "we looked in the wrong place" must never render as 0 reads."""
    _live_token(monkeypatch)
    _mock_transport(monkeypatch, lambda _r: httpx.Response(200, json=[
        {"_id": "a1", "title": "一", "readTotal": 120},
    ]))

    summary = await _vocus_service().account_summary()

    assert summary["available"] is False
    assert "reads" not in summary
    assert "readTotal" in summary["sample_keys"]


@pytest.mark.asyncio
async def test_vocus_paging_stops_when_the_page_param_is_ignored(monkeypatch):
    """An API that re-serves page one would otherwise multiply the read total."""
    _live_token(monkeypatch)
    page = [{"_id": f"a{i}", "readCount": 1} for i in range(vis.PAGE_SIZE)]
    _mock_transport(monkeypatch, lambda _r: httpx.Response(200, json=page))

    summary = await _vocus_service().account_summary()

    assert summary["articles"] == vis.PAGE_SIZE
    assert summary["reads"] == vis.PAGE_SIZE


@pytest.mark.asyncio
async def test_vocus_expired_token_is_loud_rather_than_an_empty_panel(monkeypatch):
    monkeypatch.setattr(vp, "token_status", lambda *_a, **_k: {
        "configured": True, "expired": True, "expires_at": 1,
        "seconds_left": -1, "expiring_soon": True,
    })

    def explode(_request):  # pragma: no cover - reached only on a regression
        raise AssertionError("an expired token must not reach the network")

    _mock_transport(monkeypatch, explode)
    summary = await _vocus_service().account_summary()

    assert summary["available"] is False
    assert "expired" in summary["detail"]


@pytest.mark.asyncio
async def test_vocus_recent_articles_carry_their_public_url(monkeypatch):
    _live_token(monkeypatch)
    _mock_transport(monkeypatch, lambda _r: httpx.Response(200, json=[
        {"_id": "a1", "title": "一", "readCount": 9},
    ]))

    rows = await _vocus_service().recent_post_insights(limit=5)

    assert rows[0]["url"] == "https://vocus.cc/article/a1"
    assert rows[0]["reads"] == 9


# ── substack ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_substack_falls_through_to_the_next_list_endpoint(monkeypatch):
    """Which path lists published posts is unverified, so a 404 is not the end."""
    def handler(request: httpx.Request) -> httpx.Response:
        if "post_management" in request.url.path:
            return httpx.Response(404, text="not found")
        return httpx.Response(200, json={"posts": [
            {"id": 1, "title": "一", "postviews": 30},
            {"id": 2, "title": "二", "postviews": 12},
        ]})

    _mock_transport(monkeypatch, handler)
    summary = await _substack_service().account_summary()

    assert summary["available"] is True
    assert (summary["views"], summary["posts"]) == (42, 2)
    # The path that answered is reported so it can be pinned once it is known.
    assert "/api/v1/posts" in summary["source"]


@pytest.mark.asyncio
async def test_substack_posts_without_a_view_field_report_the_keys(monkeypatch):
    _mock_transport(monkeypatch, lambda _r: httpx.Response(200, json={"posts": [
        {"id": 1, "title": "一", "audienceViews": 30},
    ]}))

    summary = await _substack_service().account_summary()

    assert summary["available"] is False
    assert "views" not in summary
    assert "audienceViews" in summary["sample_keys"]


@pytest.mark.asyncio
async def test_substack_stale_cookie_is_reported_not_swallowed(monkeypatch):
    _mock_transport(monkeypatch, lambda _r: httpx.Response(403, text='{"error":"nope"}'))

    summary = await _substack_service().account_summary()

    assert summary["available"] is False
    assert summary["detail"] == "credential_expired"


@pytest.mark.asyncio
async def test_substack_empty_publication_is_not_an_error(monkeypatch):
    _mock_transport(monkeypatch, lambda _r: httpx.Response(200, json={"posts": []}))

    summary = await _substack_service().account_summary()

    assert summary["available"] is False
    assert summary["posts"] == 0
    assert summary["detail"] == "No published posts yet."


@pytest.mark.asyncio
async def test_unconfigured_platforms_say_which_secrets_are_missing():
    """Both panels must explain themselves without credentials present."""
    substack = sis.SubstackInsightsService(sis.SubstackClient(sid=None, subdomain=None, user_id=None))
    summary = await substack.account_summary()
    assert summary["configured"] is False
    assert "SUBSTACK_SID" in summary["detail"]


# ── the daily snapshot ──────────────────────────────────────────────────────
class _FakeDB:
    """Just enough Session for record_snapshot: one row, upserted in memory."""

    def __init__(self, row=None):
        self.row = row

    def query(self, *_args):
        return self

    def filter(self, *_args):
        return self

    def first(self):
        return self.row

    def add(self, row):
        self.row = row

    def commit(self):
        pass

    def refresh(self, _row):
        pass


def _stub_sources(monkeypatch, *, vocus: dict, substack: dict):
    from src.routers import admin_analytics as aa

    def _service(payload):
        class _S:
            async def account_summary(self, *_a, **_k):
                return payload
        return lambda *_a, **_k: _S()

    monkeypatch.setattr(aa, "ThreadsInsightsService", _service({"followers": 452}))
    monkeypatch.setattr(aa, "FacebookInsightsService", _service({"followers": 1, "fans": 1}))
    monkeypatch.setattr(aa, "VocusInsightsService", _service(vocus))
    monkeypatch.setattr(aa, "SubstackInsightsService", _service(substack))
    return aa


@pytest.mark.asyncio
async def test_snapshot_records_reads_from_both_platforms(monkeypatch):
    aa = _stub_sources(
        monkeypatch,
        vocus={"available": True, "reads": 1200, "articles": 30},
        substack={"available": True, "views": 340, "posts": 28},
    )

    result = await aa.record_snapshot(None, _FakeDB())

    assert (result["vocus_reads"], result["vocus_articles"]) == (1200, 30)
    assert (result["substack_reads"], result["substack_posts"]) == (340, 28)
    assert result["threads_followers"] == 452


@pytest.mark.asyncio
async def test_snapshot_leaves_an_unmapped_read_count_null_not_zero(monkeypatch):
    """A wrong field name must leave a gap in the chart, never a 0 that reads as
    "nobody opened it" — and it must not cost the other platforms their row."""
    aa = _stub_sources(
        monkeypatch,
        vocus={"available": False, "detail": "no read field matched", "sample_keys": ["readTotal"]},
        substack={"available": True, "views": 340, "posts": 28},
    )

    result = await aa.record_snapshot(None, _FakeDB())

    assert result["vocus_reads"] is None
    assert result["substack_reads"] == 340
    assert result["threads_followers"] == 452
