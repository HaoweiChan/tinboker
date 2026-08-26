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
| `SOCIAL_PUBLISH_SLOTS` | to auto-post | TW times, e.g. `11:30,15:30,20:30`. Empty ⇒ this env never auto-posts. **Set it on exactly one environment** — dev/staging/prod all load the same tokens. |
| `SOCIAL_PUBLISH_SCAN_LIMIT` | no (default 10) | How many recent episodes each slot scans; the ledger decides what actually posts. |
| `SOCIAL_COMMENT_SYNC_MINUTES` | to answer comments | How often to pull + triage new comments. 0 (default) = off. Same one-environment rule. |
| `SOCIAL_COMMENT_MODEL` | no (default `google/gemini-2.5-flash`) | OpenRouter model used to classify a comment and draft a reply. |
| `SOCIAL_COMMENT_AUTO_REPLY_CAP` | no (default 3) | Most unattended replies per sync. |
| `SITE_URL` | no (default `https://tinboker.com`) | Origin used for episode permalinks. |

### Endpoints

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | `/api/admin/threads/publish?dry_run=true&limit=10` | admin JWT **or** `TINBOKER_SOCIAL_TOKEN` | Dry-run by default — returns composed drafts. `dry_run=false` posts. |
| GET | `/api/admin/threads/posts` | admin JWT | The idempotency ledger (what's been posted). |

### When posting happens

The backend posts on its own schedule (`SOCIAL_PUBLISH_SLOTS`, TW time), checked by the
60s social worker. Ingest no longer triggers posting: it runs four times a day
(02/08/14/20:10) for site freshness, and a third of the output used to land at
01:00–03:00 TW — the worst-performing window measured (median 376 views vs 762 at
20:00, Aug 2026). Episodes ingested overnight now wait for the next daytime slot.

`SOCIAL_AUTOPUBLISH` stays in the pipeline's `.env`, but its only remaining job is
pre-rendering social-card PNGs at ingest so a slot has something to post.

### Comment triage

`threads_comments` holds every reply that is actually addressed to us, with a category,
a verdict and a draft. The admin Social page's 留言 tab is where they get answered.

Three filters run before the model, and cost nothing:

* our own reply-chain posts (`is_reply_owned_by_me`);
* known bots — `@meta.ai` answered two of our commenters unprompted, and replying starts
  a bot-to-bot thread in public;
* replies whose parent is not our post or one of our own chain comments. Threads'
  `/conversation` returns the whole tree, so most entries in a busy thread are people
  talking to each other; answering those reads as barging in.

What survives gets one model call: category (`praise` / `question` / `substantive` /
`hostile` / `noise` / `promo` / `bot`), whether it carries a checkable factual claim,
whether it asks something, and a draft reply in the house voice.

`decide()` routes it, and that routing is deliberately in Python rather than in the
prompt — it is the part that must not drift:

* `hostile` / `noise` / `promo` / `bot` → ignored, no draft;
* plain `praise` with no factual claim, no question and nothing that looks like a
  position (a ticker, 買/賣/停損/目標價 …) → replied unattended;
* everything else → the 留言 tab.

Measured against the 33 real comments from 2026-06-15 to 08-26: 6 excluded by rule,
7 ignored (1 hostile, 5 noise, 1 promo), 20 queued for review, **0 auto-replied** —
plain praise essentially does not occur on this account. The unattended lane exists,
but in practice a human sees everything.

Hiding a reply needs the `threads_manage_replies` scope; see
`docs/social-publishing-tokens.md`.

### The idempotency ledger

One Postgres table, `social_posts`, keyed `(platform, episode_id)` — shared by Threads
and Facebook and by all three environments. A row is inserted **before** posting
(`social_ledger.claim`), so two overlapping triggers cannot both start on the same
episode; a failed publish releases the claim so the next slot retries.

It used to be two SQLite tables inside the container, with no volume — every redeploy
wiped it and re-posted everything still inside `THREADS_MAX_AGE_DAYS` (24 of 63 Threads
posts in Aug 2026 were duplicates). `backend/scripts/ops/seed_social_ledger.py` is the
one-off that rebuilt the ledger from what was already live on each platform.

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
