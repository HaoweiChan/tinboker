/**
 * Umbrella exposures the backend refuses to serve as pages (UMBRELLA_EXPOSURE_IDS in
 * backend/src/services/podcast.py): 半導體 appears in most episodes, so a page for it
 * would be "all episodes". Render these as plain text, never as a /sector link.
 */
export const UMBRELLA_SECTOR_IDS: ReadonlySet<string> = new Set(['sector_semiconductor']);

export const isUmbrellaSector = (exposureId: string | null | undefined): boolean =>
  !!exposureId && UMBRELLA_SECTOR_IDS.has(exposureId);
