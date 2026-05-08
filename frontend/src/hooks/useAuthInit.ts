import { useEffect, useState, useRef } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { authApi } from '@/services/api/auth';

/**
 * Hook to validate stored auth token on app initialization
 * and sync user preferences from the backend.
 *
 * Should be called once at the root of the app (App.tsx).
 */
export function useAuthInit() {
  const [isValidating, setIsValidating] = useState(false);
  const [isInitialized, setIsInitialized] = useState(false);
  const hasValidated = useRef(false);

  const token = useAppStore((state) => state.token);
  const login = useAppStore((state) => state.login);
  const logout = useAppStore((state) => state.logout);

  useEffect(() => {
    // Only run once on mount
    if (hasValidated.current) return;
    hasValidated.current = true;

    const validateToken = async () => {
      // No token stored - user is logged out
      if (!token) {
        setIsInitialized(true);
        return;
      }

      setIsValidating(true);
      try {
        // Validate token and get user info from backend
        const user = await authApi.getCurrentUser(token);

        // Sync user data and preferences to store
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
          token // Keep the same token since it's still valid
        );

        // Sync user preferences
        useAppStore.setState({
          watchlist: user.watchlist || [],
          subscriptions: user.podcast_subscriptions || [],
          tagSubscriptions: user.tag_subscriptions || [],
          alerts: user.alerts || [],
        });

      } catch (error) {
        // Token is invalid or expired - clear auth state
        console.warn('[useAuthInit] Token validation failed, logging out:', error);
        logout();
      } finally {
        setIsValidating(false);
        setIsInitialized(true);
      }
    };

    validateToken();
  }, []); // Empty deps - only run on mount

  return { isValidating, isInitialized };
}
