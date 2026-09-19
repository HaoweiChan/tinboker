import { useCallback, useEffect, useState } from 'react';
import { useSearchParams, Navigate } from 'react-router-dom';
import { useAppStore } from '@/store/useAppStore';
import { apiClient } from '@/services/api/client';

type Role = 'viewer' | 'admin';

/**
 * Dev-only auth bypass for automated browser testing (browser MCP, Playwright).
 * Only works when backend ENVIRONMENT != production and DEV_BYPASS_TOKEN is set.
 *
 * Two ways in:
 *  - `/auth/dev-bypass` with no token: a form. The secret goes in a POST body and never
 *    touches the URL, the history, or a log line — the way a person should do it.
 *  - `/auth/dev-bypass?token=SECRET[&role=viewer|admin]`: for scripted runners that can
 *    only navigate. Defaults to `admin`, as it always has.
 *
 * `viewer` signs in as the read-only QA user: past the dev/staging gate, not an admin.
 * That is the session to leave in an AI agent's browser.
 */
export const DevBypass: React.FC = () => {
  const [params] = useSearchParams();
  const login = useAppStore((s) => s.login);
  const urlToken = params.get('token');
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>(urlToken ? 'loading' : 'idle');
  const [errorMsg, setErrorMsg] = useState('');
  const [secret, setSecret] = useState('');
  const [role, setRole] = useState<Role>('viewer');

  const authenticate = useCallback(
    (token: string, asRole: Role) => {
      setStatus('loading');
      apiClient
        .post('/api/auth/dev-token', { token, role: asRole })
        .then((res) => {
          const { user, token: jwt, refresh_token } = res.data;
          login(user, jwt, refresh_token);
          setStatus('success');
        })
        .catch((err) => {
          setErrorMsg(err.response?.data?.detail || err.message || 'Auth failed');
          setStatus('error');
        });
    },
    [login],
  );

  useEffect(() => {
    if (!urlToken) return;
    authenticate(urlToken, params.get('role') === 'viewer' ? 'viewer' : 'admin');
  }, [urlToken, params, authenticate]);

  if (status === 'success') return <Navigate to="/" replace />;

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-6">
      {status === 'loading' && <p className="text-sm text-muted-foreground">Authenticating…</p>}
      {status !== 'loading' && (
        <form
          className="w-full max-w-xs space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (secret.trim()) authenticate(secret.trim(), role);
          }}
        >
          <p className="text-sm font-semibold text-foreground">Dev bypass</p>
          <input
            type="password"
            autoComplete="off"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            placeholder="DEV_BYPASS_TOKEN"
            aria-label="DEV_BYPASS_TOKEN"
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
          />
          {/* What was pasted, never what it is: a wrong clipboard (a whole paragraph, a
              stale value) is the usual failure, and the length gives it away at once. */}
          {secret && (
            <p className="text-xs text-muted-foreground">
              {secret.trim().length} characters{/\s/.test(secret.trim()) ? ' — contains whitespace, probably not the token' : ''}
            </p>
          )}
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as Role)}
            aria-label="Role"
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
          >
            <option value="viewer">viewer — read-only QA session (not an admin)</option>
            <option value="admin">admin — for QA of the admin pages</option>
          </select>
          <button
            type="submit"
            disabled={!secret.trim()}
            className="w-full rounded-md bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50"
          >
            Sign in
          </button>
          {status === 'error' && <p className="text-sm text-destructive">Dev bypass failed: {errorMsg}</p>}
        </form>
      )}
    </div>
  );
};
