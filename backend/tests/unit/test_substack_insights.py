"""The Substack list endpoint's required, strictly-validated sort parameters.

`post_management/published` rejects a request that omits them:

    400 {"errors":[{"param":"order_by","msg":"Invalid value"},
                   {"param":"order_direction","msg":"Invalid value"}]}

and validates the values — `publishedAt` and `DESC` are both refused, `post_date` and
`desc` are accepted. Without them the service fell through to `/api/v1/posts`, a public
endpoint that answers 200 and carries no engagement fields, so the summary came back
empty and looked merely quiet rather than broken.
"""

from src.services import substack_insights_service as m


def test_primary_endpoint_sends_the_required_sort_params():
    primary = m.LIST_ENDPOINTS[0]
    assert "post_management/published" in primary
    assert "order_by=post_date" in primary
    assert "order_direction=desc" in primary


def test_sort_values_are_the_accepted_casing():
    """Substack refuses DESC and publishedAt — the exact strings matter."""
    primary = m.LIST_ENDPOINTS[0]
    assert "order_direction=DESC" not in primary
    assert "order_by=publishedAt" not in primary


def test_endpoint_still_formats_with_offset_and_limit():
    formatted = m.LIST_ENDPOINTS[0].format(offset=50, limit=25)
    assert "offset=50" in formatted and "limit=25" in formatted
    assert "{" not in formatted, "an unfilled placeholder would 400 the request"


def test_public_fallback_is_kept_behind_the_authenticated_one():
    """The fallback has no engagement fields, so it must never be tried first."""
    assert "post_management" in m.LIST_ENDPOINTS[0]
    assert m.LIST_ENDPOINTS[1].startswith("/api/v1/posts?")
