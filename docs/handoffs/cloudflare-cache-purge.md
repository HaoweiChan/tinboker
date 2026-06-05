# Handoff — Cloudflare edge cache: post-deploy purge + `/api/search` over-caching

**Date:** 2026-06-05
**Trigger:** zh-TW launch looked broken post-deploy — the edge served pre-deploy `/api/podcast`
(`s-maxage=3600`, ~1h) and `/api/search/suggest` (`cache-control: max-age=86400`, `cf-cache-status: HIT`,
up to 24h) even though origin was already correct. Root cause: the deploy pipeline had **no
cache-purge step**, and the `/api/*` zone Cache Rule over-caches endpoints that send no
`Cache-Control` header.

## What shipped (code — done)

1. **Post-deploy edge purge** in [`backend-deploy.yml`](../../.github/workflows/backend-deploy.yml)
   and [`backend-deploy-admin.yml`](../../.github/workflows/backend-deploy-admin.yml).
   After the container health check passes, a `Purge Cloudflare CDN cache` step calls
   `POST https://api.cloudflare.com/client/v4/zones/{CLOUDFLARE_ZONE_TAG}/purge_cache`:
   - Host-scoped purge first: `{"hosts":["{api_host}"]}` where `api_host` is
     `dev-api` / `staging-api` / `api`.tinboker.com per env. (Same method as the manual
     recipe documented in `CLAUDE.md`.)
   - Falls back to `{"purge_everything":true}` if host purge returns `success:false`
     (purge by host/prefix is **Enterprise-plan only**).
   - Best-effort: warns but never fails an otherwise-green deploy.
   - Secrets `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ZONE_TAG` are fetched from GSM in the
     existing "Fetch secrets from GSM" step (both marked Optional → step skips with a
     warning if unset).

2. **Short edge TTL on dynamic search endpoints** —
   [`backend/src/routers/search.py`](../../backend/src/routers/search.py): `/api/search` and
   `/api/search/suggest` now carry `@cdn_cached(s_maxage=60, max_age=0, stale=30)`. With the
   rule's *Edge TTL: Use cache-control header*, the edge now honours 60s instead of a long
   default. Header verified: `public, s-maxage=60, stale-while-revalidate=30`.

3. **Env-var fix** — [`backend/src/cache/cdn_cache.py`](../../backend/src/cache/cdn_cache.py)
   `purge_cdn_cache()` read `CLOUDFLARE_ZONE_ID`, but the platform stores the zone id as
   `CLOUDFLARE_ZONE_TAG`. Now reads `CLOUDFLARE_ZONE_TAG` (legacy `CLOUDFLARE_ZONE_ID` still
   accepted). NOTE: this helper is currently **defined but never called** at runtime — the
   real purge path is the workflow step above.

## What still needs a human (Cloudflare dashboard — NOT code)

The `/api/*` Cache Rule (`tinboker.com` → Rules → Cache Rules) has **Browser TTL: Override**.
An override rewrites the `max-age` sent to browsers regardless of origin headers — this is the
source of the observed `max-age=86400`, and the documented value ("1 hour") had drifted. The
origin decorator from #2 only controls **edge** TTL; it cannot undo a browser-TTL override.

**Action:** set the rule's **Browser TTL → "Respect origin"** (or add a higher-priority rule
that bypasses cache / respects origin for
`starts_with(http.request.uri.path, "/api/search/")`). Then re-confirm:

```bash
curl -sI 'https://api.tinboker.com/api/search/suggest?q=2330' | grep -i 'cache-control\|cf-cache-status'
# expect: cache-control: public, s-maxage=60, stale-while-revalidate=30   (no max-age=86400)
```

## Verify the purge step after merge

- Merge to `develop` → watch the **Backend Build & Deploy** run → `Purge Cloudflare CDN cache`
  step should print `✅ Edge cache purged for dev-api.tinboker.com/api/` (or the
  `purge_everything` fallback line). If it prints the "credentials missing" warning, confirm
  `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ZONE_TAG` exist in GSM and that the token has the
  **Zone → Cache Purge** permission.

## Open question / possible simplification

The host→everything fallback exists because the Cloudflare plan tier is unconfirmed. If the
zone is **not** Enterprise, host purge always falls back to `purge_everything` (purges the
whole zone incl. the other envs + Pages assets — functional but broad). If you confirm the
tier, the step can be simplified to a single mode.
