# QA flow

Procedure for QA-ing an environment, reproducing the known bugs in [`../issues.md`](../issues.md), and using the dev-bypass token for automated browser testing. The full QA suite (every endpoint, every page, every CI check) lives in [`../agents/qa-tester.md`](../agents/qa-tester.md) — this doc is the procedural overlay: when and how to use it.

## When to run

| Pipeline stage | Subset to run |
|---|---|
| Local feature work | `L` environment §2 (Backend API spot checks) + §3 (Frontend smoke for changed surface) |
| Pre-merge to `develop` | `L` full §1–§3 + §4.1 CI gate check |
| Pre-merge to `main` | `L → D → S` full §1–§5 |
| Post-prod deploy | `P` §1 health + §3 critical frontend pages + §6 perf baselines |

The leftmost column letter (`L`/`D`/`S`/`P`) matches the environment IDs at the top of [`../agents/qa-tester.md`](../agents/qa-tester.md).

## Quick smoke (recommended starting point)

A copy-paste smoke script is in [`../agents/qa-tester.md`](../agents/qa-tester.md) §8. Save as `qa_smoke.sh`, then:

```bash
./qa_smoke.sh https://staging-api.tinboker.com https://staging.tinboker.com
./qa_smoke.sh https://api.tinboker.com https://tinboker.com
```

Passes iff: `/health` healthy + Redis connected + Redis URL NOT exposed + stocks/podcasts/graphs/search-suggest return non-empty + auth correctly rejects invalid tokens + frontend + manifest load.

## Known-issue regression checks

These were the historical platform bugs. **All but BUG-2 are resolved** (see
[`../issues.md`](../issues.md)) — the recipes below now serve as regression assertions: every row
except BUG-2 should pass. Full context is in [`../agents/qa-tester.md`](../agents/qa-tester.md) and
[`../issues.md`](../issues.md):

| Bug | What to run | Owner doc |
|---|---|---|
| BUG-1 (search broken) | `curl -s "{API}/api/search/suggest?q=apple"` → expect non-empty `stocks` array | [`../agents/search-discovery.md`](../agents/search-discovery.md) |
| BUG-2 (heatmap blank) | Load `/industry` in browser; S&P 500 heatmap should render colored cells, not empty | [`../agents/graph-visuals.md`](../agents/graph-visuals.md) |
| BUG-4 (CI never blocks) | `grep -n "continue-on-error\||| echo" .github/workflows/backend-ci.yml` → expect zero hits | [`../agents/devops-infra.md`](../agents/devops-infra.md) |
| BUG-5 (Zod marketCapTier) | Open `/story` in browser; console must not show `Schema validation failed: data.nodes.0.data.marketCapTier` | [`../agents/graph-visuals.md`](../agents/graph-visuals.md) |
| BUG-7 (fabricated stats) | Load `/stock/AAPL`; verify Open is NOT exactly `price × 0.98`, P/E is NOT exactly `15.4` | [`../agents/stock-data.md`](../agents/stock-data.md) |
| BUG-9 (stale CORS) | `curl -H "Origin: https://trendbrief.xyz" -X OPTIONS https://api.tinboker.com/api/stocks -I` → must NOT echo that origin | [`../agents/devops-infra.md`](../agents/devops-infra.md) |
| BUG-10 (recs 404) | `curl -s "{API}/api/recommendations/by-ticker/2330"` → 200; `/api/recommendations/ticker/2330` → 404 | [`../agents/podcast-domain.md`](../agents/podcast-domain.md), [`../agents/stock-data.md`](../agents/stock-data.md) |
| BUG-11 (Redis URL leak) | `curl -s {API}/health \| python3 -c "import sys,json; r=json.load(sys.stdin)['redis']; print('FAIL' if 'connection_string' in r else 'PASS')"` → `PASS` | [`../agents/devops-infra.md`](../agents/devops-infra.md) |

## Browser MCP / Playwright dev-bypass flow

Dev and staging are gated by Google OAuth + admin email allowlist. Automated browsers cannot complete Google OAuth, so they authenticate via the dev-bypass token instead.

### Steps

1. Fetch the current token from GCP Secret Manager (never paste it into docs, commits, or chat):
   ```bash
   gcloud secrets versions access latest --secret=DEV_BYPASS_TOKEN \
     --project=gen-lang-client-0901363254
   ```
2. Navigate to `https://dev.tinboker.com/auth/dev-bypass?token=$DEV_BYPASS_TOKEN`.
3. Wait for redirect to `/` (the page calls `POST /api/auth/dev-token` under the hood and stores the JWT in `localStorage`).
4. Drive the app as an authenticated session.

### Constraints

- **Dev environment only** — the endpoint is disabled when `ENVIRONMENT=production`.
- **Token is a rotating secret, not in the repo** — fetch it from GCP Secret Manager (it is also set as an env var on the VPS backend container). Never hardcode it.
- **Don't log the URL with query string** in any persisted output.
- See [`../agents/auth-admin.md`](../agents/auth-admin.md) "Dev bypass" for the contract.

## Frontend smoke (most-broken-most-often pages)

Per [`../agents/qa-tester.md`](../agents/qa-tester.md) §3, prioritize these surfaces when validating a UI change:

1. **Landing (`/`)** — no `[DEBUG]` console logs (BUG-8), search bar focusable, trending widget non-empty.
2. **Stock dashboard (`/stock/AAPL`, `/stock/2330`)** — chart renders, key stats real (BUG-7), title not doubled (BUG-6), analyst insights load (BUG-10).
3. **Graph gallery (`/story`)** — no Zod errors (BUG-5).
4. **Industry analysis (`/industry`)** — heatmap not blank (BUG-2).
5. **Search overlay** — suggestions appear (BUG-1).
6. **Mobile 375px** — header collapses, chart resizes, cards stack without overflow.

## Verifying a fix

After fixing one of the known bugs:

1. Re-run the exact repro from the bug table above.
2. Run the smoke script.
3. Update [`../issues.md`](../issues.md) to mark the bug fixed (date + commit SHA).
4. Add a regression test if one doesn't exist (see [`backend/AGENTS.md`](../../backend/AGENTS.md) testing pattern).

## Cross-references

- Full QA suite (every endpoint + page): [`../agents/qa-tester.md`](../agents/qa-tester.md)
- Bug catalog with file locations and fix notes: [`../issues.md`](../issues.md)
- Dev bypass details: [`CLAUDE.md`](../../CLAUDE.md) "Browser MCP — Dev Environment Auth Bypass"
- Deploy verification: [`./deploy-flow.md`](./deploy-flow.md) "Verification"
