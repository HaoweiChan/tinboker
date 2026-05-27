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
- **Frontend entry:** `/auth/dev-bypass?token=SECRET` ([`DevBypass.tsx`](../../frontend/src/pages/DevBypass.tsx)) calls the backend and stores the JWT.
- **Browser MCP / Playwright flow:** navigate to the URL above, wait for redirect to `/`, then drive the app as an authenticated session.
- **Token (Dev env):** `CXvkSTaZAghJF0jYidL4ii3DbgOo-Z5NVwgFLoNk05I` — only valid against `dev-api.tinboker.com`. NOT in repo; lives in [`CLAUDE.md`](../../CLAUDE.md) and the VPS `.env`.

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

- `new_episode` notifications fire when a Firestore episode appears with a never-before-seen `created_time`. See [`../firestore-contract.md`](../firestore-contract.md) §6.3 — the contract requires the agents pipeline NOT to mutate `created_time` on regeneration, or notifications re-fire.
- `stock_mention` notifications fire when a new episode's `related_tickers` intersects the user's `watchlist`.

## Common pitfalls

- **BUG-13 (low):** [`backend/src/utils/auth.py`](../../backend/src/utils/auth.py) had a synchronous `time.sleep(2)` in the Google clock-skew retry. Under async load this freezes ALL concurrent requests for 2s. Use `await asyncio.sleep(2)` per [`CLAUDE.md`](../../CLAUDE.md) "Do Not" rules.
- **Admin endpoint 401 vs 500.** Always return 401 for missing/invalid/expired tokens — never 500. Test: `curl -H "Authorization: Bearer bad" ...` should be 401.
- **Don't bypass the admin email allowlist.** The Google-login flow checks `ADMIN_EMAILS` before granting admin UI access. Skipping that check is a security regression.
- **Dev bypass token in URL.** It's a secret; never log full URLs (with query string) in production. Production must reject the endpoint entirely.
- **JWT secret in dev fallback.** If Secret Manager isn't configured locally, the app falls back to env var or generates a random secret with a warning. Don't ship code that silently bypasses this — log the fallback.

## External integrations

- **GCP Secret Manager** — all auth secrets (`JWT_SECRET_KEY`, `ADMIN_PASSWORD`, `ADMIN_JWT_SECRET`, `ADMIN_EMAILS`, `DEV_BYPASS_TOKEN`).
- **Google OAuth** — user login; `GOOGLE_CLIENT_ID` injected into the frontend at build time.
- **Firestore** `graphfolio-db` — `users/{user_id}` and `users/{user_id}/notifications/{notification_id}` (platform-owned writes per [`../firestore-contract.md`](../firestore-contract.md) §6).
- **Netdata** — embedded into admin dashboard via Caddy reverse proxy.

## Cross-references

- Dev bypass token + browser-MCP flow: [`../workflows/qa-flow.md`](../workflows/qa-flow.md) and [`CLAUDE.md`](../../CLAUDE.md) "Browser MCP — Dev Environment Auth Bypass" section
- User/notification schemas: [`../firestore-contract.md`](../firestore-contract.md) §6
- Backend code style: [`../../backend/AGENTS.md`](../../backend/AGENTS.md)
- Frontend conventions: [`../../frontend/AGENTS.md`](../../frontend/AGENTS.md)
- Bugs: BUG-13 (sync sleep in auth) in [`../qa-report-2026-05-09.md`](../qa-report-2026-05-09.md)
