# How to Get and Set VITE_GOOGLE_CLIENT_ID

## Step 1: Get Google Client ID from Google Cloud Console

### 1.1 Go to Google Cloud Console

1. Visit: https://console.cloud.google.com/
2. Sign in with your Google account
3. Select your project (or create a new one)

### 1.2 Configure OAuth Consent Screen (First Time Only)

1. Navigate to **APIs & Services** > **OAuth consent screen**
2. Select **User Type**: **External** (for public apps)
3. Fill in:
   - **App name**: `TinBoker` (or your app name)
   - **User support email**: Your email
   - **Developer contact**: Your email
4. Click **Save and Continue**
5. **Scopes**: Add `.../auth/userinfo.email`, `.../auth/userinfo.profile`, `openid`
6. Click **Save and Continue** through all steps

### 1.3 Create OAuth 2.0 Client ID

1. Navigate to **APIs & Services** > **Credentials**
2. Click **+ CREATE CREDENTIALS** > **OAuth client ID**
3. Select **Application type**: **Web application**
4. Enter **Name**: `TinBoker Web Client`
5. **Authorized JavaScript origins** (add these):
   ```
   http://localhost:5173
   http://localhost:5175
   http://127.0.0.1:5173
   http://127.0.0.1:5175
   https://your-production-domain.com
   https://*.vercel.app
   ```
6. **Authorized redirect URIs** (add these):
   ```
   http://localhost:5173
   http://localhost:5175
   http://127.0.0.1:5173
   http://127.0.0.1:5175
   https://your-production-domain.com
   ```
7. Click **Create**
8. **IMPORTANT**: A dialog will appear showing your **Client ID**
   - It looks like: `123456789-abcdefghijklmnop.apps.googleusercontent.com`
   - **Copy this Client ID** - you'll need it for the frontend

### 1.4 Enable Required APIs

1. Navigate to **APIs & Services** > **Library**
2. Search for and enable:
   - **Google+ API** (may show as deprecated, but still needed)
   - **People API**

---

## Step 2: Set VITE_GOOGLE_CLIENT_ID in Frontend

### 2.1 Create `.env.local` File

1. Navigate to the frontend project directory:
   ```bash
   cd tinboker/frontend
   ```

2. Create a file named `.env.local` in the root directory:
   ```bash
   # On Linux/Mac
   touch .env.local
   
   # Or create it manually in your editor
   ```

### 2.2 Add Environment Variables

Open `.env.local` and add:

```env
# Google OAuth Client ID
# Get this from: Google Cloud Console > APIs & Services > Credentials
VITE_GOOGLE_CLIENT_ID=your-client-id-here.apps.googleusercontent.com

# Backend API URL
VITE_API_URL=http://localhost:3000/api
```

**Replace `your-client-id-here.apps.googleusercontent.com` with the actual Client ID you copied from Google Cloud Console.**

### 2.3 Example `.env.local` File

```env
VITE_GOOGLE_CLIENT_ID=123456789-abcdefghijklmnopqrstuvwxyz.apps.googleusercontent.com
VITE_API_URL=http://localhost:3000/api
```

### 2.4 Important Notes

- **File name**: Must be `.env.local` (not `.env`)
- **Location**: Must be in the root of `tinboker/frontend/` directory
- **Git**: `.env.local` should already be in `.gitignore` (don't commit it)
- **Restart**: After creating/updating `.env.local`, you **must restart** the dev server

### 2.5 Verify Environment Variables

1. **Restart your dev server**:
   ```bash
   # Stop the server (Ctrl+C)
   # Then restart
   npm run dev
   ```

2. **Check in browser console** (after server restarts):
   ```javascript
   // Open browser DevTools console
   console.log('Google Client ID:', import.meta.env.VITE_GOOGLE_CLIENT_ID);
   console.log('API URL:', import.meta.env.VITE_API_URL);
   ```

   You should see your Client ID printed (not `undefined`)

---

## Step 3: For Production (Vercel/Deployment)

When deploying to production (e.g., Vercel):

1. Go to your deployment platform's environment variables settings
2. Add:
   - `VITE_GOOGLE_CLIENT_ID` = `your-client-id.apps.googleusercontent.com`
   - `VITE_API_URL` = `https://your-backend-domain.com/api`

3. **Important**: After adding environment variables, you must **redeploy** your application for them to take effect.

---

## Troubleshooting

### Problem: `VITE_GOOGLE_CLIENT_ID` is `undefined`

**Solutions:**
1. Check file name is exactly `.env.local` (not `.env` or `.env.local.txt`)
2. Check file is in the root of `tinboker/frontend/` directory
3. Restart the dev server after creating/updating the file
4. Check for typos in variable name (must be `VITE_GOOGLE_CLIENT_ID`)

### Problem: "Invalid client" error

**Solutions:**
1. Verify Client ID matches exactly (no extra spaces)
2. Check that your frontend URL is in "Authorized JavaScript origins" in Google Cloud Console
3. Ensure you're using the correct Client ID (not Client Secret)

### Problem: CORS errors

**Solutions:**
1. Add your frontend URL to "Authorized JavaScript origins" in Google Cloud Console
2. Make sure the URL matches exactly (including `http://` vs `https://`)

---

## Quick Reference

**Where to get Client ID:**
- Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client IDs

**Where to set it:**
- `tinboker/frontend/.env.local` file

**Format:**
```env
VITE_GOOGLE_CLIENT_ID=123456789-abcdefghijklmnop.apps.googleusercontent.com
```

**After setting:**
- Restart dev server: `npm run dev`

