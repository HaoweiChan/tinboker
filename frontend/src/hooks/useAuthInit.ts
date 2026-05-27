import { useEffect, useState, useRef } from 'react';
import { AxiosError } from 'axios';
import { useAppStore } from '@/store/useAppStore';
import { authApi } from '@/services/api/auth';

const DEV_TOKEN_PREFIX = 'dev-token-';
const MAX_RETRIES = 2;
const RETRY_DELAY_MS = 1500;

function isAuthError(error: unknown): boolean {
  if (error instanceof AxiosError && error.response) {
    return error.response.status === 401 || error.response.status === 403;
  }
  const msg = error instanceof Error ? error.message : String(error);
  return msg.includes('401') || msg.includes('403') || msg.includes('Authentication failed');
}

function isNetworkError(error: unknown): boolean {
  if (error instanceof AxiosError) {
    return !error.response && !!error.request;
  }
  const msg = error instanceof Error ? error.message : String(error);
  return msg.includes('Network Error') || msg.includes('timeout') || msg.includes('ECONNREFUSED');
}

/**
 * Hook to validate stored auth token on app initialization
 * and sync user preferences from the backend.
 *
 * Only logs out on definitive auth failures (401/403).
 * Retries on transient network errors to avoid spurious logouts.
 */
export function useAuthInit() {
  const [isValidating, setIsValidating] = useState(false);
  const [isInitialized, setIsInitialized] = useState(false);
  const hasValidated = useRef(false);

  const token = useAppStore((state) => state.token);
  const login = useAppStore((state) => state.login);
  const logout = useAppStore((state) => state.logout);
  const setAuthReady = useAppStore((state) => state.setAuthReady);

  useEffect(() => {
    if (hasValidated.current) return;
    hasValidated.current = true;

    const validateToken = async () => {
      if (!token) {
        setAuthReady(true);
        setIsInitialized(true);
        return;
      }

      // Dev tokens bypass backend validation entirely
      if (import.meta.env.DEV && token.startsWith(DEV_TOKEN_PREFIX)) {
        setAuthReady(true);
        setIsInitialized(true);
        return;
      }

      setIsValidating(true);
      let lastError: unknown;

      for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
        try {
          const user = await authApi.getCurrentUser(token);

          login(
            {
              id: user.id,
              name: user.name,
              email: user.email,
              avatar: user.avatar || '',
              initials: user.name
                .split(' ')
                .map((n: string) => n[0])
                .join('')
                .toUpperCase()
                .slice(0, 2),
            },
            token,
          );

          useAppStore.setState({
            watchlist: user.watchlist || [],
            subscriptions: user.podcast_subscriptions || [],
            tagSubscriptions: user.tag_subscriptions || [],
            alerts: user.alerts || [],
          });

          setIsValidating(false);
          setAuthReady(true);
          setIsInitialized(true);
          return;
        } catch (error) {
          lastError = error;

          if (isAuthError(error)) {
            if (import.meta.env.DEV) {
              console.warn('[useAuthInit] Token rejected by server (401/403), logging out');
            }
            logout();
            setIsValidating(false);
            setAuthReady(true);
            setIsInitialized(true);
            return;
          }

          // Retry on network errors, but give up after MAX_RETRIES
          if (isNetworkError(error) && attempt < MAX_RETRIES) {
            if (import.meta.env.DEV) {
              console.info(`[useAuthInit] Network error, retrying (${attempt + 1}/${MAX_RETRIES})...`);
            }
            await new Promise((r) => setTimeout(r, RETRY_DELAY_MS));
            continue;
          }

          break;
        }
      }

      // After retries exhausted: keep user logged in with stale data
      // rather than logging them out due to a transient network issue
      if (import.meta.env.DEV) {
        console.warn('[useAuthInit] Token validation failed after retries, keeping session:', lastError);
      }
      setIsValidating(false);
      setAuthReady(true);
      setIsInitialized(true);
    };

    validateToken();
  }, []);

  return { isValidating, isInitialized };
}
