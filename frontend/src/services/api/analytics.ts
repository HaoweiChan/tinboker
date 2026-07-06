import { apiClient } from './client';

export interface ClickEvent {
    type: 'podcast' | 'stock' | 'episode';
    id: string; // "gooaye", "2330", etc.
}

/**
 * Track user interaction (click) for trending algorithms.
 * Fire-and-forget.
 */
export const trackClick = async (event: ClickEvent): Promise<void> => {
    try {
        await apiClient.post('/api/analytics/click', event);
    } catch (error) {
        // Silently fail for analytics
        if (import.meta.env.DEV) {
            console.warn('[Analytics] Failed to track click:', error);
        }
    }
};

// ── Subscription funnel (issue #424) ────────────────────────────────────────
// A `source` names the CTA slot that sent the user (snake_case, e.g.
// "article_detail_end", "articles_hero", "ticker_page", "subscribe_page").
// Keep new slots in sync with docs/features/subscription-funnel.md.

/**
 * Absolute URL of the outbound subscription entry point. Point an anchor/button
 * at this: the backend records the click (server-side, reliable) then 302-redirects
 * to the config-driven newsletter destination (Substack today).
 */
export const subscribeOutboundUrl = (source: string): string => {
    const base = apiClient.defaults.baseURL ?? '';
    return `${base}/api/subscribe?source=${encodeURIComponent(source)}`;
};

/**
 * Beacon that the subscribe landing page was viewed. Fire-and-forget.
 */
export const trackSubscribeView = async (source: string): Promise<void> => {
    try {
        await apiClient.post('/api/subscribe/view', { source });
    } catch (error) {
        if (import.meta.env.DEV) {
            console.warn('[Analytics] Failed to track subscribe view:', error);
        }
    }
};
