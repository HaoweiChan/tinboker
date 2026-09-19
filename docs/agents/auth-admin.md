# Auth & admin domain

Tool-neutral reference for any agent working on authentication (Google OAuth, JWT, dev bypass), user profile/watchlist/settings, the admin dashboard, dev portal, or admin analytics/translations. For code style, defer to [`backend/AGENTS.md`](../../backend/AGENTS.md) and [`frontend/AGENTS.md`](../../frontend/AGENTS.md).

## Scope

Two distinct auth surfaces plus a shared "logged-in user" experience:

1. **User auth** — Google OAuth → JWT for end users. Drives profile, watchlist, comments, notifications.
2. **Admin auth** — password + JWT (single shared password from Secret Manager) for admin/dev-portal pages.
3. **Dev bypass** — non-production-only path that issues a JWT given a secret token, enabling automated browsers to test without OAuth.

## Key files

### Backend

| Concern | File |
|---|---|
| Google OAuth + user JWT + dev bypass | [`backend/src/routers/auth.py`](../../backend/src/routers/auth.py), [`backend/src/utils/auth.py`](../../backend/src/utils/auth.py) |
| User profile, watchlist, preferences | [`backend/src/routers/user.py`](../../backend/src/routers/user.py), [`backend/src/database/user_db.py`](../../backend/src/database/user_db.py) |
| Admin auth (password → admin JWT) | look in [`backend/src/routers/auth.py`](../../backend/src/routers/auth.py) for admin endpoints; admin JWT is signed with `ADMIN_JWT_SECRET` |
| Admin analytics | [`backend/src/routers/admin_analytics.py`](../../backend/src/routers/admin_analytics.py) |
| Admin translations | [`backend/src/routers/admin_translations.py`](../../backend/src/routers/admin_translations.py) |
| Admin system status (Docker, Redis, uptime) | [`backend/src/routers/admin_system.py`](../../backend/src/routers/admin_system.py), [`backend/src/services/system_service.py`](../../backend/src/services/system_service.py) |
| Notifications | [`backend/src/routers/notifications.py`](../../backend/src/routers/notifications.py), [`backend/src/services/notification_service.py`](../../backend/src/services/notification_service.py) |

### Frontend

| Concern | File |
|---|---|
| Profile / watchlist / settings | [`frontend/src/pages/ProfilePage.tsx`](../../frontend/src/pages/ProfilePage.tsx), [`frontend/src/pages/WatchlistPage.tsx`](../../frontend/src/pages/WatchlistPage.tsx), [`frontend/src/pages/SettingsPage.tsx`](../../frontend/src/pages/SettingsPage.tsx) |
| Admin layout + dashboard | [`frontend/src/pages/AdminPage.tsx`](../../frontend/src/pages/AdminPage.tsx), [`frontend/src/pages/AdminDashboardPage.tsx`](../../frontend/src/pages/AdminDashboardPage.tsx) |
| Admin analytics / translations | [`frontend/src/pages/AdminAnalyticsPage.tsx`](../../frontend/src/pages/AdminAnalyticsPage.tsx), [`frontend/src/pages/AdminTranslationsPage.tsx`](../../frontend/src/pages/AdminTranslationsPage.tsx) |
| Dev portal | [`frontend/src/pages/DevPortalPage.tsx`](../../frontend/src/pages/DevPortalPage.tsx), [`frontend/src/pages/DevGrafanaPage.tsx`](../../frontend/src/pages/DevGrafanaPage.tsx), [`frontend/src/pages/DevTranslationsPage.tsx`](../../frontend/src/pages/DevTranslationsPage.tsx), [`frontend/src/pages/DevPodcasterListPage.tsx`](../../frontend/src/pages/DevPodcasterListPage.tsx) |
| Dev bypass entry | [`frontend/src/pages/DevBypass.tsx`](../../frontend/src/pages/DevBypass.tsx) |
| Auth components | [`frontend/src/components/auth/`](../../frontend/src/components/auth/) |
| Admin components | [`frontend/src/components/admin/`](../../frontend/src/components/admin/) |
| API clients | [`frontend/src/services/api/auth.ts`](../../frontend/src/services/api/auth.ts), `user.ts`, `userSettings.ts`, `analytics.ts`, `notifications.ts`, `system.ts` |
| Global app store (auth + user state) | [`frontend/src/store/useAppStore.ts`](../../frontend/src/store/useAppStore.ts) |

## Conventions

### User auth

- **Google OAuth → JWT** signed with `JWT_SECRET_KEY` (from Secret Manager).
- **Token storage:** JWT goes in `localStorage`. On 401 from any API request, the client clears the token and redirects to the login form.
- **Admin emails allowlist** lives in `ADMIN_EMAILS` (comma-separated, from Secret Manager). Only those emails can access admin/dev-portal routes after Google login.

