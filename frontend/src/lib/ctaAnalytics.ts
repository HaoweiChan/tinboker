/**
 * Lightweight CTA analytics — frontend event emit only.
 *
 * Keeps the surface small and dependency-free so backend tracking can land
 * separately (see #423). Each event is:
 *   1. pushed to `window.dataLayer` (GA/GTM style) when present,
 *   2. re-dispatched as a `tinboker:cta` CustomEvent on `window` so other
 *      listeners (or tests) can subscribe,
 *   3. logged in DEV for quick verification.
 *
 * Fire-and-forget; never throws into the render path.
 */

import type { NewsletterPlacement } from '@/config/site';

export type CtaAction = 'impression' | 'click';

export interface CtaEvent {
  /** Logical CTA family. */
  cta: 'newsletter';
  /** Where on the page the CTA was rendered. */
  placement: NewsletterPlacement;
  /** Impression when it enters the viewport, click when activated. */
  action: CtaAction;
}

interface WindowWithDataLayer extends Window {
  dataLayer?: Array<Record<string, unknown>>;
}

export const trackCtaEvent = (event: CtaEvent): void => {
  if (typeof window === 'undefined') return;
  try {
    const w = window as WindowWithDataLayer;
    w.dataLayer = w.dataLayer || [];
    w.dataLayer.push({ event: 'cta', ...event });
    window.dispatchEvent(new CustomEvent('tinboker:cta', { detail: event }));
    if (import.meta.env.DEV) {
      console.log('[CTA]', event.cta, event.placement, event.action);
    }
  } catch {
    // Analytics must never break the UI.
  }
};
