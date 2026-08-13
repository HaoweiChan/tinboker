"""Which host the syndication platforms are told to fetch the cover from."""
from unittest import mock

from src.routers.social import _public_base_url


def _request(headers: dict, base: str = "http://backend:8000/"):
    return mock.Mock(headers=headers, base_url=base)


def test_forwarded_headers_win_because_they_carry_the_public_host():
    """Behind Cloudflare the app sees an internal host; only the forwarded pair knows
    which environment the caller actually reached."""
    r = _request({"x-forwarded-proto": "https", "x-forwarded-host": "dev-api.tinboker.com"})
    assert _public_base_url(r) == "https://dev-api.tinboker.com"


def test_a_forwarded_list_takes_the_first_hop():
    r = _request({"x-forwarded-proto": "https,http", "x-forwarded-host": "api.tinboker.com, internal"})
    assert _public_base_url(r) == "https://api.tinboker.com"


def test_falls_back_to_the_request_origin_when_not_proxied():
    r = _request({}, base="https://staging-api.tinboker.com/")
    assert _public_base_url(r) == "https://staging-api.tinboker.com"


def test_a_local_origin_falls_through_to_the_setting():
    """A localhost URL is useless to an outside fetcher, so it must not be handed out."""
    from src.config import settings
    r = _request({}, base="http://localhost:5174/")
    assert _public_base_url(r) == settings.public_api_url.rstrip("/")
