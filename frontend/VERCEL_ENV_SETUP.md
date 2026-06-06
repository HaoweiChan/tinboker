# Vercel Environment Variables Setup

## Issue: "Missing required parameter: client_id"

This error occurs when `VITE_GOOGLE_CLIENT_ID` is not set in Vercel's environment variables.

## Solution: Set Environment Variables in Vercel

### Step 1: Get Your Google Client ID

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to **APIs & Services** > **Credentials**
3. Find your OAuth 2.0 Client ID (it looks like: `123456789-abc...xyz.apps.googleusercontent.com`)
4. Copy the entire Client ID

### Step 2: Add Environment Variable in Vercel

1. Go to your [Vercel Dashboard](https://vercel.com/dashboard)
2. Select your project (tinboker/frontend)
3. Go to **Settings** > **Environment Variables**
4. Click **Add New** or **Add Environment Variable**
5. Add the following:

   **Name:**
   ```
   VITE_GOOGLE_CLIENT_ID
   ```

   **Value:**
   ```
   your-client-id-here.apps.googleusercontent.com
   ```
   (Replace with your actual Client ID from Google Cloud Console)

   **Environment:**
   - Select **Production**, **Preview**, and **Development** (or at least **Production**)

6. Click **Save**

### Step 3: Add Backend API URL (if not already set)

Also add:

**Name:**
```
VITE_API_URL
```

**Value:**
```
https://api.tinboker.com/api
```
(or your backend URL)

### Step 4: Redeploy

**IMPORTANT**: After adding environment variables, you **MUST redeploy** for them to take effect:

1. Go to **Deployments** tab in Vercel
2. Click the **three dots** (⋯) on the latest deployment
3. Click **Redeploy**
4. Or push a new commit to trigger a new deployment

### Step 5: Verify

After redeployment, check:
1. Open your Vercel app URL
2. Open browser DevTools Console (F12)
3. You should NOT see the error about missing `client_id`
4. Try logging in with Google - it should work

## Required Environment Variables for Vercel

| Variable Name | Description | Example |
|--------------|-------------|---------|
| `VITE_GOOGLE_CLIENT_ID` | Google OAuth Client ID | `123456789-abc...xyz.apps.googleusercontent.com` |
| `VITE_API_URL` | Backend API URL | `https://api.tinboker.com/api` |

## Troubleshooting

### Still seeing "Missing required parameter: client_id"?

1. **Check variable name**: Must be exactly `VITE_GOOGLE_CLIENT_ID` (case-sensitive)
2. **Check value**: No extra spaces, quotes, or line breaks
3. **Redeploy**: Environment variables only apply to NEW deployments
4. **Check environment**: Make sure you selected the correct environment (Production/Preview)

### How to verify environment variables are set:

1. In Vercel Dashboard > Settings > Environment Variables
2. You should see `VITE_GOOGLE_CLIENT_ID` listed
3. The value should show (masked) - click to view

### For Google Cloud Console:

Make sure your Vercel domain is added to **Authorized JavaScript origins**:
- Go to Google Cloud Console > APIs & Services > Credentials
- Edit your OAuth 2.0 Client ID
- Add to **Authorized JavaScript origins**:
  ```
  https://your-app.vercel.app
  https://*.vercel.app
  ```

## Quick Checklist

- [ ] Got Google Client ID from Google Cloud Console
- [ ] Added `VITE_GOOGLE_CLIENT_ID` in Vercel Environment Variables
- [ ] Added `VITE_API_URL` in Vercel Environment Variables (if needed)
- [ ] Selected correct environments (Production/Preview)
- [ ] Redeployed the application
- [ ] Verified Google login works


