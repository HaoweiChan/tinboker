/**
 * Admin Analytics Page — live traffic + SEO + social engagement.
 *
 * Pulls Cloudflare zone analytics, Google Search Console (clicks/impressions/CTR +
 * top queries & pages), and Threads + Facebook Page engagement insights, and renders
 * them inline.
 * Each source degrades to a "not connected" note + dashboard link when its upstream
 * credentials aren't configured, so the page is always safe to open.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
    ExternalLink,
    TrendingUp,
    Globe,
    Search,
    CheckCircle,
    AlertTriangle,
    RefreshCw,
    Eye,
    Users,
    Server,
    Hash,
    Heart,
    MessageCircle,
    Repeat2,
    Facebook,
    ThumbsUp,
    MousePointerClick,
} from 'lucide-react';
import {
    getCloudflareOverview,
    getSeoOverview,
    getThreadsInsights,
    getFacebookInsights,
    type CloudflareOverview,
    type SeoOverview,
    type SeoRow,
    type ThreadsInsights,
    type FacebookInsights,
} from '@/services/api/adminAnalytics';

// ── formatting helpers ─────────────────────────────────────────────────────
const nf = new Intl.NumberFormat('en-US');
const fmt = (n: number | null | undefined): string =>
    n === null || n === undefined ? '—' : nf.format(n);
const pct = (ctr: number | null | undefined): string =>
    ctr === null || ctr === undefined ? '—' : `${(ctr * 100).toFixed(2)}%`;
const shortPath = (url: string | null): string => {
    if (!url) return '—';
    try {
        const u = new URL(url);
        return u.pathname + u.search || '/';
    } catch {
        return url;
    }
};

// ── small presentational pieces ────────────────────────────────────────────
const Stat: React.FC<{ icon: React.ReactNode; label: string; value: string }> = ({
    icon,
    label,
    value,
}) => (
    <div className="rounded-xl border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
        <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400">
            {icon}
            <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
        </div>
        <div className="mt-2 text-2xl font-bold text-gray-900 dark:text-white">{value}</div>
    </div>
);

const NotConnected: React.FC<{ detail?: string; href: string; cta: string }> = ({
    detail,
    href,
    cta,
}) => (
    <div className="mt-4 flex flex-col gap-3 rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4 dark:border-gray-600 dark:bg-gray-800/50">
        <div className="flex items-start gap-2 text-sm text-gray-600 dark:text-gray-400">
            <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-yellow-500" />
            <span>{detail || 'Not connected.'}</span>
        </div>
        <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex w-fit items-center gap-2 rounded-lg bg-gray-100 px-3 py-1.5 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600"
        >
            {cta}
            <ExternalLink className="h-4 w-4" />
        </a>
    </div>
);

const SeoTable: React.FC<{ title: string; rows: SeoRow[]; isPage?: boolean }> = ({
    title,
    rows,
    isPage,
}) => (
    <div>
        <h4 className="mb-2 text-sm font-semibold text-gray-700 dark:text-gray-300">{title}</h4>
        <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
            <table className="min-w-full text-sm">
                <thead className="bg-gray-50 text-xs uppercase text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                    <tr>
                        <th className="px-3 py-2 text-left font-medium">{isPage ? 'Page' : 'Query'}</th>
                        <th className="px-3 py-2 text-right font-medium">Clicks</th>
                        <th className="px-3 py-2 text-right font-medium">Impr.</th>
                        <th className="px-3 py-2 text-right font-medium">CTR</th>
                        <th className="px-3 py-2 text-right font-medium">Pos.</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                    {rows.length === 0 ? (
                        <tr>
                            <td colSpan={5} className="px-3 py-4 text-center text-gray-400">
                                No data in this period
                            </td>
                        </tr>
                    ) : (
                        rows.map((r, i) => (
                            <tr key={i} className="text-gray-700 dark:text-gray-300">
                                <td className="max-w-xs truncate px-3 py-2" title={r.key || ''}>
                                    {isPage ? shortPath(r.key) : r.key || '—'}
                                </td>
                                <td className="px-3 py-2 text-right tabular-nums">{fmt(r.clicks)}</td>
                                <td className="px-3 py-2 text-right tabular-nums">{fmt(r.impressions)}</td>
                                <td className="px-3 py-2 text-right tabular-nums">{pct(r.ctr)}</td>
                                <td className="px-3 py-2 text-right tabular-nums">{r.position.toFixed(1)}</td>
                            </tr>
                        ))
                    )}
                </tbody>
            </table>
        </div>
    </div>
);

const SectionCard: React.FC<{
    icon: React.ReactNode;
    title: string;
    subtitle: string;
    children: React.ReactNode;
}> = ({ icon, title, subtitle, children }) => (
    <div className="rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-800">
        <div className="flex items-center gap-3">
            <div className="rounded-lg bg-gray-100 p-2 dark:bg-gray-700">{icon}</div>
            <div>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h2>
                <p className="text-sm text-gray-500 dark:text-gray-400">{subtitle}</p>
            </div>
        </div>
        {children}
    </div>
);

interface TrackingItemProps {
    label: string;
    detail: string;
    status: 'active' | 'pending';
}
const TrackingItem: React.FC<TrackingItemProps> = ({ label, detail, status }) => (
    <li className="flex items-center gap-3 rounded-lg px-3 py-2.5">
        {status === 'active' ? (
            <CheckCircle className="h-4 w-4 flex-shrink-0 text-green-500" />
        ) : (
            <AlertTriangle className="h-4 w-4 flex-shrink-0 text-yellow-500" />
        )}
        <div className="min-w-0">
            <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{label}</span>
            <span className="ml-2 text-sm text-gray-500 dark:text-gray-400">{detail}</span>
        </div>
    </li>
);

const CF_DASH = 'https://dash.cloudflare.com/?to=/:account/web-analytics';
const GSC_DASH = 'https://search.google.com/search-console?resource_id=sc-domain:tinboker.com';
const GA_DASH = 'https://analytics.google.com/analytics/web/#/p464726391/reports/intelligenthome';

export const AdminAnalyticsPage: React.FC = () => {
    const [cf, setCf] = useState<CloudflareOverview | null>(null);
    const [seo, setSeo] = useState<SeoOverview | null>(null);
    const [threads, setThreads] = useState<ThreadsInsights | null>(null);
    const [fb, setFb] = useState<FacebookInsights | null>(null);
    const [loading, setLoading] = useState(true);

    const load = useCallback(async () => {
        setLoading(true);
        // Independent sources — settle each on its own so one failure never blanks the page.
        const [cfRes, seoRes, thRes, fbRes] = await Promise.allSettled([
            getCloudflareOverview(7),
            getSeoOverview(28),
            getThreadsInsights(28, 5),
            getFacebookInsights(28),
        ]);
        if (cfRes.status === 'fulfilled') setCf(cfRes.value);
        if (seoRes.status === 'fulfilled') setSeo(seoRes.value);
        if (thRes.status === 'fulfilled') setThreads(thRes.value);
        if (fbRes.status === 'fulfilled') setFb(fbRes.value);
        setLoading(false);
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    const tm = threads?.metrics || {};
    const fm = fb?.metrics || {};

    return (
        <div className="mx-auto max-w-7xl space-y-8">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Analytics</h1>
                    <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                        Traffic, search performance, and social engagement
                    </p>
                </div>
                <button
                    onClick={load}
                    disabled={loading}
                    className="flex items-center gap-2 rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
                >
                    <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                    Refresh
                </button>
            </div>

            {/* Cloudflare traffic */}
            <SectionCard
                icon={<Globe className="h-5 w-5 text-orange-500" />}
                title="Cloudflare Web Traffic"
                subtitle={
                    cf?.range
                        ? `Last ${cf.range.days} days (${cf.range.start} → ${cf.range.end})`
                        : 'Real-time traffic from the Cloudflare edge'
                }
            >
                {cf?.available && cf.totals ? (
                    <>
                        <div className="mt-4 grid gap-4 sm:grid-cols-3">
                            <Stat icon={<Eye className="h-4 w-4" />} label="Page Views" value={fmt(cf.totals.pageViews)} />
                            <Stat icon={<Users className="h-4 w-4" />} label="Visits" value={fmt(cf.totals.uniques)} />
                            <Stat icon={<Server className="h-4 w-4" />} label="Requests" value={fmt(cf.totals.requests)} />
                        </div>
                        <div className="mt-4 flex justify-end">
                            <a
                                href={cf.dashboards.cloudflare}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
                            >
                                Open Cloudflare dashboard <ExternalLink className="h-4 w-4" />
                            </a>
                        </div>
                    </>
                ) : (
                    <NotConnected
                        detail={
                            cf?.detail ||
                            (loading ? 'Loading…' : 'Cloudflare analytics token not configured.')
                        }
                        href={cf?.dashboards.cloudflare || CF_DASH}
                        cta="Open Cloudflare dashboard"
                    />
                )}
            </SectionCard>

            {/* SEO / Search Console */}
            <SectionCard
                icon={<Search className="h-5 w-5 text-blue-500" />}
                title="SEO Performance"
                subtitle={
                    seo?.range
                        ? `Google Search Console · last ${seo.range.days} days`
                        : 'Organic search clicks, impressions, and top pages & queries'
                }
            >
                {seo?.configured && seo.totals ? (
                    <>
                        <div className="mt-4 grid gap-4 sm:grid-cols-3">
                            <Stat icon={<TrendingUp className="h-4 w-4" />} label="Clicks" value={fmt(seo.totals.clicks)} />
                            <Stat icon={<Eye className="h-4 w-4" />} label="Impressions" value={fmt(seo.totals.impressions)} />
                            <Stat icon={<Hash className="h-4 w-4" />} label="Avg CTR" value={pct(seo.totals.ctr)} />
                        </div>
                        <div className="mt-6 grid gap-6 lg:grid-cols-2">
                            <SeoTable title="Top Search Queries" rows={seo.top_queries || []} />
                            <SeoTable title="Top Pages" rows={seo.top_pages || []} isPage />
                        </div>
                        <div className="mt-4 flex justify-end">
                            <a
                                href={GSC_DASH}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300"
                            >
                                Open Search Console <ExternalLink className="h-4 w-4" />
                            </a>
                        </div>
                    </>
                ) : (
                    <NotConnected
                        detail={
                            seo?.detail ||
                            (loading ? 'Loading…' : 'Set GSC_SITE_URL to enable SEO monitoring.')
                        }
                        href={GSC_DASH}
                        cta="Open Google Search Console"
                    />
                )}
            </SectionCard>

            {/* Threads engagement */}
            <SectionCard
                icon={<Hash className="h-5 w-5 text-purple-500" />}
                title="Threads Engagement"
                subtitle={
                    threads?.range
                        ? `Meta Threads · last ${threads.range.days} days`
                        : 'Views, likes, replies & reposts on auto-published episode threads'
                }
            >
                {threads?.available ? (
                    <>
                        <div className="mt-4 grid gap-4 sm:grid-cols-3 lg:grid-cols-6">
                            <Stat icon={<Eye className="h-4 w-4" />} label="Views" value={fmt(tm.views)} />
                            <Stat icon={<Heart className="h-4 w-4" />} label="Likes" value={fmt(tm.likes)} />
                            <Stat icon={<MessageCircle className="h-4 w-4" />} label="Replies" value={fmt(tm.replies)} />
                            <Stat icon={<Repeat2 className="h-4 w-4" />} label="Reposts" value={fmt(tm.reposts)} />
                            <Stat icon={<Repeat2 className="h-4 w-4" />} label="Quotes" value={fmt(tm.quotes)} />
                            <Stat icon={<Users className="h-4 w-4" />} label="Followers" value={fmt(threads.followers)} />
                        </div>
                        {threads.recent_posts && threads.recent_posts.length > 0 && (
                            <div className="mt-6 overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
                                <table className="min-w-full text-sm">
                                    <thead className="bg-gray-50 text-xs uppercase text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                                        <tr>
                                            <th className="px-3 py-2 text-left font-medium">Recent Post</th>
                                            <th className="px-3 py-2 text-right font-medium">Views</th>
                                            <th className="px-3 py-2 text-right font-medium">Likes</th>
                                            <th className="px-3 py-2 text-right font-medium">Replies</th>
                                            <th className="px-3 py-2 text-right font-medium">Reposts</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                                        {threads.recent_posts.map((p, i) => (
                                            <tr key={i} className="text-gray-700 dark:text-gray-300">
                                                <td className="max-w-xs truncate px-3 py-2">
                                                    {p.url ? (
                                                        <a
                                                            href={p.url}
                                                            target="_blank"
                                                            rel="noopener noreferrer"
                                                            className="text-blue-600 hover:underline dark:text-blue-400"
                                                        >
                                                            {p.episode_id || p.media_id}
                                                        </a>
                                                    ) : (
                                                        p.episode_id || p.media_id || '—'
                                                    )}
                                                    {p.error && (
                                                        <span className="ml-2 text-xs text-gray-400">(no data)</span>
                                                    )}
                                                </td>
                                                <td className="px-3 py-2 text-right tabular-nums">{fmt(p.metrics.views)}</td>
                                                <td className="px-3 py-2 text-right tabular-nums">{fmt(p.metrics.likes)}</td>
                                                <td className="px-3 py-2 text-right tabular-nums">{fmt(p.metrics.replies)}</td>
                                                <td className="px-3 py-2 text-right tabular-nums">{fmt(p.metrics.reposts)}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </>
                ) : (
                    <NotConnected
                        detail={
                            threads?.detail ||
                            (loading
                                ? 'Loading…'
                                : 'Set THREADS_ACCESS_TOKEN and THREADS_USER_ID to enable Threads insights.')
                        }
                        href="https://www.threads.net/"
                        cta="Open Threads"
                    />
                )}
            </SectionCard>

            {/* Facebook Page engagement */}
            <SectionCard
                icon={<Facebook className="h-5 w-5 text-blue-600" />}
                title="Facebook Page"
                subtitle={
                    fb?.name
                        ? `${fb.name} · last ${fb.range?.days ?? 28} days`
                        : 'Page audience, views & engagement'
                }
            >
                {fb?.available ? (
                    <div className="mt-4 grid gap-4 sm:grid-cols-3 lg:grid-cols-5">
                        <Stat icon={<Users className="h-4 w-4" />} label="Followers" value={fmt(fb.followers)} />
                        <Stat icon={<ThumbsUp className="h-4 w-4" />} label="Page Likes" value={fmt(fb.fans)} />
                        <Stat icon={<Eye className="h-4 w-4" />} label="Page Views" value={fmt(fm.page_views_total)} />
                        <Stat icon={<Heart className="h-4 w-4" />} label="Engagements" value={fmt(fm.page_post_engagements)} />
                        <Stat icon={<MousePointerClick className="h-4 w-4" />} label="Actions" value={fmt(fm.page_total_actions)} />
                    </div>
                ) : (
                    <NotConnected
                        detail={
                            fb?.detail ||
                            (loading
                                ? 'Loading…'
                                : 'Set FACEBOOK_PAGE_ID and FACEBOOK_PAGE_ACCESS_TOKEN to enable Facebook insights.')
                        }
                        href="https://business.facebook.com/latest/insights/overview"
                        cta="Open Meta Business Suite"
                    />
                )}
            </SectionCard>

            {/* External dashboards */}
            <div className="grid gap-4 sm:grid-cols-2">
                <a
                    href={CF_DASH}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group flex items-center justify-between rounded-xl border border-gray-200 bg-white p-4 text-gray-700 transition-colors hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700/50"
                >
                    <span className="flex items-center gap-3 text-sm font-medium">
                        <Globe className="h-5 w-5 text-orange-500" /> Cloudflare Web Analytics
                    </span>
                    <ExternalLink className="h-4 w-4 opacity-60 group-hover:opacity-100" />
                </a>
                <a
                    href={GA_DASH}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group flex items-center justify-between rounded-xl border border-gray-200 bg-white p-4 text-gray-700 transition-colors hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700/50"
                >
                    <span className="flex items-center gap-3 text-sm font-medium">
                        <TrendingUp className="h-5 w-5 text-blue-500" /> Google Analytics
                    </span>
                    <ExternalLink className="h-4 w-4 opacity-60 group-hover:opacity-100" />
                </a>
            </div>

            {/* Tracking Configuration */}
            <div className="rounded-xl border border-gray-200 bg-white p-6 dark:border-gray-700 dark:bg-gray-800">
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                    Tracking Configuration
                </h3>
                <ul className="mt-3 space-y-1">
                    <TrackingItem
                        label="Cloudflare Web Analytics"
                        detail={cf?.available ? 'Connected (GraphQL API)' : 'Enabled (auto-injected via Cloudflare Pages)'}
                        status="active"
                    />
                    <TrackingItem label="Google Analytics" detail="G-VYVPJ535WH" status="active" />
                    <TrackingItem
                        label="Google Search Console"
                        detail={seo?.configured ? `Connected (${seo.site_url || 'sc-domain:tinboker.com'})` : 'Verify domain ownership'}
                        status={seo?.configured ? 'active' : 'pending'}
                    />
                    <TrackingItem
                        label="Threads (Meta)"
                        detail={threads?.available ? 'Connected (Graph API)' : 'Set THREADS_ACCESS_TOKEN to enable'}
                        status={threads?.available ? 'active' : 'pending'}
                    />
                    <TrackingItem
                        label="Facebook Page (Meta)"
                        detail={fb?.available ? 'Connected (Graph API)' : 'Set FACEBOOK_PAGE_ACCESS_TOKEN to enable'}
                        status={fb?.available ? 'active' : 'pending'}
                    />
                </ul>
            </div>
        </div>
    );
};
