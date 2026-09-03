/**
 * API client for admin analytics: Cloudflare traffic, AdSense monetization, Google
 * Search Console (SEO), Threads/Facebook engagement, and 方格子/Substack reading
 * stats. All endpoints require an admin Bearer token and
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

// ── Google AdSense monetization ────────────────────────────────────────────
export interface AdSenseRow {
    url: string | null;
    earnings: number;
    pageViews: number;
    rpm: number;
}

export interface AdSenseOverview {
    configured: boolean;
    available: boolean;
    detail?: string;
    account?: string;
    /** `state` is GETTING_READY while the site is still under AdSense review. */
    site?: { domain: string | null; state: string | null; autoAdsEnabled: boolean | null };
    range?: { start: string; end: string; days: number };
    currency?: string;
    totals?: {
        earnings: number;
        pageViews: number;
        rpm: number;
        impressions: number;
        clicks: number;
        ctr: number;
        coverage: number;
        viewability: number;
    };
    series?: { date: string; earnings: number; pageViews: number; rpm: number }[];
    top_pages?: AdSenseRow[];
    dashboard: string;
}

export async function getAdSenseOverview(days = 28): Promise<AdSenseOverview> {
    const res = await apiClient.get<AdSenseOverview>('/api/admin/analytics/adsense', {
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
    series?: { date: string; clicks: number; impressions: number }[];
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
    series?: { date: string; [metric: string]: string | number }[];
}

export async function getFacebookInsights(days = 28): Promise<FacebookInsights> {
    const res = await apiClient.get<FacebookInsights>('/api/admin/facebook/insights', {
        ...adminAuthConfig(),
        params: { days },
    });
    return res.data;
}

// ── Syndication reading stats (方格子 / Substack) ────────────────────────────
// Counts are lifetime totals, not windowed: both platforms keep a running counter per
// article and no history, so growth comes from the daily snapshot chart below.
export interface SyndicationPostInsight {
    title: string;
    url: string | null;
    /** vocus */
    article_id?: string | null;
    reads?: number | null;
    likes?: number | null;
    /** Substack */
    post_id?: string | null;
    views?: number | null;
    reactions?: number | null;
}

interface SyndicationInsightsBase {
    configured: boolean;
    available: boolean;
    detail?: string;
    lifetime?: boolean;
    truncated?: boolean;
    /** Which response key each number came from — the API is undocumented. */
    field_map?: Record<string, string>;
    /** Keys the platform actually sent, when no count field matched. */
    sample_keys?: string[];
    recent_posts?: SyndicationPostInsight[];
}

export interface VocusInsights extends SyndicationInsightsBase {
    articles?: number;
    reads?: number;
    likes?: number;
    bookmarks?: number;
    token?: { configured: boolean; expired: boolean; expiring_soon: boolean; seconds_left: number | null };
}

export interface SubstackInsights extends SyndicationInsightsBase {
    posts?: number;
    views?: number;
    reactions?: number;
    comments?: number;
    /** The list endpoint that answered; the path is not documented. */
    source?: string | null;
}

export async function getVocusInsights(posts = 10): Promise<VocusInsights> {
    const res = await apiClient.get<VocusInsights>('/api/admin/vocus/insights', {
        ...adminAuthConfig(),
        params: { posts },
    });
    return res.data;
}

export async function getSubstackInsights(posts = 10): Promise<SubstackInsights> {
    const res = await apiClient.get<SubstackInsights>('/api/admin/substack/insights', {
        ...adminAuthConfig(),
        params: { posts },
    });
    return res.data;
}

// ── Registered-member analytics (first-party, from the users collection) ─────
export interface MemberAnalytics {
    total_users: number;
    signups: { week: string; count: number }[];
    top_podcasters: { name: string; count: number }[];
    top_tags: { slug: string; label: string; count: number }[];
    top_tickers: { ticker: string; count: number }[];
    top_episodes: { episode_id: string; title: string; count: number }[];
}

export async function getMemberAnalytics(top = 10): Promise<MemberAnalytics> {
    const res = await apiClient.get<MemberAnalytics>('/api/admin/analytics/members', {
        ...adminAuthConfig(),
        params: { top },
    });
    return res.data;
}

// ── Audience-growth snapshots (daily Threads/FB follower + fan counts) ───────
export interface AnalyticsSnapshot {
    day: string;
    threads_followers: number | null;
    fb_followers: number | null;
    fb_fans: number | null;
    /** Lifetime reads across all published articles, as of that day. */
    vocus_reads: number | null;
    vocus_articles: number | null;
    substack_reads: number | null;
    substack_posts: number | null;
}

export async function getAnalyticsHistory(days = 90): Promise<AnalyticsSnapshot[]> {
    const res = await apiClient.get<{ snapshots: AnalyticsSnapshot[] }>('/api/admin/analytics/history', {
        ...adminAuthConfig(),
        params: { days },
    });
    return res.data.snapshots;
}
