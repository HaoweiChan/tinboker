from fastapi import Response

from src.cache.cdn_cache import CacheProfile, cdn_cached


async def test_cdn_cached_preserves_route_cache_control_header():
    @cdn_cached(profile=CacheProfile.PODCAST)
    async def route(response: Response):
        response.headers["Cache-Control"] = "public, max-age=300, s-maxage=3600"
        return {"ok": True}

    result = await route(Response())

    assert result.headers["Cache-Control"] == "public, max-age=300, s-maxage=3600"
    assert result.headers["Vary"] == "Accept-Encoding"


async def test_cdn_cached_uses_profile_when_route_sets_no_header():
    @cdn_cached(profile=CacheProfile.PODCAST)
    async def route():
        return {"ok": True}

    result = await route()

    assert result.headers["Cache-Control"] == "public, s-maxage=3600, max-age=3600, stale-while-revalidate=7200"
