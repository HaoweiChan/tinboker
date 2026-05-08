# Google Login Complete Reference

This document provides a comprehensive reference for all Google login related code, setup, and environment variables in the TinBoker WebUI project.

## Table of Contents

1. [Environment Variables](#environment-variables)
2. [Dependencies](#dependencies)
3. [Code Files](#code-files)
4. [Setup & Configuration](#setup--configuration)
5. [Authentication Flow](#authentication-flow)
6. [Development Mode](#development-mode)
7. [Production Deployment](#production-deployment)
8. [Backend API Requirements](#backend-api-requirements)

---

## Environment Variables

### Required Variables

#### `VITE_GOOGLE_CLIENT_ID`
- **Type**: String
- **Required**: Yes (for production)
- **Description**: Google OAuth 2.0 Client ID from Google Cloud Console
- **Format**: `123456789-abcdefghijklmnop.apps.googleusercontent.com`
- **Location**: 
  - Local: `.env.local` or `.env` file in project root
  - Production: Vercel Dashboard > Settings > Environment Variables
- **Usage**: Used to initialize `GoogleOAuthProvider` in `src/main.tsx`

**Example:**
```bash
VITE_GOOGLE_CLIENT_ID=123456789-abcdefghijklmnop.apps.googleusercontent.com
```

#### `VITE_API_BASE_URL`
- **Type**: String
- **Required**: No (has default fallback)
- **Description**: Base URL for the backend API
- **Default**: `https://api.tinboker.com`
- **Location**: Same as `VITE_GOOGLE_CLIENT_ID`
- **Usage**: Used by `src/services/api/client.ts` to configure API requests

**Example:**
```bash
# Local development
VITE_API_BASE_URL=http://localhost:8000

# Production
VITE_API_BASE_URL=https://api.tinboker.com
```

### Environment Variable Files

Create `.env.local` in the project root for local development:

```bash
# .env.local
VITE_GOOGLE_CLIENT_ID=your-google-client-id-here
VITE_API_BASE_URL=http://localhost:8000
```

**Note**: `.env.local` is gitignored and should not be committed to version control.

---

## Dependencies

### `@react-oauth/google`
- **Version**: `^0.12.2` (as of package.json)
- **Purpose**: React library for Google OAuth 2.0 authentication
- **Installation**: 
  ```bash
  npm install @react-oauth/google
  ```
- **Key Exports Used**:
  - `GoogleOAuthProvider`: Context provider component
  - `useGoogleLogin`: Hook for triggering Google login flow

**Package.json Reference:**
```json
{
  "dependencies": {
    "@react-oauth/google": "^0.12.2"
  }
}
```

---

## Code Files

### 1. `src/main.tsx`
**Purpose**: Application entry point that initializes Google OAuth Provider

**Key Code:**
```12:48:src/main.tsx
// Get Google Client ID from environment
// If missing, use a placeholder to prevent app crash, though login will fail
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || 'mock_client_id_to_prevent_crash'

// Debug: Log environment variable status (only in production for debugging)
if (import.meta.env.PROD) {
  console.log('[DEBUG] Environment check:', {
    hasClientId: !!GOOGLE_CLIENT_ID,
    clientIdLength: GOOGLE_CLIENT_ID.length,
    clientIdPreview: GOOGLE_CLIENT_ID ? `${GOOGLE_CLIENT_ID.substring(0, 20)}...` : 'EMPTY',
    allEnvVars: Object.keys(import.meta.env).filter(key => key.startsWith('VITE_'))
  });
}

// Warn if Google Client ID is missing
if (!GOOGLE_CLIENT_ID) {
  const errorMsg = import.meta.env.PROD
    ? '⚠️ VITE_GOOGLE_CLIENT_ID is not set in Vercel!\n' +
    'Steps to fix:\n' +
    '1. Go to Vercel Dashboard > Your Project > Settings > Environment Variables\n' +
    '2. Add: VITE_GOOGLE_CLIENT_ID = your-client-id.apps.googleusercontent.com\n' +
    '3. Select "Production" environment (and "Preview" if needed)\n' +
    '4. Click Save\n' +
    '5. Go to Deployments tab and click "Redeploy" on the latest deployment\n' +
    '6. Wait for deployment to complete'
    : '⚠️ VITE_GOOGLE_CLIENT_ID is not set in .env.local!\n' +
    'Create .env.local file in tinboker-platform/frontend/ with:\n' +
    'VITE_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com';

  console.error(errorMsg);

  // Show user-friendly error in production
  if (import.meta.env.PROD) {
    // Don't block the app, but show a warning
    console.warn('Google login will not work until VITE_GOOGLE_CLIENT_ID is set and the app is redeployed.');
  }
}
```

**Provider Setup:**
```52:66:src/main.tsx
// Conditionally wrap in StrictMode only in production
// StrictMode causes double-mounting in dev which leads to duplicate API calls
const AppWrapper = import.meta.env.PROD ? (
  <StrictMode>
    <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>
      <HelmetProvider>
        <App />
      </HelmetProvider>
    </GoogleOAuthProvider>
  </StrictMode>
) : (
  <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>
    <HelmetProvider>
      <App />
    </HelmetProvider>
  </GoogleOAuthProvider>
);
```

**Key Features:**
- Reads `VITE_GOOGLE_CLIENT_ID` from environment
- Falls back to `'mock_client_id_to_prevent_crash'` if missing (prevents app crash)
- Logs debug information in production mode
- Provides helpful error messages for missing configuration
- Wraps entire app in `GoogleOAuthProvider` to enable OAuth functionality

---

### 2. `src/components/auth/GoogleLoginButton.tsx`
**Purpose**: Main component that handles Google login flow

**Key Code:**
```39:83:src/components/auth/GoogleLoginButton.tsx
  const googleLogin = useGoogleLogin({
    onSuccess: async (tokenResponse) => {
      try {
        // Exchange access token for app session
        const authResponse = await authApi.verifyGoogleToken({
          accessToken: tokenResponse.access_token
        });

        const { user: backendUser, token: appToken } = authResponse;

        login(
          {
            id: backendUser.id,
            name: backendUser.name,
            email: backendUser.email,
            avatar: backendUser.avatar || '',
            initials: backendUser.name
              .split(' ')
              .map((n: string) => n[0])
              .join('')
              .toUpperCase()
              .slice(0, 2),
          },
          appToken
        );

        // Sync user preferences to store
        useAppStore.setState({
          watchlist: backendUser.watchlist || [],
          subscriptions: backendUser.podcast_subscriptions || [],
          alerts: backendUser.alerts || []
        });

        console.log('Login successful');
      } catch (error) {
        console.error('Login failed:', error);
        alert('登入失敗，請稍後再試');
      }
    },
    onError: () => {
      console.error('Google login error');
      alert('Google 登入失敗');
    },
    flow: 'implicit', // Get access token
  });
```

**Development Mode Bypass:**
```15:37:src/components/auth/GoogleLoginButton.tsx
  // Dev mode: Bypass Google OAuth with dummy user
  const devLogin = () => {
    console.log('[DEV] Using dummy login for local development');
    const dummyUser = {
      id: 'dev-user-123',
      name: 'Dev User',
      email: 'dev@tinboker.local',
      avatar: '',
      initials: 'DU',
    };
    const dummyToken = 'dev-token-' + Date.now();
    
    login(dummyUser, dummyToken);
    
    // Set some dummy preferences
    useAppStore.setState({
      watchlist: [],
      subscriptions: [],
      alerts: []
    });
    
    console.log('[DEV] Dummy login successful:', dummyUser);
  };
```

**Click Handler:**
```85:92:src/components/auth/GoogleLoginButton.tsx
  const handleClick = () => {
    // In dev mode, use dummy login
    if (import.meta.env.DEV) {
      devLogin();
    } else {
      googleLogin();
    }
  };
```

**Key Features:**
- Uses `useGoogleLogin` hook from `@react-oauth/google`
- Implements implicit OAuth flow (gets access token directly)
- Exchanges Google access token for backend session token
- Syncs user data and preferences to Zustand store
- Provides development mode bypass for local testing
- Handles errors with user-friendly alerts

---

### 3. `src/components/auth/LoginButton.tsx`
**Purpose**: Wrapper component that provides a simple interface for login button

**Code:**
```1:15:src/components/auth/LoginButton.tsx
import React from 'react';
import { GoogleLoginButton } from './GoogleLoginButton';

interface LoginButtonProps {
  className?: string;
  children?: React.ReactNode;
}

export const LoginButton: React.FC<LoginButtonProps> = ({ className, children }) => {
  return (
    <GoogleLoginButton className={className}>
      {children || '登入'}
    </GoogleLoginButton>
  );
};
```

**Key Features:**
- Simple wrapper around `GoogleLoginButton`
- Provides default text "登入" (Login in Traditional Chinese)
- Allows custom className and children

---

### 4. `src/services/api/auth.ts`
**Purpose**: API service for authentication endpoints

**Key Code:**
```4:21:src/services/api/auth.ts
export interface AuthResponse {
  user: {
    id: string;
    google_id: string;
    email: string;
    name: string;
    avatar?: string;
    email_verified: boolean;
    created_at: string;
    updated_at: string;
    watchlist?: string[];
    podcast_subscriptions?: string[];
    episode_bookmarks?: string[];
    alerts?: string[];
    tag_subscriptions?: string[];
  };
  token: string;
}
```

**API Methods:**
```23:43:src/services/api/auth.ts
export const authApi = {
  verifyGoogleToken: async (data: { idToken?: string; accessToken?: string }): Promise<AuthResponse> => {
    try {
      const response = await apiClient.post<AuthResponse>(
        '/api/auth/google',
        data,
        {
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );
      return response.data;
    } catch (error: any) {
      if (error.isAxiosError || error instanceof AxiosError) {
        const message = error.response?.data?.detail || error.message;
        throw new Error(`Authentication failed: ${message}`);
      }
      throw error;
    }
  },
```

**Additional Methods:**
- `getCurrentUser(token: string)`: Fetches current user info using JWT token
- `logout()`: Logs out user (client-side handled)

**Key Features:**
- Sends Google access token to backend `/api/auth/google` endpoint
- Handles errors with descriptive messages
- Returns user data and JWT token for session management

---

### 5. `src/store/useAppStore.ts`
**Purpose**: Zustand store for global application state including authentication

**User Interface:**
```9:15:src/store/useAppStore.ts
interface User {
  id: string;
  name: string;
  email: string;
  avatar?: string;
  initials?: string;
}
```

**Auth State:**
```70:72:src/store/useAppStore.ts
  // Auth state
  user: User | null;
  token: string | null;
```

**Auth Actions:**
```115:117:src/store/useAppStore.ts
  // Auth Actions
  login: (user: User, token: string) => void;
  logout: () => void;
```

**Login Implementation:**
```337:339:src/store/useAppStore.ts
      // Auth actions
      login: (user, token) => set(() => ({ user, token })),
      logout: () => set(() => ({ user: null, token: null })),
```

**Persistence:**
```565:577:src/store/useAppStore.ts
    {
      name: 'tinboker-storage', // localStorage key
      partialize: (state) => ({
        theme: state.theme,
        token: state.token,
        user: state.user,
        watchlist: state.watchlist,
        alerts: state.alerts,
        subscriptions: state.subscriptions,
        stockColorMode: state.stockColorMode,
        useMockData: state.useMockData,
        recentSearches: state.recentSearches
      }), // Persist auth and user preferences
    }
```

**Key Features:**
- Stores user and token in global state
- Persists authentication state to localStorage
- Provides `login` and `logout` actions
- Syncs user preferences (watchlist, subscriptions, alerts) after login

---

### 6. `src/services/api/client.ts`
**Purpose**: Axios client configuration for API requests

**Base URL Configuration:**
```14:27:src/services/api/client.ts
// Get base URL from environment or use defaults
const getBaseURL = (): string => {
  const envUrl = import.meta.env.VITE_API_BASE_URL;
  if (envUrl) {
    return envUrl;
  }

  // Log warning in production if falling back to default
  if (import.meta.env.PROD) {
    console.warn('VITE_API_BASE_URL not set in production. Using default: https://api.tinboker.com');
  }

  // Always use production URL, avoiding local/staging unless specified
  return 'https://api.tinboker.com';
};
```

**Key Features:**
- Reads `VITE_API_BASE_URL` from environment
- Falls back to production URL if not set
- Configures timeout, headers, and interceptors
- Used by `authApi` to make authentication requests

---

## Setup & Configuration

### 1. Google Cloud Console Setup

1. **Go to Google Cloud Console**: [https://console.cloud.google.com/](https://console.cloud.google.com/)

2. **Create a New Project** (e.g., "TinBoker-Dev")

3. **Configure OAuth Consent Screen**:
   - Navigate to **APIs & Services > OAuth consent screen**
   - Select **External** (for testing) or **Internal** (if organization-only)
   - Fill in app name ("TinBoker"), support email, etc.
   - **Scopes**: Add `userinfo.email` and `userinfo.profile`
   - **Test Users**: Add your own email for testing

4. **Create OAuth Credentials**:
   - Navigate to **APIs & Services > Credentials**
   - Click **Create Credentials > OAuth client ID**
   - **Application type**: Web application
   - **Name**: "Web Client 1"
   - **Authorized JavaScript origins**:
     - `http://localhost:5173` (for local development)
     - `https://your-production-domain.com` (for production)
   - **Authorized redirect URIs**:
     - `http://localhost:5173` (for local development)
     - `https://your-production-domain.com` (for production)

5. **Copy Client ID**: Save the Client ID string (e.g., `123456-abcde.apps.googleusercontent.com`)

### 2. Local Development Setup

1. **Create `.env.local` file** in project root:
   ```bash
   VITE_GOOGLE_CLIENT_ID=your-google-client-id-here
   VITE_API_BASE_URL=http://localhost:8000
   ```

2. **Install dependencies** (if not already installed):
   ```bash
   npm install
   ```

3. **Start development server**:
   ```bash
   npm run dev
   ```

4. **Test login**: Click "登入" button in the header

### 3. Production Deployment (Vercel)

1. **Go to Vercel Dashboard** > Your Project > **Settings** > **Environment Variables**

2. **Add Environment Variables**:
   - `VITE_GOOGLE_CLIENT_ID`: Your Google Client ID
   - `VITE_API_BASE_URL`: Your production API URL (optional, has default)

3. **Select Environments**: Choose "Production" (and "Preview" if needed)

4. **Save and Redeploy**: 
   - Click "Save"
   - Go to **Deployments** tab
   - Click "Redeploy" on the latest deployment
   - Wait for deployment to complete

---

## Authentication Flow

### Production Flow

1. **User clicks "登入" button**
2. **Google OAuth popup opens** (handled by `@react-oauth/google`)
3. **User authenticates with Google**
4. **Google returns access token** (implicit flow)
5. **Frontend sends access token to backend** (`POST /api/auth/google`)
6. **Backend verifies token** and returns:
   - User data (id, name, email, avatar, preferences)
   - JWT session token
7. **Frontend stores user and token** in Zustand store
8. **User preferences synced** (watchlist, subscriptions, alerts)
9. **Authentication state persisted** to localStorage

### Development Flow

1. **User clicks "登入" button**
2. **Development mode detected** (`import.meta.env.DEV`)
3. **Dummy login bypasses Google OAuth**:
   - Creates dummy user: `dev@tinboker.local`
   - Generates dummy token: `dev-token-{timestamp}`
   - Sets empty preferences
4. **User logged in without Google authentication**

**Note**: This allows local development without Google Cloud Console setup.

---

## Development Mode

### Features

- **Automatic Bypass**: Google OAuth is bypassed in development mode
- **Dummy User**: Creates a test user automatically
- **No Backend Required**: Works without backend API running
- **Console Logging**: Detailed logs for debugging

### Dummy User Details

```typescript
{
  id: 'dev-user-123',
  name: 'Dev User',
  email: 'dev@tinboker.local',
  avatar: '',
  initials: 'DU'
}
```

### Disabling Development Bypass

To test actual Google OAuth in development:
1. Set `VITE_GOOGLE_CLIENT_ID` in `.env.local`
2. Modify `GoogleLoginButton.tsx` to remove the dev mode check (or set `import.meta.env.DEV = false`)

---

## Production Deployment

### Vercel Configuration

1. **Environment Variables**:
   - `VITE_GOOGLE_CLIENT_ID`: Required
   - `VITE_API_BASE_URL`: Optional (defaults to production URL)

2. **Build Settings**:
   - Framework: Vite
   - Build Command: `npm run build`
   - Output Directory: `dist`

3. **Redeployment**:
   - After adding environment variables, redeploy is required
   - Environment variables are injected at build time

### Error Handling

The app includes error handling for missing configuration:

- **Missing Client ID**: Logs warning, uses placeholder to prevent crash
- **Missing API URL**: Falls back to production URL
- **Login Failure**: Shows user-friendly alert in Chinese: "登入失敗，請稍後再試"

---

## Backend API Requirements

### Required Endpoint

**`POST /api/auth/google`**

**Request Body:**
```json
{
  "accessToken": "google-access-token-string"
}
```

**Response:**
```json
{
  "user": {
    "id": "user-uuid",
    "google_id": "google-sub-id",
    "email": "user@example.com",
    "name": "User Name",
    "avatar": "https://...",
    "email_verified": true,
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z",
    "watchlist": ["AAPL", "GOOGL"],
    "podcast_subscriptions": ["podcast-id-1"],
    "episode_bookmarks": ["episode-id-1"],
    "alerts": ["TSLA"],
    "tag_subscriptions": ["tag-1"]
  },
  "token": "jwt-session-token"
}
```

**Backend Implementation Requirements:**

1. **Verify Google Access Token**:
   - Use Google's token verification API or library
   - Verify token signature and expiration
   - Extract user information (sub, email, name, picture)

2. **User Management**:
   - Create user if doesn't exist
   - Update user if exists
   - Store Google ID for future lookups

3. **Session Management**:
   - Generate JWT token for session
   - Include user ID in JWT payload
   - Set appropriate expiration time

4. **Error Handling**:
   - Return 401 for invalid tokens
   - Return 500 for server errors
   - Include error details in response

### Additional Endpoints

**`GET /api/auth/me`** (Optional, for token refresh)
- **Headers**: `Authorization: Bearer {token}`
- **Response**: Same user object as above

**`POST /api/auth/logout`** (Optional, for server-side logout)
- **Headers**: `Authorization: Bearer {token}`
- **Response**: Success status

---

## Troubleshooting

### Common Issues

1. **"Google login will not work until VITE_GOOGLE_CLIENT_ID is set"**
   - **Solution**: Add `VITE_GOOGLE_CLIENT_ID` to `.env.local` (local) or Vercel environment variables (production)

2. **"登入失敗，請稍後再試" (Login failed)**
   - **Check**: Backend API is running and accessible
   - **Check**: `VITE_API_BASE_URL` is correct
   - **Check**: Backend `/api/auth/google` endpoint is implemented
   - **Check**: Google Client ID is correct and authorized origins match

3. **CORS Errors**
   - **Solution**: Ensure backend allows requests from frontend origin
   - **Check**: `VITE_API_BASE_URL` matches backend CORS configuration

4. **Token Verification Fails**
   - **Check**: Backend is using correct Google Client ID for verification
   - **Check**: Token hasn't expired
   - **Check**: Backend has internet access to verify tokens

### Debug Mode

Enable debug logging by checking browser console:
- Development mode: Automatic detailed logging
- Production mode: Check `[DEBUG] Environment check` logs in console

---

## File Structure Summary

```
src/
├── main.tsx                          # GoogleOAuthProvider initialization
├── components/
│   └── auth/
│       ├── GoogleLoginButton.tsx    # Main login component
│       └── LoginButton.tsx          # Wrapper component
├── services/
│   └── api/
│       ├── auth.ts                   # Authentication API service
│       └── client.ts                # Axios client configuration
└── store/
    └── useAppStore.ts                # Zustand store (auth state)

.env.local                            # Local environment variables
package.json                          # Dependencies (@react-oauth/google)
```

---

## Related Documentation

- [Google Login Setup Guide](./process/google-login-setup.md) - Step-by-step setup instructions
- [API Gaps](./api/api-gaps.md) - Backend API requirements
- [Backend API Frontend Comparison](./engineering/backend-api-frontend-comparison.md) - API integration details

---

## Version Information

- **@react-oauth/google**: `^0.12.2`
- **React**: `^19.1.1`
- **Zustand**: `^5.0.8`
- **Axios**: `^1.13.2`

---

*Last Updated: Based on current codebase state*
