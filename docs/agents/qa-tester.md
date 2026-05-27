# QA tester

Tool-neutral reference for any agent (Claude Code, Codex, Cursor, etc.) tasked with QA-ing the TinBoker platform across environments. Defines the full test suite to run before any release. Pair this with [`../workflows/qa-flow.md`](../workflows/qa-flow.md) for the procedural overlay (when to run which subset, dev-bypass flow) and [`qa-report-2026-05-09.md`](../qa-report-2026-05-09.md) for the catalog of bugs this suite regression-tests against.

---

## Environments Under Test

| ID | Label | Frontend | Backend API | Notes |
|----|-------|----------|-------------|-------|
| L | Local | http://localhost:5173 | http://localhost:5174 | SQLite, no GCP |
| D | Dev | https://dev.tinboker.com | https://dev-api.tinboker.com | Auto-deployed from `develop` |
| S | Staging | `https://{branch}.tinboker-platform.pages.dev` | https://staging-api.tinboker.com | Manual deploy of PR image |
| P | Production | https://tinboker.com | https://api.tinboker.com | `main` branch only |

Run **L → D → S** before every PR merge to `main`. Run **P** after every production deploy.

---

## 1. Infrastructure Health

### 1.1 Backend Health Endpoints

For each environment, hit the health endpoint and verify:

```bash
# Replace {API} with the backend URL for the target environment
curl -s {API}/health | python3 -m json.tool
```

**Expected response shape:**
```json
{
  "status": "healthy",
  "database": "connected",
  "redis": { "status": "connected" },
  "environment": "production"
}
```

**Checks:**
- [ ] `status` is `"healthy"` (not `"degraded"`)
- [ ] `database` is `"connected"`
- [ ] `redis.status` is `"connected"`
- [ ] `environment` matches the target env (`development` / `staging` / `production`)
- [ ] `redis.connection_string` is NOT present in staging/production responses (BUG-11)
- [ ] Response time < 500ms

### 1.2 Backend OpenAPI Docs

```bash
curl -s {API}/docs -o /dev/null -w "%{http_code}"   # expect 200
curl -s {API}/openapi.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['paths']), 'endpoints')"
```

**Checks:**
- [ ] `/docs` returns 200
- [ ] OpenAPI spec lists ≥ 40 endpoints

### 1.3 VPS Container Status (dev/staging/prod only)

```bash
ssh root@152.53.136.182 "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
```

**Expected containers:**
- [ ] `tinboker-backend-prod` — Up (healthy) — port 8000
- [ ] `tinboker-backend-dev` — Up (healthy) — port 8001
- [ ] `tinboker-backend-staging` — Up (healthy) — port 8002 (when active)
- [ ] `redis` — Up
- [ ] `netdata` — Up

**Check restart counts:**
```bash
ssh root@152.53.136.182 "docker inspect --format '{{.RestartCount}} {{.Name}}' \$(docker ps -q)"
```
- [ ] No container has restart count > 3

### 1.4 Redis Cache Health

```bash
curl -s {API}/health | python3 -c "import sys,json; h=json.load(sys.stdin)['redis']; print('hits:', h.get('hit_count'), 'misses:', h.get('miss_count'))"
```

- [ ] Redis hit rate > 50% on dev/prod (baseline from qa-report-2026-05-09: 35% — needs improvement)
- [ ] No `"error"` key in redis section

### 1.5 Caddy / TLS

```bash
# Check TLS cert validity for each domain
for DOMAIN in api.tinboker.com dev-api.tinboker.com staging-api.tinboker.com; do
  echo -n "$DOMAIN: "
  echo | openssl s_client -servername $DOMAIN -connect $DOMAIN:443 2>/dev/null | openssl x509 -noout -dates
done
```

- [ ] All certs are valid and expire > 14 days from today
- [ ] `curl -I https://api.tinboker.com/health` returns `HTTP/2 200`

### 1.6 CORS Validation

```bash
# Verify production domain is allowed
curl -s -H "Origin: https://tinboker.com" \
     -H "Access-Control-Request-Method: GET" \
     -X OPTIONS https://api.tinboker.com/api/stocks \
     -I | grep -i "access-control"
```

- [ ] `access-control-allow-origin: https://tinboker.com` is present
- [ ] `trendbrief.xyz` is NOT accepted (test: use `-H "Origin: https://trendbrief.xyz"` and verify rejected)

