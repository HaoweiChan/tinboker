"""Unit tests for the post-edit cache invalidation on the admin content-sources path.

An admin toggling a source active/inactive must bust the Redis origin caches and purge
the Cloudflare edge. Because every environment shares the same Postgres and Redis, a
source change from any env must purge ALL envs' API + frontend hosts in one call — these
tests pin that contract (pattern list + all-hosts purge + best-effort no-raise) so a
refactor can't silently regress it.
"""
import src.routers.admin_sources as m


EXPECTED_PATTERNS = [
    "release:allowed_podcasts:*",
    "podcast:*",
    "episode:*",
    "episodes:*",
    "news:*",
]

# The full set of hosts a single source edit must purge (all envs share DB/Redis).
EXPECTED_HOSTS = m._ALL_API_HOSTS + m._ALL_FRONTEND_HOSTS


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

    monkeypatch.setattr(m, "cache_delete_pattern_all_envs", fake_delete_pattern)
    monkeypatch.setattr(m, "purge_cdn_cache", fake_purge)
    return patterns, purges


async def test_invalidate_clears_all_redis_patterns(monkeypatch):
    patterns, _ = _patch_cache(monkeypatch)

    await m._invalidate_source_caches()

    assert patterns == EXPECTED_PATTERNS


async def test_invalidate_purges_all_env_hosts_in_one_call(monkeypatch):
    """One batched purge of every env's API + frontend host — env-independent, since
    all environments share the same Postgres/Redis."""
    _, purges = _patch_cache(monkeypatch)

    await m._invalidate_source_caches()

    assert purges == [{"hosts": EXPECTED_HOSTS}]
    # Sanity: prod, staging, and dev hosts are all covered.
    assert {"api.tinboker.com", "staging-api.tinboker.com", "dev-api.tinboker.com"} <= set(EXPECTED_HOSTS)
    assert {"tinboker.com", "staging.tinboker.com", "dev.tinboker.com"} <= set(EXPECTED_HOSTS)


async def test_invalidate_is_best_effort_and_never_raises(monkeypatch):
    """A cache failure must not turn an already-committed admin write into a 500."""
    async def boom_pattern(pattern):
        raise RuntimeError("redis down")

    async def boom_purge(**kwargs):
        raise RuntimeError("cloudflare down")

    monkeypatch.setattr(m, "cache_delete_pattern_all_envs", boom_pattern)
    monkeypatch.setattr(m, "purge_cdn_cache", boom_purge)

    # Must complete without raising.
    await m._invalidate_source_caches()


def test_env_redis_urls_targets_each_logical_db():
    """An admin edit must purge prod (/0), staging (/1), and dev (/2) logical DBs —
    derived from the configured Redis URL regardless of which DB it points at."""
    from src.cache.redis_client import _env_redis_urls, _ENV_REDIS_DBS

    assert _env_redis_urls("redis://redis:6379/2") == [
        "redis://redis:6379/0",
        "redis://redis:6379/1",
        "redis://redis:6379/2",
    ]
    # Credentials in the netloc survive the DB rewrite (no password loss).
    assert _env_redis_urls("redis://:pw@host:6379/0") == [
        f"redis://:pw@host:6379/{db}" for db in _ENV_REDIS_DBS
    ]
    # A URL with no DB suffix still fans out to all envs.
    assert _env_redis_urls("redis://host:6379") == [
        f"redis://host:6379/{db}" for db in _ENV_REDIS_DBS
    ]
