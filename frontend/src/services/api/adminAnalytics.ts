/**
 * API client for admin analytics: Cloudflare traffic, Google Search Console (SEO),
 * and Threads engagement insights. All endpoints require an admin Bearer token and
 * always return 200 with `configured`/`available` flags when an upstream is missing.
 */

import { apiClient } from './client';
import { useAppStore } from '@/store/useAppStore';

function adminAuthConfig() {
    const token = useAppStore.getState().token;
    if (!token) throw new Error('Not authenticated');
    return { headers: { Authorization: `Bearer ${token}` } };
}

// ── Cloudflare zone analytics ──────────────────────────────────────────────
export interface CloudflareOverview {
    configured: boolean;
    available: boolean;
    detail?: string;
    range?: { start: string; end: string; days: number };
    totals?: { requests: number; pageViews: number; uniques: number };
    series?: { date: string; requests: number; pageViews: number; uniques: number }[];
    dashboards: { cloudflare: string; googleAnalytics: string };
}

export async function getCloudflareOverview(days = 7): Promise<CloudflareOverview> {
    const res = await apiClient.get<CloudflareOverview>('/api/admin/analytics/overview', {
        ...adminAuthConfig(),
        params: { days },
    });
    return res.data;
}

// ── Google Search Console (SEO) ────────────────────────────────────────────
export interface SeoRow {
    key: string | null;
    clicks: number;
    impressions: number;
    ctr: number;
    position: number;
}

export interface SeoOverview {
    configured: boolean;
    detail?: string;
    site_url?: string;
    range?: { start: string; end: string; days: number };
    totals?: { clicks: number; impressions: number; ctr: number };
    top_queries?: SeoRow[];
    top_pages?: SeoRow[];
    fetched_at?: string;
}

export async function getSeoOverview(days = 28, refresh = false): Promise<SeoOverview> {
    const res = await apiClient.get<SeoOverview>('/api/admin/seo/overview', {
        ...adminAuthConfig(),
        params: { days, refresh },
    });
    return res.data;
}

// ── Threads (Meta) engagement insights ─────────────────────────────────────
export interface ThreadsPostInsight {
    episode_id: string | null;
    media_id: string | null;
    url: string | null;
    posted_at: string | null;
    metrics: Record<string, number>;
    error?: string;
}

export interface ThreadsInsights {
    configured: boolean;
    available: boolean;
    detail?: string;
    range?: { days: number };
    metrics?: Record<string, number>;
    followers?: number | null;
    recent_posts?: ThreadsPostInsight[];
}

export async function getThreadsInsights(days = 28, posts = 5): Promise<ThreadsInsights> {
    const res = await apiClient.get<ThreadsInsights>('/api/admin/threads/insights', {
        ...adminAuthConfig(),
        params: { days, posts },
    });
    return res.data;
}

// ── Facebook Page insights ─────────────────────────────────────────────────
export interface FacebookInsights {
    configured: boolean;
    available: boolean;
    detail?: string;
    range?: { days: number };
    name?: string | null;
    fans?: number | null;
    followers?: number | null;
    metrics?: Record<string, number>;
}

export async function getFacebookInsights(days = 28): Promise<FacebookInsights> {
    const res = await apiClient.get<FacebookInsights>('/api/admin/facebook/insights', {
        ...adminAuthConfig(),
        params: { days },
    });
    return res.data;
}