---

## 2. Backend API Tests

Run these against each target environment. Replace `{API}` with the backend URL.

### 2.1 Stock Endpoints

```bash
# List stocks
curl -s "{API}/api/stocks?sort_by=ticker&limit=10"

# Single stock
curl -s "{API}/api/stocks/AAPL"

# Taiwan stock
curl -s "{API}/api/stocks/2330"

# Price history
curl -s "{API}/api/stocks/AAPL/history"
```

**Checks:**
- [ ] Stock list returns array of ≥ 5 items with `ticker`, `name`, `price` fields
- [ ] `AAPL` returns `ticker`, `price`, `changePercent`, `chartData`
- [ ] `2330` (TSMC) returns data — verify Taiwan stocks are working
- [ ] `chartData` contains ≥ 30 OHLCV data points
- [ ] `price` is a non-zero float
- [ ] No stock returns hardcoded dummy values (`price: 100.0` exactly, `pe_ratio: 15.4` exactly) — BUG-7

### 2.2 Search Endpoints

```bash
# Suggest (this has been broken — BUG-1)
curl -s "{API}/api/search/suggest?q=apple"

# Full search
curl -s "{API}/api/search?q=台積電"
```

**Checks:**
- [ ] `/suggest?q=apple` returns non-empty `stocks` array — **BUG-1 regression test**
- [ ] `/search?q=台積電` returns results with `type`, `id`, `title` fields
- [ ] Suggest response time < 200ms (in-memory index should be fast)

### 2.3 Podcast / Episode Endpoints

```bash
curl -s "{API}/api/podcasts"
curl -s "{API}/api/podcasts" | python3 -c "import sys,json; pods=json.load(sys.stdin); name=pods[0]['name'] if pods else None; print(name)" | xargs -I{} curl -s "{API}/api/podcasts/{}"
```

**Checks:**
- [ ] Podcast list returns ≥ 1 item
- [ ] Single podcast has `name`, `description`, `image_url` fields
- [ ] `image_url` is not null or a placeholder path — fallback images are present (BUG previously)

### 2.4 Graph Endpoints

```bash
curl -s "{API}/api/graphs?limit=5"
GRAPH_ID=$(curl -s "{API}/api/graphs?limit=1" | python3 -c "import sys,json; g=json.load(sys.stdin); print(g[0]['id'] if g else '')")
curl -s "{API}/api/graphs/${GRAPH_ID}"
```

**Checks:**
- [ ] Graph list returns array
- [ ] Single graph response has `nodes` and `edges` arrays
- [ ] Nodes have `id`, `data.label` fields
- [ ] Zod `marketCapTier` validation: values are one of `large`, `medium`, `small`, or field is absent — **BUG-5 regression test**

### 2.5 Authentication Endpoints

```bash
# Verify JWT check rejects invalid token
curl -s -H "Authorization: Bearer invalid_token" "{API}/user/me"
```

**Checks:**
- [ ] `/user/me` with invalid token returns 401 (not 500)
- [ ] `/auth/check` endpoint exists and returns 401 without token

### 2.6 Recommendations Endpoint

```bash
curl -s "{API}/api/recommendations/by-ticker/2330"
# Also test the WRONG url to confirm 404
curl -s "{API}/api/recommendations/ticker/2330" -o /dev/null -w "%{http_code}"
```

**Checks:**
- [ ] `/by-ticker/2330` returns 200 with data
- [ ] `/ticker/2330` (old path) returns 404 — confirms BUG-10 is tracked

### 2.7 News Endpoint

```bash
curl -s "{API}/api/news?limit=5&sort_by=date"
```

**Checks:**
- [ ] Returns array with `id`, `title`, `date`, `tickers` fields
- [ ] `date` is a valid ISO date string
- [ ] No future-dated articles (date ≤ today)

### 2.8 WebSocket Smoke Test (Local/Dev Only)

```bash
# Requires wscat: npm install -g wscat
wscat -c "wss://dev-api.tinboker.com/ws/prices" --wait 5
```

- [ ] Connection opens without error
- [ ] At least one price message received within 10 seconds
- [ ] Message has `ticker`, `price`, `timestamp` fields

---

## 3. Frontend UI Tests

Use a browser or Playwright. Visit each URL and verify the checklist.

### 3.1 Landing Page (`/`)

