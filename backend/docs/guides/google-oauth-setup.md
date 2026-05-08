# Google Login Setup Guide

**Date:** 2025-12-22  
**Project:** TinBoker (Backend + Frontend)  
**Purpose:** Step-by-step setup instructions for Google OAuth authentication

---

## Table of Contents

1. [Google Cloud Console Setup](#google-cloud-console-setup)
2. [Backend Environment Configuration](#backend-environment-configuration)
3. [Frontend Environment Configuration](#frontend-environment-configuration)
4. [Firebase Service Account Setup](#firebase-service-account-setup)
5. [Verification Checklist](#verification-checklist)

---

## Google Cloud Console Setup

### Step 1: Create or Select Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Click on the project dropdown at the top
3. Either:
   - **Select existing project**: Choose your project
   - **Create new project**: Click "New Project" → Enter name (e.g., "TinBoker") → Click "Create"

### Step 2: Configure OAuth Consent Screen

1. Navigate to **APIs & Services** > **OAuth consent screen**
2. Select **User Type**:
   - **External** (for public apps) - Recommended for production
   - **Internal** (only for Google Workspace organizations)
3. Click **Create**
4. Fill in **App information**:
   - **App name**: `TinBoker` (or your app name)
   - **User support email**: Your email address
   - **App logo**: (Optional) Upload your app logo
   - **App domain**: (Optional) Your domain
   - **Developer contact information**: Your email address
5. Click **Save and Continue**
6. **Scopes** (Step 2):
   - Click **Add or Remove Scopes**
   - Select:
     - `.../auth/userinfo.email`
     - `.../auth/userinfo.profile`
     - `openid`
   - Click **Update** → **Save and Continue**
7. **Test users** (Step 3 - for External apps):
   - Add test user emails if you want to test before publishing
   - Click **Save and Continue**
8. **Summary** (Step 4):
   - Review settings
   - Click **Back to Dashboard**

### Step 3: Create OAuth 2.0 Client ID

1. Navigate to **APIs & Services** > **Credentials**
2. Click **+ CREATE CREDENTIALS** > **OAuth client ID**
3. If prompted, complete OAuth consent screen setup first (see Step 2)
4. Select **Application type**: **Web application**
5. Enter **Name**: `TinBoker Web Client`
6. **Authorized JavaScript origins**:
   ```
   http://localhost:5173
   http://localhost:5175
   http://127.0.0.1:5173
   http://127.0.0.1:5175
   https://your-production-domain.com
   https://*.vercel.app
   ```
   > **Note**: Add all domains where your frontend will run. For Vercel, you can use `https://*.vercel.app` to allow all preview deployments.

7. **Authorized redirect URIs**:
   ```
   http://localhost:5173
   http://localhost:5175
   http://127.0.0.1:5173
   http://127.0.0.1:5175
   https://your-production-domain.com
   ```
   > **Note**: These should match your frontend URLs. The redirect URI is where Google sends the user after authentication.

8. Click **Create**
9. **IMPORTANT**: Copy the **Client ID** and **Client Secret**
   - You'll need the **Client ID** for frontend
   - You'll need the **Client Secret** for backend (if using server-side flow)
   - For client-side OAuth with ID tokens, you typically only need the Client ID

10. Click **OK**

### Step 4: Enable Required APIs

1. Navigate to **APIs & Services** > **Library**
2. Search for and enable:
   - **Google+ API** (may show as deprecated, but still needed)
   - **People API** (for user profile information)

---

## Firebase Service Account Setup

### Step 1: Create Firebase Project

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Click **Add project** (or select existing project)
3. Enter **Project name**: `TinBoker` (or match your Google Cloud project)
4. Click **Continue**
5. **Google Analytics** (Optional):
   - Enable or disable Google Analytics
   - Click **Continue**
6. Click **Create project**
7. Wait for project creation to complete
8. Click **Continue**

### Step 2: Generate Service Account Key

1. In Firebase Console, click the **gear icon** (⚙️) > **Project settings**
2. Go to **Service accounts** tab
3. Click **Generate new private key**
4. A warning dialog will appear:
   - Click **Generate key**
   - A JSON file will be downloaded (e.g., `tinboker-firebase-adminsdk-xxxxx.json`)
5. **IMPORTANT**: 
   - Save this file securely
   - **Never commit this file to git**
   - This file contains sensitive credentials

### Step 3: Note Firebase Project ID

1. In Firebase Console, go to **Project settings** (gear icon)
2. Under **General** tab, find **Project ID**
3. Copy the Project ID (e.g., `tinboker-12345`)
4. You'll need this for backend configuration

---

## Backend Environment Configuration

### Step 1: Create/Update `.env` File

Create or update `.env` file in `tinboker-platform/backend/` directory:

```env
# ============================================
# Google OAuth Configuration
# ============================================
# Get these from: Google Cloud Console > APIs & Services > Credentials
GOOGLE_CLIENT_ID=your-client-id-here.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret-here

# ============================================
# Firebase Admin SDK Configuration
# ============================================
# Option 1: Path to service account JSON file (for local development)
GCP_CREDENTIALS_PATH=/absolute/path/to/your/firebase-service-account-key.json

# Option 2: Service account JSON as environment variable (for production)
# Uncomment and paste the entire JSON content (single line or escaped)
# GCP_CREDENTIALS_JSON={"type":"service_account","project_id":"your-project-id",...}

# Firebase Project ID (get from Firebase Console > Project Settings)
FIREBASE_PROJECT_ID=your-firebase-project-id

# ============================================
# JWT Token Configuration
# ============================================
# Generate a secure random key (minimum 32 characters)
# Use: python -c "import secrets; print(secrets.token_urlsafe(32))"
JWT_SECRET_KEY=your-super-secret-jwt-key-minimum-32-characters-long
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

# ============================================
# Existing Backend Configuration
# ============================================
# (Keep your existing settings)
HOST=0.0.0.0
PORT=3000
ENVIRONMENT=development

# CORS - Add your frontend URLs
CORS_ORIGINS=http://localhost:5173,http://localhost:5175,https://your-production-domain.com

# Database (keep existing)
DATABASE_PATH=data/tinboker.db
USE_POSTGRES=false

# Redis (keep existing if you have it)
# REDIS_URL=redis://localhost:6379/0
```

### Step 2: Generate JWT Secret Key

Run this command to generate a secure JWT secret key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copy the output and paste it as `JWT_SECRET_KEY` in your `.env` file.

### Step 3: Set Firebase Credentials Path

**For Local Development:**

1. Copy your Firebase service account JSON file to a secure location:
   ```bash
   # Example: Save to credentials folder
   mkdir -p credentials
   cp ~/Downloads/tinboker-firebase-adminsdk-xxxxx.json credentials/firebase-service-account.json
   ```

2. Update `.env` with absolute path:
   ```env
   GCP_CREDENTIALS_PATH=/home/lewis/1project/tinboker-platform/backend/credentials/firebase-service-account.json
   ```

**For Production (Render.com, etc.):**

1. Use environment variable instead of file path:
   ```env
   # Read the JSON file content
   cat credentials/firebase-service-account.json
   
   # Copy the entire JSON (it's a single line)
   # Paste it as GCP_CREDENTIALS_JSON in your production environment variables
   ```

2. In your production platform (e.g., Render.com):
   - Go to Environment Variables
   - Add: `GCP_CREDENTIALS_JSON` = `{"type":"service_account",...}` (paste entire JSON)
   - Add: `FIREBASE_PROJECT_ID` = `your-project-id`

### Step 4: Verify Backend Configuration

Check that all required variables are set:

```bash
# In tinboker-platform/backend directory
python -c "
import os
from dotenv import load_dotenv
load_dotenv()

required_vars = [
    'GOOGLE_CLIENT_ID',
    'FIREBASE_PROJECT_ID',
    'JWT_SECRET_KEY',
]

missing = []
for var in required_vars:
    if not os.getenv(var):
        missing.append(var)
    else:
        print(f'✅ {var} is set')

if missing:
    print(f'\n❌ Missing variables: {', '.join(missing)}')
else:
    print('\n✅ All required variables are set!')
    
# Check credentials path or JSON
if os.getenv('GCP_CREDENTIALS_PATH'):
    path = os.getenv('GCP_CREDENTIALS_PATH')
    if os.path.exists(path):
        print(f'✅ Firebase credentials file exists: {path}')
    else:
        print(f'❌ Firebase credentials file not found: {path}')
elif os.getenv('GCP_CREDENTIALS_JSON'):
    print('✅ Firebase credentials JSON is set (environment variable)')
else:
    print('❌ Firebase credentials not configured (need GCP_CREDENTIALS_PATH or GCP_CREDENTIALS_JSON)')
"
```

---

## Frontend Environment Configuration

### Step 1: Create/Update `.env.local` File

Create or update `.env.local` file in `tinboker-platform/frontend/` directory:

```env
# ============================================
# Google OAuth Client ID
# ============================================
# Get this from: Google Cloud Console > APIs & Services > Credentials
# Use the Client ID (not the Client Secret - that's for backend only)
VITE_GOOGLE_CLIENT_ID=your-client-id-here.apps.googleusercontent.com

# ============================================
# Backend API URL
# ============================================
# Local development
VITE_API_URL=http://localhost:3000/api

# Production (uncomment and update when deploying)
# VITE_API_URL=https://your-backend-domain.com/api
```

> **Note**: 
> - Use `.env.local` for local development (this file is gitignored)
> - For production, set these as environment variables in your deployment platform (Vercel, etc.)

### Step 2: Verify Frontend Configuration

Check that the environment variable is loaded:

```bash
# In tinboker-platform/frontend directory
# Check if .env.local exists
if [ -f .env.local ]; then
    echo "✅ .env.local file exists"
    grep "VITE_GOOGLE_CLIENT_ID" .env.local && echo "✅ VITE_GOOGLE_CLIENT_ID is set"
    grep "VITE_API_URL" .env.local && echo "✅ VITE_API_URL is set"
else
    echo "❌ .env.local file not found"
fi
```

### Step 3: Restart Development Server

After updating environment variables, restart your frontend dev server:

```bash
# Stop the server (Ctrl+C)
# Then restart
npm run dev
```

> **Important**: Environment variables starting with `VITE_` are only available at build time. You must restart the dev server after changing them.

---

## Production Deployment Configuration

### Render.com (Backend)

1. Go to your Render.com dashboard
2. Select your backend service
3. Go to **Environment** tab
4. Add the following environment variables:

```
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
FIREBASE_PROJECT_ID=your-firebase-project-id
GCP_CREDENTIALS_JSON={"type":"service_account","project_id":"...","private_key_id":"...","private_key":"...","client_email":"...","client_id":"...","auth_uri":"...","token_uri":"...","auth_provider_x509_cert_url":"...","client_x509_cert_url":"..."}
JWT_SECRET_KEY=your-jwt-secret-key
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24
CORS_ORIGINS=https://your-frontend-domain.com,https://*.vercel.app
```

> **Note**: For `GCP_CREDENTIALS_JSON`, paste the entire JSON content as a single line (or use Render's multi-line environment variable support if available).

### Vercel (Frontend)

1. Go to your Vercel project dashboard
2. Go to **Settings** > **Environment Variables**
3. Add:

```
VITE_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
VITE_API_URL=https://your-backend-domain.com/api
```

4. **Important**: After adding environment variables:
   - Go to **Deployments**
   - Click **...** on the latest deployment
   - Click **Redeploy** (environment variables require a new deployment)

---

## Verification Checklist

Use this checklist to verify your setup is complete:

### Google Cloud Console
- [ ] OAuth consent screen configured
- [ ] OAuth 2.0 Client ID created
- [ ] Client ID copied
- [ ] Client Secret copied (if needed)
- [ ] Authorized JavaScript origins configured
- [ ] Authorized redirect URIs configured
- [ ] Required APIs enabled (Google+ API, People API)

### Firebase Console
- [ ] Firebase project created
- [ ] Service account key downloaded
- [ ] Project ID noted
- [ ] Service account JSON file saved securely

### Backend Configuration
- [ ] `.env` file created/updated
- [ ] `GOOGLE_CLIENT_ID` set
- [ ] `GOOGLE_CLIENT_SECRET` set (if needed)
- [ ] `FIREBASE_PROJECT_ID` set
- [ ] `GCP_CREDENTIALS_PATH` or `GCP_CREDENTIALS_JSON` configured
- [ ] `JWT_SECRET_KEY` generated and set (32+ characters)
- [ ] `JWT_ALGORITHM` set to `HS256`
- [ ] `JWT_EXPIRATION_HOURS` set
- [ ] `CORS_ORIGINS` includes frontend URLs
- [ ] Firebase credentials file exists (if using path)
- [ ] Backend can start without errors

### Frontend Configuration
- [ ] `.env.local` file created/updated
- [ ] `VITE_GOOGLE_CLIENT_ID` set
- [ ] `VITE_API_URL` set
- [ ] Development server restarted after changes
- [ ] Environment variables accessible in code

### Production (if applicable)
- [ ] Backend environment variables set in deployment platform
- [ ] Frontend environment variables set in deployment platform
- [ ] Production URLs added to Google OAuth authorized origins
- [ ] Production URLs added to Google OAuth redirect URIs
- [ ] CORS configured for production domains
- [ ] Application redeployed after environment variable changes

### Security
- [ ] `.env` file added to `.gitignore`
- [ ] `.env.local` file added to `.gitignore`
- [ ] Firebase service account JSON not committed to git
- [ ] JWT secret key is strong and random
- [ ] Production secrets stored securely (not in code)

---

## Quick Reference: Environment Variables

### Backend (`.env`)

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `GOOGLE_CLIENT_ID` | ✅ Yes | OAuth Client ID from Google Cloud | `123456.apps.googleusercontent.com` |
| `GOOGLE_CLIENT_SECRET` | ⚠️ Optional | OAuth Client Secret | `GOCSPX-xxxxx` |
| `FIREBASE_PROJECT_ID` | ✅ Yes | Firebase project ID | `tinboker-12345` |
| `GCP_CREDENTIALS_PATH` | ✅* | Path to service account JSON | `/path/to/key.json` |
| `GCP_CREDENTIALS_JSON` | ✅* | Service account JSON as env var | `{"type":"service_account",...}` |
| `JWT_SECRET_KEY` | ✅ Yes | Secret for JWT tokens | `random-32-char-string` |
| `JWT_ALGORITHM` | ✅ Yes | JWT algorithm | `HS256` |
| `JWT_EXPIRATION_HOURS` | ✅ Yes | Token expiration time | `24` |

*Either `GCP_CREDENTIALS_PATH` or `GCP_CREDENTIALS_JSON` is required

### Frontend (`.env.local`)

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `VITE_GOOGLE_CLIENT_ID` | ✅ Yes | OAuth Client ID from Google Cloud | `123456.apps.googleusercontent.com` |
| `VITE_API_URL` | ✅ Yes | Backend API base URL | `http://localhost:3000/api` |

---

## Troubleshooting Setup Issues

### Issue: "Invalid client" error in frontend

**Solution:**
1. Verify `VITE_GOOGLE_CLIENT_ID` matches the Client ID in Google Cloud Console
2. Check that your frontend URL is in "Authorized JavaScript origins"
3. Restart the frontend dev server after changing `.env.local`

### Issue: Firebase Admin SDK initialization fails

**Solution:**
1. Verify `GCP_CREDENTIALS_PATH` points to a valid file, OR
2. Verify `GCP_CREDENTIALS_JSON` contains valid JSON
3. Check that `FIREBASE_PROJECT_ID` matches your Firebase project
4. Verify the service account JSON file is not corrupted

### Issue: CORS errors

**Solution:**
1. Add your frontend URL to backend `CORS_ORIGINS` in `.env`
2. Verify the URL format matches exactly (including `http://` vs `https://`)
3. Restart backend server after changing `.env`

### Issue: Environment variables not loading

**Solution:**
1. **Backend**: Ensure `.env` file is in the project root
2. **Frontend**: Ensure `.env.local` file is in the project root
3. **Frontend**: Variables must start with `VITE_` to be accessible
4. Restart the development server after changes

### Issue: JWT token errors

**Solution:**
1. Verify `JWT_SECRET_KEY` is set and is at least 32 characters
2. Check `JWT_ALGORITHM` is set to `HS256`
3. Ensure the same secret is used for token creation and verification

---

## Next Steps

After completing this setup:

1. ✅ Verify all checklist items are complete
2. 📖 Read the [Implementation Guide](./google_login_implementation_guide.md) for code implementation
3. 🧪 Test the authentication flow
4. 🚀 Deploy to production

---

**Last Updated:** 2025-12-22  
**Related Documents:**
- [Google Login Implementation Guide](./google_login_implementation_guide.md) - Code implementation details

