/**
 * Subscription funnel config (issue #425).
 *
 * TinBoker runs a hybrid model: a free public web edition here, and the paid
 * full edition on Substack. The paid destination is configured once via
 * `VITE_SUBSTACK_URL`; individual articles may override it with their own
 * `subscribe_url` (e.g. a topic-specific paid series).
 */

export const DEFAULT_SUBSCRIBE_URL: string =
  (import.meta.env.VITE_SUBSTACK_URL as string) || 'https://tinboker.substack.com/subscribe';

/** Resolve the subscribe destination for an article, falling back to the global default. */
export function resolveSubscribeUrl(articleUrl?: string | null): string {
  const trimmed = articleUrl?.trim();
  return trimmed || DEFAULT_SUBSCRIBE_URL;
}