- [ ] Page loads without blank white screen
- [ ] Header shows logo and navigation links
- [ ] Stock feed / trending section has ≥ 3 items
- [ ] No `[DEBUG]` or `[StockHeaderCard]` logs in browser console — **BUG-8 regression test**
- [ ] Search bar is visible and keyboard-focusable
- [ ] Google login button visible (if unauthenticated)

### 3.2 Stock Dashboard (`/stock/AAPL` and `/stock/2330`)

- [ ] Stock name and ticker shown in header
- [ ] Price and change percent displayed (non-zero)
- [ ] TradingView chart renders — not blank
- [ ] Browser tab title does NOT contain duplicate `| TinBoker | TinBoker` — **BUG-6 regression test**
- [ ] Key Statistics section (`關鍵數據`) shows real OHLC values, not fabricated multiples — **BUG-7 regression test**
  - Verify Open ≠ price × 0.98 exactly
- [ ] Analyst insights section (`分析師觀點`) loads data — not always showing "暫無詳細分析觀點" — **BUG-10 regression test**
- [ ] Related episodes panel shows ≥ 1 episode (or "no episodes" message, not spinner stuck)

### 3.3 Graph Gallery (`/story`)

- [ ] Page loads without console errors
- [ ] Graph nodes render inside canvas area
- [ ] No `Schema validation failed: data.nodes.0.data.marketCapTier` in console — **BUG-5 regression test**
- [ ] Clicking a node shows detail panel

### 3.4 Industry Analysis (`/industry`)

- [ ] S&P 500 heatmap (`標普 500 地圖`) renders with colored cells — **BUG-2 regression test**
- [ ] Sector labels visible
- [ ] Hovering a cell shows tooltip with stock name and performance

### 3.5 Search

- [ ] Typing 2+ characters in header search shows autocomplete suggestions
- [ ] Suggestions include stocks and podcasts — **BUG-1 regression test**
- [ ] Pressing Enter navigates to search results page
- [ ] Results page shows cards with name, type, and link

### 3.6 Podcaster Page (`/podcaster/:id`)

- [ ] Podcast image loads (not broken image icon)
- [ ] Episode list renders with title, date, duration
- [ ] Play button triggers audio player
- [ ] Player controls (pause, progress bar) are functional

### 3.7 Navigation & Auth

- [ ] All header nav links navigate without 404
- [ ] Google login flow redirects and returns to app
- [ ] After login, profile icon appears in header
- [ ] Logout clears session and redirects to landing

### 3.8 PWA & Offline

- [ ] `manifest.json` loads at `/manifest.json` (200)
- [ ] Service worker registered (check Application tab in DevTools)
- [ ] Navigating to a cached stock page while offline shows cached content (not blank)

### 3.9 Mobile Responsiveness

Test at 375px viewport width:

- [ ] Header collapses to hamburger menu
- [ ] Stock chart resizes and remains interactive
- [ ] Episode cards stack vertically without overflow

---

## 4. CI/CD Pipeline Checks

### 4.1 Backend CI Gate

Create a PR with an intentionally failing test and verify:

- [ ] `pytest` step reports failure (red X)
- [ ] PR is **blocked** from merging — **BUG-4 regression test**: `continue-on-error: true` must NOT be present in `backend-ci.yml`
- [ ] No `|| echo "::warning::"` swallowing exit codes in test step

Inspect the file directly:
```bash
grep -n "continue-on-error\||| echo" .github/workflows/backend-ci.yml
# Expected: no matches (both patterns should be absent)
```

### 4.2 Docker Image Tags

After a merge to `develop`:
```bash
# Verify image was pushed
curl -s "https://ghcr.io/v2/haoweichan/tinboker-backend/tags/list" \
  -H "Authorization: Bearer $(echo $GHCR_TOKEN | base64 -d)" | python3 -m json.tool
```

- [ ] `develop` tag is present and was updated within last 1 hour
- [ ] `main` tag exists (if production was recently deployed)

### 4.3 Health Check After Deploy

After any deploy to dev/staging/prod:
```bash
# Wait up to 60s for the container to be healthy
for i in $(seq 1 12); do
  STATUS=$(curl -s {API}/health | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null)
  echo "Attempt $i: $STATUS"
  [ "$STATUS" = "healthy" ] && break
  sleep 5
done
```