### Admin auth

- **Single shared password** stored in `ADMIN_PASSWORD` (Secret Manager).
- `POST /api/admin/auth/login` with `{password}` returns `{access_token, token_type: "bearer", expires_in: 86400}`.
- Admin tokens signed with `ADMIN_JWT_SECRET` (separate key from user JWT).
- 24-hour expiry. Expired/invalid token → 401 with message; UI auto-redirects to login.

### Dev bypass (non-production only)

- **Endpoint:** `POST /api/auth/dev-token` with `{token}` returns the same shape as Google OAuth (JWT + user object).
- **Activation conditions:** `ENVIRONMENT != production` AND `DEV_BYPASS_TOKEN` env var is set.
- **Frontend entry:** `/auth/dev-bypass` ([`DevBypass.tsx`](../../frontend/src/pages/DevBypass.tsx)) — a form (secret in the POST body), or `?token=SECRET[&role=viewer|admin]` for scripted runners; calls the backend and stores the JWT.
- **Roles:** `admin` (default, first `ADMIN_EMAILS` entry) or `viewer` (`qa-viewer@tinboker.com`: passes the env gate via `is-admin`'s `env_access`, is not an admin). Tokens carry `dev_bypass` + `role`, survive `/refresh`, and are rejected by `verify_jwt_token` when `ENVIRONMENT=production` (all envs share one JWT secret). Procedure: [`../workflows/qa-flow.md`](../workflows/qa-flow.md).
- **Browser MCP / Playwright flow:** navigate to the URL above, wait for redirect to `/`, then drive the app as an authenticated session.
- **Token (Dev env):** the `DEV_BYPASS_TOKEN` is a rotating secret, never stored in the repo. Fetch it with:
  ```bash
  gcloud secrets versions access latest --secret=DEV_BYPASS_TOKEN --project=gen-lang-client-0901363254
  ```
  It is also set as an env var on the VPS backend container. Never paste the value into docs, commits, or chat transcripts.

### Admin dashboard layout

- Sidebar with: Dashboard (home), Translations, Analytics, System. Highlight current section.
- Mobile (< 768px): sidebar collapses to a menu button; content goes full-width.
- Dashboard home shows status cards for Docker containers (Backend, Redis), DB pool, uptime — colors `green/yellow/red` for `healthy/warning/error`.
- Netdata charts embedded via iframe (proxied through Caddy under `/netdata/*`).

### Admin translations UI

- `/admin/translations` shows paginated table with search, market filter, status filter.
- Inline editing on `name_zh_tw` cells — save on blur.
- "Missing translations" view at `/admin/translations/missing?market=US`.
- Bulk CSV/JSON import via `POST /api/admin/translations/bulk-import`.

### Notifications

- `new_episode` notifications fire when an episode row first appears in the Postgres mirror (`firestore_mirror.episodes.first_seen_at` high-water mark). See [`../firestore-contract.md`](../firestore-contract.md) §6.3 — `created_time` must still never be mutated on regeneration (feeds and sort order consume it).
- `stock_mention` notifications fire when a new episode's `related_tickers` intersects the user's `watchlist`.

## Common pitfalls

- **BUG-13 (low):** [`backend/src/utils/auth.py`](../../backend/src/utils/auth.py) had a synchronous `time.sleep(2)` in the Google clock-skew retry. Under async load this freezes ALL concurrent requests for 2s. Use `await asyncio.sleep(2)` per [`CLAUDE.md`](../../CLAUDE.md) "Do Not" rules.
- **Admin endpoint 401 vs 500.** Always return 401 for missing/invalid/expired tokens — never 500. Test: `curl -H "Authorization: Bearer bad" ...` should be 401.
- **Don't bypass the admin email allowlist.** The Google-login flow checks `ADMIN_EMAILS` before granting admin UI access. Skipping that check is a security regression.
- **Dev bypass token in URL.** It's a secret; never log full URLs (with query string) in production. Production must reject the endpoint entirely.
- **JWT secret in dev fallback.** If Secret Manager isn't configured locally, the app falls back to env var or generates a random secret with a warning. Don't ship code that silently bypasses this — log the fallback.
- **Admin content-source edits must bust caches.** `/admin/sources` toggles (`PUT/POST/DELETE /api/admin/sources*`) write to the `content_sources` table, but the public catalog is Redis- and Cloudflare-cached. The router's `_invalidate_source_caches()` ([`backend/src/routers/admin_sources.py`](../../backend/src/routers/admin_sources.py)) clears the Redis allowlist/list keys and purges the current env's CDN host after each write — best-effort (logged, never raised). If you add another source-mutating endpoint, call it too, or edits won't show up until the TTLs expire (edge ≤1h, browser per the `/api/*` rule). The public site still also browser-caches; see [`../infra-runbook.md`](../infra-runbook.md) §1.4.

## External integrations

- **GCP Secret Manager** — all auth secrets (`JWT_SECRET_KEY`, `ADMIN_PASSWORD`, `ADMIN_JWT_SECRET`, `ADMIN_EMAILS`, `DEV_BYPASS_TOKEN`).
- **Google OAuth** — user login; `GOOGLE_CLIENT_ID` injected into the frontend at build time.
- **Postgres** `public.users` — one row per user, keyed by `id` (uuid4); notifications live in `user_notifications` (was Firestore `users/{user_id}` and its `notifications` subcollection until P3 of the Firestore exit, [`../firestore-contract.md`](../firestore-contract.md) §11.5).
- **Netdata** — embedded into admin dashboard via Caddy reverse proxy.

### Membership

- `users.member_until` (nullable, timezone-aware) is the entitlement column; a user is a member iff it's set and in the future — `is_active_member()` / `UserResponse.is_member` in [`backend/src/models/user.py`](../../backend/src/models/user.py) is the single source of truth (naive SQLite datetimes are treated as UTC).
- `require_member` ([`backend/src/utils/dependencies.py`](../../backend/src/utils/dependencies.py)) gates a route on it: 401 anonymous, 402 signed-in-but-not-a-member.
- Frontend: `MemberGate` ([`frontend/src/components/auth/MemberGate.tsx`](../../frontend/src/components/auth/MemberGate.tsx)) is the content-side equivalent.
- Manual grant (no billing yet): `PUT /api/admin/members/{email}` and `GET /api/admin/members`, in [`backend/src/routers/admin_members.py`](../../backend/src/routers/admin_members.py).
- **Rule:** member-only data goes on separate endpoints with `CacheProfile.PRIVATE` — never add member fields to a `cdn_cached` route, because Cloudflare caches every `GET /api/*` by URL with no Vary on Authorization ([`../infra-runbook.md`](../infra-runbook.md) §1.4).
- **Billing (PR 3a, no checkout yet):** `subscriptions` / `payment_events` tables ([`backend/src/database/models.py`](../../backend/src/database/models.py)). Every row carries `gateway_env` (`sandbox`/`production`) because dev/staging/prod share one Postgres but NewebPay's sandbox and production are separate merchant accounts; `Settings.newebpay_env` derives it from `ENVIRONMENT` (never a configured field, so it cannot disagree with which credential set — `newebpay_merchant_id`/`_hash_key`/`_hash_iv` for production, `newebpay_sandbox_*` for everything else, both GSM-backed — is actually in use). `payment_events` dedupes on `(mer_order_no, already_times, kind)`, not `period_no`: NewebPay's first-auth result carries no `AlreadyTimes` (written as `0`), so a `period_no`-keyed constraint would let two first-auth deliveries both through (NULLs are distinct in SQL). A partial unique index caps each user at one `status='active'` subscription (backstop only — PR 3b must also check inside the checkout transaction). [`backend/src/services/newebpay.py`](../../backend/src/services/newebpay.py) is pure AES-256-CBC hex crypto — Periodic has no TradeSha, so a decryptable payload is the *only* authenticity check; a notify handler must still re-verify amount/order against the `subscriptions` row before trusting it. `GET /api/billing/plans` (public) reports price + founding-seat availability, advisory only (60s edge cache, non-transactional count); the founding-price offer is capped at `membership_founding_limit` seats, counting `active`/`cancelled` (already-paid) rows in the current `gateway_env` only.
- **PR 3b contract:** re-check founding seats inside the checkout transaction, not from `/plans`; write first auth as `already_times=0`, mapping NewebPay's `MerchantOrderNo` echo to our `mer_order_no`; re-verify amount + order against the `subscriptions` row on every notify (decryptability is the only authenticity signal); `ProdDesc` charset is 中/英/數/空格/底線 only; `next_auth_date` is a Taipei-local date — never compare it against a UTC "today"; non-production checkout restricted to `is_admin_email` (a sandbox test-card payment would otherwise grant real membership through the shared DB); every `member_until` write goes through `set_member_until`.

## Cross-references

- Dev bypass token + browser-MCP flow: [`../workflows/qa-flow.md`](../workflows/qa-flow.md) and [`CLAUDE.md`](../../CLAUDE.md) "Browser MCP — Dev Environment Auth Bypass" section
- User/notification schemas: [`../firestore-contract.md`](../firestore-contract.md) §6
- Backend code style: [`../../backend/AGENTS.md`](../../backend/AGENTS.md)
- Frontend conventions: [`../../frontend/AGENTS.md`](../../frontend/AGENTS.md)
