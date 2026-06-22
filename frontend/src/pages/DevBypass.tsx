import { useEffect, useState } from 'react';
import { useSearchParams, Navigate } from 'react-router-dom';
import { useAppStore } from '@/store/useAppStore';
import { apiClient } from '@/services/api/client';

/**
 * Dev-only auth bypass for automated browser testing (Cursor browser MCP).
 * Navigating to /auth/dev-bypass?token=SECRET authenticates without Google OAuth.
 * Only works when backend ENVIRONMENT != production and DEV_BYPASS_TOKEN is set.
 */
export const DevBypass: React.FC = () => {
  const [params] = useSearchParams();
  const login = useAppStore((s) => s.login);
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    const token = params.get('token');
    if (!token) {
      setErrorMsg('Missing token parameter');
      setStatus('error');
      return;
    }
    apiClient
      .post('/api/auth/dev-token', { token })
      .then((res) => {
        const { user, token: jwt, refresh_token } = res.data;
        login(user, jwt, refresh_token);
        setStatus('success');
      })
      .catch((err) => {
        setErrorMsg(err.response?.data?.detail || err.message || 'Auth failed');
        setStatus('error');
      });
  }, [params, login]);

  if (status === 'success') return <Navigate to="/" replace />;

  return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      {status === 'loading' && (
        <p className="text-sm text-muted-foreground">Authenticating…</p>
      )}
      {status === 'error' && (
        <p className="text-sm text-destructive">Dev bypass failed: {errorMsg}</p>
      )}
    </div>
  );
};