- [ ] Status reaches `healthy` within 60 seconds
- [ ] No container restart after deploy: `docker inspect --format='{{.RestartCount}}' tinboker-backend-prod` = 0 (or unchanged from before)

### 4.4 Rollback Readiness

Identify the previous image tag before each production deploy:
```bash
ssh root@152.53.136.182 "docker inspect tinboker-backend-prod --format='{{.Config.Image}}'"
```

- [ ] Previous image tag is noted (for manual rollback if needed)
- [ ] Document rollback command: `docker compose -f docker-compose.prod.yml up -d --no-deps backend` with previous `IMAGE_TAG`

---

## 5. Security Spot Checks

### 5.1 Secrets Not Exposed

```bash
# Health endpoint must not expose Redis connection string in staging/prod
curl -s https://api.tinboker.com/health | python3 -c \
  "import sys,json; r=json.load(sys.stdin).get('redis',{}); print('FAIL' if 'connection_string' in r else 'PASS')"
```

- [ ] `PASS` — connection string not in health response — **BUG-11 regression test**

```bash
# OpenAPI spec must not contain any secret-looking strings
curl -s https://api.tinboker.com/openapi.json | grep -i "password\|secret\|api_key\|token" | grep -v "description\|summary\|title"
# Expected: no output
```

- [ ] No secrets in OpenAPI spec

### 5.2 Auth Bypass Attempt

```bash
# Admin endpoints must require auth
curl -s https://api.tinboker.com/api/admin/system -o /dev/null -w "%{http_code}"
# Expected: 401 or 403
```

- [ ] Admin endpoints return 401/403 without credentials

### 5.3 CORS Strict Check (Production Only)

```bash
curl -s -H "Origin: https://evil.com" -X OPTIONS https://api.tinboker.com/api/stocks -I | grep "access-control-allow-origin"
# Expected: no line, or header with value that is NOT "https://evil.com" or "*"
```

- [ ] Arbitrary origins are rejected by CORS

---

## 6. Performance Baselines

Run against production after each release to catch regressions.

```bash
# Stock list p95 latency
for i in $(seq 1 10); do
  curl -s -o /dev/null -w "%{time_total}\n" "https://api.tinboker.com/api/stocks?limit=20"
done | sort -n | tail -2
```

**Baselines (reject if exceeded):**

| Endpoint | p95 Target |
|----------|-----------|
| `GET /api/stocks?limit=20` | < 1.0s |
| `GET /api/stocks/AAPL` | < 1.5s (with cache) |
| `GET /api/search/suggest?q=apple` | < 0.3s (in-memory) |
| `GET /api/podcasts` | < 1.0s |
| Frontend LCP (Lighthouse) | < 2.5s |

- [ ] All endpoints within baseline on production

---

## 7. Pre-Release Checklist

Complete this checklist before every merge to `main`:

### Code Quality
- [ ] `pytest tests/ -v` passes with 0 failures in backend
- [ ] `npm run build` completes without TypeScript errors in frontend
- [ ] `ruff check src/` produces 0 errors in backend
- [ ] `npm run lint` produces 0 errors in frontend
- [ ] No new `continue-on-error: true` in any CI workflow

### Data Integrity
- [ ] Search autocomplete returns real results (BUG-1)
- [ ] Stock key statistics use real API data (BUG-7)
- [ ] Industry heatmap is populated (BUG-2)
- [ ] Graph nodes pass Zod validation (BUG-5)

### Infrastructure
- [ ] All three VPS containers are running and healthy
- [ ] TLS certs valid > 14 days
- [ ] CORS allows `tinboker.com`, `dev.tinboker.com`
- [ ] Health endpoint does not leak Redis connection string

### Deployment Readiness
- [ ] Previous production image tag documented for rollback
- [ ] Backend deployed and healthy on staging before frontend
- [ ] Cloudflare preview URL tested with staging backend

---

## 8. Running the Full Suite

### Automated (CI hook, run on staging before prod deploy)

