import { createContext, useContext } from 'react';

/**
 * Transitional flag: true when a page is rendered inside <AppLayout>.
 * The legacy <Header>/<Footer> read this and render null so unmigrated pages
 * don't double up the chrome. Removed once every page is migrated and the
 * legacy Header/Footer are deleted (Phase 5).
 */
export const AppLayoutContext = createContext(false);

export function useWithinAppLayout(): boolean {
  return useContext(AppLayoutContext);
}
