/** Podcast 觀點 newer than this are members-only; everything older is free to
 *  everyone, humans and crawlers alike. */
export const INSIGHT_PAYWALL_DAYS = 7;

const DAY_MS = 86_400_000;

/**
 * Is this mention inside the paywalled window?
 *
 * The cutoff is the mention's own launch time, so a page's split is stable no
 * matter who is looking. An unparseable/absent timestamp counts as OLD — an
 * insight we can't date is one we can't justify charging for, and treating it as
 * fresh would silently hide it from crawlers too.
 */
export function isPaywalledInsight(launchTime: string | null | undefined, now: number = Date.now()): boolean {
  const t = launchTime ? Date.parse(launchTime) : NaN;
  if (!Number.isFinite(t)) return false;
  return now - t < INSIGHT_PAYWALL_DAYS * DAY_MS;
}

/**
 * Split a mention list into what a non-member may read and what is gated.
 *
 * Callers must render only `free` for non-members — the gated rows never reach the
 * DOM, so this is a real gate, not a blur. What the crawler body serves has to go
 * through the same split, or the page cloaks.
 */
export function splitByPaywall<T extends { podcast_launch_time?: string | null }>(
  insights: readonly T[],
  now: number = Date.now(),
): { free: T[]; gated: T[] } {
  const free: T[] = [];
  const gated: T[] = [];
  for (const i of insights) (isPaywalledInsight(i.podcast_launch_time, now) ? gated : free).push(i);
  return { free, gated };
}
