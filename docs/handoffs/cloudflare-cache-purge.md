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

## ✅ Resolved 2026-06-09 (was: manual Cloudflare dashboard action)

The `/api/*` Cache Rule (`tinboker.com` → Rules → Cache Rules) had **Browser TTL: Override**
(`default=86400`). An override rewrites the `max-age` sent to browsers regardless of origin
headers — this was the source of the observed `max-age=86400`, and the documented value
("1 hour") had drifted. The origin decorator from #2 only controls **edge** TTL; it could not
undo a browser-TTL override. Symptom that finally surfaced it: 2330's ticker-insight cards
showed the zh-TW "尚未完成繁中轉寫" frontend fallback because browsers held a 24h-cached
*pre-translation* `/api/ticker-insights` response while the origin/edge already served correct
zh-TW.

**Fix (2026-06-09):** the rule's **Browser TTL** was flipped `override_origin → respect_origin`
via the Cloudflare Rulesets API (no dashboard click required):

- Ruleset `3a79f70b83684381ac87335f06fd8968` (phase `http_request_cache_settings`), rule
  `c87f100f126d41139d20b96c7fcab229` ("Cache API GET requests",
  expr `starts_with(http.request.uri.path, "/api/") and http.request.method eq "GET"`).
- `action_parameters.browser_ttl`: `{"default":86400,"mode":"override_origin"}` →
  `{"mode":"respect_origin"}`. `edge_ttl` was already `respect_origin`; `cache:true` unchanged.
- Needs a token with `Zone → Cache Rules: Edit` + `Account → Account Rulesets: Edit` (the GSM
  `CLOUDFLARE_API_TOKEN` was broadened to include these — consider narrowing it back to
  `Cache Purge: Purge` now that this one-time change is done).

Re-confirm with **GET** (not HEAD — the rule only matches `method eq "GET"`, so a HEAD shows
`cf-cache-status: DYNAMIC` with no `cache-control`):

```bash
curl -s -o /dev/null -D - 'https://api.tinboker.com/api/ticker-insights/by-ticker/2330' \
  | grep -i 'cache-control\|cf-cache-status'
# now: cache-control: public, s-maxage=3600, max-age=3600, stale-while-revalidate=7200  (no max-age=86400)

curl -s -o /dev/null -D - 'https://api.tinboker.com/api/search/suggest?q=2330' \
  | grep -i 'cache-control\|cf-cache-status'
# now: cache-control: public, s-maxage=60, stale-while-revalidate=30   (origin header passes through)
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
