# Google login setup

The frontend uses `@react-oauth/google`. `src/main.tsx` provides the Google OAuth
context; `src/components/auth/GoogleLoginButton.tsx` starts sign-in; and
`src/services/api/auth.ts` sends the resulting token to `POST /api/auth/google`. The
backend verifies it and returns the application's session.

## Local development

1. Install dependencies with `npm install` from `frontend/`.
2. Start Vite with `npm run dev -- --port 5173 --strictPort`. The dev API allows
   `http://localhost:5173` as an origin.
3. If Google sign-in is needed and no client ID is already supplied by your
   environment, set `VITE_GOOGLE_CLIENT_ID` in gitignored `frontend/.env.local`. Use
   an OAuth web client authorized for the local origin. Keep credential values out of
   documentation and commits.
4. The frontend calls `https://dev-api.tinboker.com` by default in dev mode. To
   use a local backend, set `VITE_API_BASE_URL=http://localhost:5174` in `.env.local`.

The deployed dev and staging sites require an authorized account at the environment
gate. A local Vite dev server does not apply that gate. See the root
[QA workflow](../../../docs/workflows/qa-flow.md) for environment access and
[infra runbook](../../../docs/infra-runbook.md) for deployed variable configuration.

The older [complete reference](../google-login-complete-reference.md) is a historical
snapshot; it contains retired mock-login and deployment instructions.
