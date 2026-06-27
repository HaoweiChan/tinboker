import { useCallback } from 'react';
import { useAppStore } from '@/store/useAppStore';

/**
 * Thrown by `ensure()` to abort an in-flight async action when login is
 * required, so the caller can tell "needs login" apart from a real failure
 * (e.g. keep the user's typed comment instead of clearing it).
 */
export class AuthRequiredError extends Error {
  constructor() {
    super('AUTH_REQUIRED');
    this.name = 'AuthRequiredError';
  }
}

/**
 * Gates personalized / write actions on now-public pages (episode, stock,
 * article). Two shapes for two control-flow needs:
 *  - `guard(fn)` — fire-and-forget (buttons): runs `fn` if logged in, else
 *    opens the global login prompt and skips `fn` (never throws).
 *  - `ensure()`  — async submits: returns if logged in, else opens the prompt
 *    and throws `AuthRequiredError` so the caller aborts cleanly.
 * Gates read fresh store state; the hook subscribes to `user` so consumers
 * re-render on auth change.
 */
export function useRequireAuth() {
  useAppStore((s) => s.user);

  const guard = useCallback(<T>(fn: () => T): T | void => {
    if (useAppStore.getState().user) return fn();
    useAppStore.getState().openLoginPrompt();
  }, []);

  const ensure = useCallback((): void => {
    if (useAppStore.getState().user) return;
    useAppStore.getState().openLoginPrompt();
    throw new AuthRequiredError();
  }, []);

  return { guard, ensure };
}
