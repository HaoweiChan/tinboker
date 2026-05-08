# Google Login Setup Guide

This guide details how to configure and enable Google Authentication for the TrendBrief (TinBoker) WebUI.

## 1. Google Cloud Console Configuration

To enable "Sign in with Google", you need a Google Cloud Project with OAuth credentials.

1.  **Go to Google Cloud Console**: [https://console.cloud.google.com/](https://console.cloud.google.com/)
2.  **Create a New Project** (e.g., "TrendBrief-Dev").
3.  **Configure OAuth Consent Screen**:
    *   Navigate to **APIs & Services > OAuth consent screen**.
    *   Select **External** (for testing) or **Internal** (if organization-only).
    *   Fill in app name ("TrendBrief"), support email, etc.
    *   **Scopes**: Add `userinfo.email` and `userinfo.profile`.
    *   **Test Users**: Add your own email for testing.
4.  **Create Credentials**:
    *   Navigate to **APIs & Services > Credentials**.
    *   Click **Create Credentials > OAuth client ID**.
    *   **Application type**: Web application.
    *   **Name**: "Web Client 1".
    *   **Authorized JavaScript origins**:
        *   `http://localhost:5173` (for local development)
        *   `https://your-production-domain.com` (for production)
    *   **Authorized redirect URIs**:
        *   `http://localhost:5173`
        *   `http://localhost:5173/auth/callback` (if using redirect flow)
5.  **Copy Client ID**: You will need this string (e.g., `123456-abcde.apps.googleusercontent.com`).

## 2. Frontend Configuration

### Environment Variables

Create or update the `.env` file in the project root:

```bash
# .env or .env.local
VITE_GOOGLE_CLIENT_ID=your-google-client-id-here
VITE_API_URL=http://localhost:8000/api
```

### Dependencies

The project uses `@react-oauth/google` for handling the OAuth flow.

```bash
npm install @react-oauth/google
```

### Implementation Details

*   **Provider**: The app is wrapped in `GoogleOAuthProvider` in `src/main.tsx`.
*   **Store**: `src/store/useAppStore.ts` manages the `user` and `token` state.
*   **Login Button**: `src/components/auth/LoginButton.tsx` handles the login click and success callback.
*   **Verification**: `src/services/api/auth.ts` sends the Google token to the backend.

## 3. Backend Integration (Required)

The frontend currently uses a **mock implementation** for successful login if the backend is unavailable or the token verification fails in dev mode. For production, the backend MUST implement the verification endpoint.

### Required Endpoint

**`POST /api/auth/google`**

*   **Request**: `{ "idToken": "..." }` (or `accessToken` depending on flow)
*   **Logic**:
    1.  Verify the token using Google libraries (e.g., `google-auth-library` for Python/Node).
    2.  Extract user info (sub, email, name).
    3.  Create/Update user in DB.
    4.  Return a session JWT.
*   **Response**:
    ```json
    {
      "user": { "id": "...", "name": "...", "email": "..." },
      "token": "backend-jwt-token"
    }
    ```

See `docs/api-gaps.md` for more details on the API contract.

## 4. Testing Local Development

1.  Set `VITE_GOOGLE_CLIENT_ID` in `.env`.
2.  Run `npm run dev`.
3.  Click "登入" in the header.
4.  Complete the Google popup flow.
5.  **Note**: Until the backend is ready, the frontend may log an error in the console or fallback to a mock user ("Demo User") if configured in `src/services/api/auth.ts`.
