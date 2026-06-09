# Threads auto-posting + SEO monitoring

Two related features on the backend:

1. **Threads auto-posting** — fan new episode summaries out to the brand's Threads
   account, composed from the agents pipeline's contract fields.
2. **SEO monitoring** — read Google Search Console analytics + serve a dynamic
   episode sitemap so Google can discover every episode page.

Both are **credential-gated and dry-run-safe**: with no secrets configured, the
publish endpoint composes drafts without posting and the SEO endpoints report
`configured: false`. Nothing posts or calls Google until you set the env vars below.

> Reminder: Threads is **distribution / referral traffic**, not SEO. The SEO needle
> is moved by the sitemap + on-page markup + Search Console; Threads drives clicks
> back to the (indexable) episode pages. They're complementary, not the same lever.

---

## 1. Threads auto-posting

### Flow

```
agents pipeline ingests an episode (Firestore)
   └─ POST {platform}/api/admin/threads/publish?dry_run=false   (TINBOKER_SOCIAL_TOKEN)
         └─ scan recent episodes → skip already-posted / too-old / contentless
               └─ compose zh-TW post (title + key_insights + ticker #tags + permalink)
                     └─ Threads Graph API: create container → publish
                           └─ record episode_id in the `threads_posts` ledger (idempotent)
```

Example composed post (181/500 chars):

```
股癌｜輝達財報與台積電法說會解析

• 輝達資料中心營收年增超過 100%，AI 需求未見放緩
• 台積電 CoWoS 產能持續滿載，2025 先進製程報價看漲
• 美光記憶體報價觸底反彈，HBM 訂單能見度高

#台股 #投資理財 #財經 #NVDA #2330 #MU

▶ 完整重點：https://tinboker.com/episode/EP168
```

### One-time setup (Meta)

1. Create a Meta app and add the **Threads API** use case
   (https://developers.facebook.com/docs/threads/get-started).
2. Add the brand's Threads account as a tester / connect it; grant
   `threads_basic` + `threads_content_publish`.
3. Generate a **long-lived access token** (~60 days; refresh before expiry) and note
   the account's **numeric user id** (`GET /me?fields=id` on the Threads API).
4. Store both in GCP Secret Manager:
   - `THREADS_ACCESS_TOKEN`
   - `THREADS_USER_ID`

### Env vars (backend)

| Var | Required | Purpose |
|-----|----------|---------|
| `THREADS_ACCESS_TOKEN` | to post | Long-lived Threads token. Unset ⇒ dry-run only. |
| `THREADS_USER_ID` | to post | Numeric Threads account id. |
| `TINBOKER_SOCIAL_TOKEN` | for headless trigger | `openssl rand -hex 32`. Lets the agents pipeline call publish without an admin JWT. Scoped to the publish endpoint only. |
| `THREADS_MAX_AGE_DAYS` | no (default 4) | Recency guard — only post episodes published within N days. Caps blast radius even if the ledger is wiped. |
| `SITE_URL` | no (default `https://tinboker.com`) | Origin used for episode permalinks. |

### Endpoints

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/api/admin/threads/publish?dry_run=true&limit=10` | admin JWT **or** `TINBOKER_SOCIAL_TOKEN` | Dry-run by default — returns composed drafts. `dry_run=false` posts. |
| GET | `/api/admin/threads/posts` | admin JWT | The idempotency ledger (what's been posted). |

### Wiring the agents pipeline (other repo)

The agents runners already have `TINBOKER_PLATFORM_API_URL`. After an ingest run, add:

```bash
curl -fsS -X POST "$TINBOKER_PLATFORM_API_URL/api/admin/threads/publish?dry_run=false" \
  -H "Authorization: Bearer $TINBOKER_SOCIAL_TOKEN"
```

Idempotency + the recency window make this safe to call every run. Until you trust
it, run with `dry_run=true` and inspect the drafts.

### Durability note

The `threads_posts` ledger lives in the backend SQLite store (`data/tinboker.db`),
same as comments/news. If that store is ever reset, the recency window
(`THREADS_MAX_AGE_DAYS`) bounds re-posting to the last few days rather than the whole
back catalog.

---

## 2. SEO monitoring

### Dynamic sitemap

`GET /sitemap.xml` (public, no auth) lists the static routes **plus every recent
episode permalink**, with `lastmod` from `released_at_ms`. This supersedes the
hand-maintained `frontend/public/sitemap.xml` (which is stale and hardcodes EP155/156).

**To use it:** submit `https://api.tinboker.com/sitemap.xml` directly in Search
Console, **or** add a Cloudflare route so `tinboker.com/sitemap.xml` proxies to the
backend endpoint (preferred — keeps the sitemap on the canonical host).

### Search Console analytics

Reuses the Google service account the backend already runs with. One-time setup:

1. Verify the `tinboker.com` property in Search Console (DNS or the existing
   Cloudflare/GA verification).
2. In Search Console → **Settings → Users and permissions**, add the backend's
   service-account email (the one in `gcp-service-account.json`) as a **Full** or
   **Restricted** user.
3. Set env vars:

| Var | Required | Purpose |
|-----|----------|---------|
| `GSC_SITE_URL` | to enable | Property id. Domain property ⇒ `sc-domain:tinboker.com`. Unset ⇒ monitoring disabled. |
| `GOOGLE_APPLICATION_CREDENTIALS` | no | Path to the service-account JSON. Falls back to ADC (the same creds firebase-admin uses on the VPS). |

### Endpoints

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| GET | `/api/admin/seo/overview?days=28&refresh=false` | admin JWT | Totals + top 25 queries + top 25 pages (clicks / impressions / CTR / position). Cached; `refresh=true` pulls live. |
| POST | `/api/admin/seo/refresh?days=28` | admin JWT | Force a live pull and cache it. |

A scheduled `POST /api/admin/seo/refresh` (e.g. daily, via the same cron that
triggers Threads) keeps the cache warm so the admin dashboard reads instantly.

---

## Quick test (no credentials needed)

```bash
# Sitemap (public)
curl -s https://dev-api.tinboker.com/sitemap.xml | head

# Dry-run Threads compose (admin JWT or social token)
curl -s -X POST "https://dev-api.tinboker.com/api/admin/threads/publish?dry_run=true" \
  -H "Authorization: Bearer $TOKEN" | jq '.posted[].text'
```