```bash
#!/bin/bash
# qa_smoke.sh — quick smoke test against any environment
# Usage: ./qa_smoke.sh https://api.tinboker.com https://tinboker.com

BACKEND=${1:-https://api.tinboker.com}
FRONTEND=${2:-https://tinboker.com}
PASS=0; FAIL=0

check() {
  local desc=$1; local cmd=$2; local expected=$3
  result=$(eval "$cmd" 2>/dev/null)
  if echo "$result" | grep -q "$expected"; then
    echo "  PASS  $desc"
    ((PASS++))
  else
    echo "  FAIL  $desc (got: $result)"
    ((FAIL++))
  fi
}

echo "=== Backend Health ==="
check "status healthy"          "curl -s $BACKEND/health | python3 -c \"import sys,json; print(json.load(sys.stdin).get('status',''))\"" "healthy"
check "redis connected"         "curl -s $BACKEND/health | python3 -c \"import sys,json; print(json.load(sys.stdin).get('redis',{}).get('status',''))\"" "connected"
check "no redis connection_str" "curl -s $BACKEND/health | python3 -c \"import sys,json; r=json.load(sys.stdin).get('redis',{}); print('CLEAN' if 'connection_string' not in r else 'EXPOSED')\"" "CLEAN"

echo "=== API Endpoints ==="
check "stocks list"             "curl -s '$BACKEND/api/stocks?limit=5' | python3 -c \"import sys,json; d=json.load(sys.stdin); print('ok' if isinstance(d,list) and len(d)>0 else 'empty')\"" "ok"
check "search suggest"          "curl -s '$BACKEND/api/search/suggest?q=apple' | python3 -c \"import sys,json; d=json.load(sys.stdin); print('ok' if d.get('stocks') else 'empty')\"" "ok"
check "podcasts list"           "curl -s '$BACKEND/api/podcasts' | python3 -c \"import sys,json; d=json.load(sys.stdin); print('ok' if isinstance(d,list) and len(d)>0 else 'empty')\"" "ok"
check "graphs list"             "curl -s '$BACKEND/api/graphs?limit=3' | python3 -c \"import sys,json; d=json.load(sys.stdin); print('ok' if isinstance(d,list) else 'fail')\"" "ok"
check "auth rejects invalid"    "curl -s -o /dev/null -w '%{http_code}' -H 'Authorization: Bearer bad' '$BACKEND/user/me'" "401"
check "admin blocked"           "curl -s -o /dev/null -w '%{http_code}' '$BACKEND/api/admin/system'" "40"

echo "=== Frontend ==="
check "frontend loads"          "curl -s -o /dev/null -w '%{http_code}' '$FRONTEND/'" "200"
check "manifest.json"           "curl -s -o /dev/null -w '%{http_code}' '$FRONTEND/manifest.json'" "200"

echo ""
echo "Results: $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ] && exit 0 || exit 1
```

Save as `qa_smoke.sh`, `chmod +x qa_smoke.sh`, run:

```bash
./qa_smoke.sh https://staging-api.tinboker.com https://staging.tinboker-platform.pages.dev
./qa_smoke.sh https://api.tinboker.com https://tinboker.com
```

---

## Appendix: Known Bugs Tracked by This Suite

| Bug ID | Test Section | Regression Check |
|--------|-------------|-----------------|
| BUG-1 | §2.2 | Search suggest returns non-empty stocks |
| BUG-2 | §3.4 | Industry heatmap has colored cells |
| BUG-4 | §4.1 | CI workflow blocks on test failure |
| BUG-5 | §2.4, §3.3 | Zod `marketCapTier` no console errors |
| BUG-6 | §3.2 | Tab title not doubled |
| BUG-7 | §3.2 | Key stats not fabricated |
| BUG-8 | §3.1 | No `[DEBUG]` console logs in prod |
| BUG-9 | §1.6 | CORS rejects `trendbrief.xyz` |
| BUG-10 | §2.6, §3.2 | Analyst insights load successfully |
| BUG-11 | §5.1 | Health endpoint hides Redis URL |

Full bug catalog with root-cause analysis and file:line citations: [`../qa-report-2026-05-09.md`](../qa-report-2026-05-09.md).

---

## Cross-references

- Procedural overlay (when to run which subset, dev-bypass flow): [`../workflows/qa-flow.md`](../workflows/qa-flow.md)
- Bug catalog with root causes: [`../qa-report-2026-05-09.md`](../qa-report-2026-05-09.md)
- Deploy pipeline + post-deploy verification: [`../workflows/deploy-flow.md`](../workflows/deploy-flow.md)
- Infrastructure runbook (VPS, Caddy, GCP): [`../infra-runbook.md`](../infra-runbook.md)
- Project-wide rules + dev bypass token: [`../../CLAUDE.md`](../../CLAUDE.md)
