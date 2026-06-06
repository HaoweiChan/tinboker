"""Unit tests for the post-edit cache invalidation on the admin content-sources path.

An admin toggling a source active/inactive must bust the Redis origin caches and purge
the current environment's Cloudflare edge host, so the change shows up on the public site
without waiting out the TTLs. These tests pin that contract (pattern list + per-env host
+ best-effort no-raise) so a refactor can't silently regress it.
"""
import pytest

import src.routers.admin_sources as m


EXPECTED_PATTERNS = [
    "release:allowed_podcasts:*",
    "podcast:*",
    "episode:*",
    "episodes:*",
    "news:*",
]


def _patch_cache(monkeypatch):
    """Replace the two async cache helpers with recorders; return their call logs."""
    patterns: list[str] = []
    purges: list[dict] = []

    async def fake_delete_pattern(pattern):
        patterns.append(pattern)
        return 0

    async def fake_purge(**kwargs):
        purges.append(kwargs)
        return True

    monkeypatch.setattr(m, "cache_delete_pattern", fake_delete_pattern)
    monkeypatch.setattr(m, "purge_cdn_cache", fake_purge)
    return patterns, purges


async def test_invalidate_clears_all_redis_patterns(monkeypatch):
    patterns, _ = _patch_cache(monkeypatch)
    monkeypatch.setattr(m.settings, "environment", "development")

    await m._invalidate_source_caches()

    assert patterns == EXPECTED_PATTERNS


@pytest.mark.parametrize(
    "environment,expected_host",
    [
        ("production", "api.tinboker.com"),
        ("staging", "staging-api.tinboker.com"),
        ("development", "dev-api.tinboker.com"),
        ("Production", "api.tinboker.com"),  # case-insensitive
    ],
)
async def test_invalidate_purges_correct_host_per_env(monkeypatch, environment, expected_host):
    _, purges = _patch_cache(monkeypatch)
    monkeypatch.setattr(m.settings, "environment", environment)

    await m._invalidate_source_caches()

    assert purges == [{"hosts": [expected_host]}]


async def test_invalidate_skips_cdn_purge_for_unknown_env(monkeypatch):
    patterns, purges = _patch_cache(monkeypatch)
    monkeypatch.setattr(m.settings, "environment", "local")

    await m._invalidate_source_caches()

    # Redis is still cleared, but no host purge is attempted for an unmapped env.
    assert patterns == EXPECTED_PATTERNS
    assert purges == []


async def test_invalidate_is_best_effort_and_never_raises(monkeypatch):
    """A cache failure must not turn an already-committed admin write into a 500."""
    async def boom_pattern(pattern):
        raise RuntimeError("redis down")

    async def boom_purge(**kwargs):
        raise RuntimeError("cloudflare down")

    monkeypatch.setattr(m, "cache_delete_pattern", boom_pattern)
    monkeypatch.setattr(m, "purge_cdn_cache", boom_purge)
    monkeypatch.setattr(m.settings, "environment", "development")

    # Must complete without raising.
    await m._invalidate_source_caches()
