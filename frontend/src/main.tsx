import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { HelmetProvider } from 'react-helmet-async'
import { GoogleOAuthProvider } from '@react-oauth/google'
import './index.css'
import App from './App.tsx'
import { PWAUpdatePrompt } from './components/common/PWAUpdatePrompt'
import { PWAInstallBanner } from './components/common/PWAInstallPrompt'
import { initializeTheme } from './utils/themeInit'

// Initialize theme before rendering
initializeTheme()

// Get Google Client ID from environment
// If missing, use a placeholder to prevent app crash, though login will fail
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || 'mock_client_id_to_prevent_crash'

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
    'Create .env.local file in frontend/ with:\n' +
    'VITE_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com';

  console.error(errorMsg);

  // Show user-friendly error in production
  if (import.meta.env.PROD) {
    // Don't block the app, but show a warning
    console.warn('Google login will not work until VITE_GOOGLE_CLIENT_ID is set and the app is redeployed.');
  }
}

// Conditionally wrap in StrictMode only in production
// StrictMode causes double-mounting in dev which leads to duplicate API calls
const AppWrapper = import.meta.env.PROD ? (
  <StrictMode>
    <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>
      <HelmetProvider>
        <App />
        <PWAUpdatePrompt />
        <PWAInstallBanner />
      </HelmetProvider>
    </GoogleOAuthProvider>
  </StrictMode>
) : (
  <GoogleOAuthProvider clientId={GOOGLE_CLIENT_ID}>
    <HelmetProvider>
      <App />
      <PWAUpdatePrompt />
      <PWAInstallBanner />
    </HelmetProvider>
  </GoogleOAuthProvider>
);

createRoot(document.getElementById('root')!).render(AppWrapper)
