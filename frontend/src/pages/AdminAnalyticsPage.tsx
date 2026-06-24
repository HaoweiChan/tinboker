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
    Mic,
    Star,
    Bookmark,
    UserPlus,
} from 'lucide-react';
import {
    getCloudflareOverview,
    getSeoOverview,
    getThreadsInsights,
    getFacebookInsights,
    getMemberAnalytics,
    type CloudflareOverview,
    type SeoOverview,
    type SeoRow,
    type ThreadsInsights,
    type FacebookInsights,
    type MemberAnalytics,
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
    <div className="rounded-xl border border-border bg-card p-4">
        <div className="flex items-center gap-2 text-muted-foreground">
            {icon}
            <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
        </div>
        <div className="mt-2 text-2xl font-bold text-foreground">{value}</div>
    </div>
);

const NotConnected: React.FC<{ detail?: string; href: string; cta: string }> = ({
    detail,
    href,
    cta,
}) => (
    <div className="mt-4 flex flex-col gap-3 rounded-lg border border-dashed border-border bg-muted/50 p-4">
        <div className="flex items-start gap-2 text-base text-muted-foreground">
            <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary" />
            <span>{detail || 'Not connected.'}</span>
        </div>
        <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex w-fit items-center gap-2 rounded-lg bg-muted px-3 py-1.5 text-base font-medium text-foreground transition-colors hover:bg-muted/70"
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
        <h4 className="mb-2 text-base font-semibold text-foreground">{title}</h4>
        <div className="overflow-x-auto rounded-lg border border-border">
            <table className="min-w-full text-base">
                <thead className="bg-muted text-xs uppercase text-muted-foreground">
                    <tr>
                        <th className="px-3 py-2 text-left font-medium">{isPage ? 'Page' : 'Query'}</th>
                        <th className="px-3 py-2 text-right font-medium">Clicks</th>
                        <th className="px-3 py-2 text-right font-medium">Impr.</th>
                        <th className="px-3 py-2 text-right font-medium">CTR</th>
                        <th className="px-3 py-2 text-right font-medium">Pos.</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-border">
                    {rows.length === 0 ? (
                        <tr>
                            <td colSpan={5} className="px-3 py-4 text-center text-muted-foreground">
                                No data in this period
                            </td>
                        </tr>
                    ) : (
                        rows.map((r, i) => (
                            <tr key={i} className="text-foreground">
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

// Top-N ranked list of saved-interest items (label + count), with a relative bar.
const RankList: React.FC<{
    icon: React.ReactNode;
    title: string;
    rows: { label: string; count: number }[];
}> = ({ icon, title, rows }) => {
    const max = rows.reduce((m, r) => Math.max(m, r.count), 0) || 1;
    return (
        <div>
            <h4 className="mb-2 flex items-center gap-2 text-base font-semibold text-foreground">
                {icon} {title}
            </h4>
            <div className="rounded-lg border border-border">
                {rows.length === 0 ? (
                    <div className="px-3 py-4 text-center text-base text-muted-foreground">No saves yet</div>
                ) : (
                    rows.map((r, i) => (
                        <div key={i} className="flex items-center gap-3 border-b border-border px-3 py-2 last:border-0">
                            <span className="w-5 text-right text-xs tabular-nums text-muted-foreground">{i + 1}</span>
                            <div className="min-w-0 flex-1">
                                <div className="truncate text-base text-foreground" title={r.label}>{r.label}</div>
                                <div className="mt-1 h-1.5 rounded-full bg-muted">
                                    <div className="h-1.5 rounded-full bg-accent-info" style={{ width: `${(r.count / max) * 100}%` }} />
                                </div>
                            </div>
                            <span className="text-base font-semibold tabular-nums text-foreground">{r.count}</span>
                        </div>
                    ))
                )}
            </div>
        </div>
    );
};

const SectionCard: React.FC<{
    icon: React.ReactNode;
    title: string;
    subtitle: string;
    children: React.ReactNode;
}> = ({ icon, title, subtitle, children }) => (
    <div className="rounded-xl border border-border bg-card p-6">
        <div className="flex items-center gap-3">
            <div className="rounded-lg bg-muted p-2">{icon}</div>
            <div>
                <h2 className="text-xl font-semibold text-foreground">{title}</h2>
                <p className="text-base text-muted-foreground">{subtitle}</p>
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
            <CheckCircle className="h-4 w-4 flex-shrink-0 text-sentiment-bull" />
        ) : (
            <AlertTriangle className="h-4 w-4 flex-shrink-0 text-primary" />
        )}
        <div className="min-w-0">
            <span className="text-base font-medium text-foreground">{label}</span>
            <span className="ml-2 text-base text-muted-foreground">{detail}</span>
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
    const [members, setMembers] = useState<MemberAnalytics | null>(null);
    const [loading, setLoading] = useState(true);

    const load = useCallback(async () => {
        setLoading(true);
        // Independent sources — settle each on its own so one failure never blanks the page.
        const [cfRes, seoRes, thRes, fbRes, memRes] = await Promise.allSettled([
            getCloudflareOverview(7),
            getSeoOverview(28),
            getThreadsInsights(28, 5),
            getFacebookInsights(28),
            getMemberAnalytics(10),
        ]);
        if (cfRes.status === 'fulfilled') setCf(cfRes.value);
        if (seoRes.status === 'fulfilled') setSeo(seoRes.value);
        if (thRes.status === 'fulfilled') setThreads(thRes.value);
        if (fbRes.status === 'fulfilled') setFb(fbRes.value);
        if (memRes.status === 'fulfilled') setMembers(memRes.value);
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
                    <h1 className="text-2xl font-bold text-foreground">Analytics</h1>
                    <p className="mt-1 text-base text-muted-foreground">
                        Traffic, search performance, and social engagement
                    </p>
                </div>
                <button
                    onClick={load}
                    disabled={loading}
                    className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-base text-foreground hover:bg-muted disabled:opacity-50"
                >
                    <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                    Refresh
                </button>
            </div>

            {/* Registered members (first-party saved-interest) */}
            <SectionCard
                icon={<Users className="h-5 w-5 text-sentiment-bull" />}
                title="Members"
                subtitle="What our registered members save & follow — first-party signal GA4 can't see. For sessions, retention & visit frequency, use the GA4 reports below."
            >
                <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    <Stat icon={<Users className="h-4 w-4" />} label="Total Members" value={fmt(members?.total_users)} />
                    <Stat
                        icon={<UserPlus className="h-4 w-4" />}
                        label="New (8 wks)"
                        value={fmt(members?.signups.reduce((s, w) => s + w.count, 0))}
                    />
                    <div className="rounded-xl border border-border bg-card p-4 sm:col-span-2">
                        <div className="flex items-center gap-2 text-muted-foreground">
                            <TrendingUp className="h-4 w-4" />
                            <span className="text-xs font-medium uppercase tracking-wide">Signups / week</span>
                        </div>
                        <div className="mt-3 flex items-end gap-1" style={{ height: 40 }}>
                            {(members?.signups || []).map((w) => {
                                const peak = Math.max(1, ...(members?.signups || []).map((x) => x.count));
                                return (
                                    <div
                                        key={w.week}
                                        className="flex-1 rounded-t bg-accent-info"
                                        style={{ height: `${Math.max(4, (w.count / peak) * 100)}%` }}
                                        title={`${w.week}: ${w.count}`}
                                    />
                                );
                            })}
                        </div>
                    </div>
                </div>
                <div className="mt-6 grid gap-6 lg:grid-cols-2">
                    <RankList
                        icon={<Mic className="h-4 w-4 text-muted-foreground" />}
                        title="Top Podcasters (subscribed)"
                        rows={(members?.top_podcasters || []).map((r) => ({ label: r.name, count: r.count }))}
                    />
                    <RankList
                        icon={<Star className="h-4 w-4 text-muted-foreground" />}
                        title="Top Tickers (watchlisted)"
                        rows={(members?.top_tickers || []).map((r) => ({ label: r.ticker, count: r.count }))}
                    />
                    <RankList
                        icon={<Hash className="h-4 w-4 text-muted-foreground" />}
                        title="Top Tags (followed)"
                        rows={(members?.top_tags || []).map((r) => ({ label: r.label, count: r.count }))}
                    />
                    <RankList
                        icon={<Bookmark className="h-4 w-4 text-muted-foreground" />}
                        title="Top Episodes (bookmarked)"
                        rows={(members?.top_episodes || []).map((r) => ({ label: r.title, count: r.count }))}
                    />
                </div>
            </SectionCard>

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
                                className="inline-flex items-center gap-1 text-base text-muted-foreground hover:text-foreground"
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
                icon={<Search className="h-5 w-5 text-accent-info" />}
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
                                className="inline-flex items-center gap-1 text-base text-muted-foreground hover:text-foreground"
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
                icon={<Hash className="h-5 w-5 text-foreground" />}
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
                            <div className="mt-6 overflow-x-auto rounded-lg border border-border">
                                <table className="min-w-full text-base">
                                    <thead className="bg-muted text-xs uppercase text-muted-foreground">
                                        <tr>
                                            <th className="px-3 py-2 text-left font-medium">Recent Post</th>
                                            <th className="px-3 py-2 text-right font-medium">Views</th>
                                            <th className="px-3 py-2 text-right font-medium">Likes</th>
                                            <th className="px-3 py-2 text-right font-medium">Replies</th>
                                            <th className="px-3 py-2 text-right font-medium">Reposts</th>
                                        </tr>
                                    </thead>
                                    <tbody className="divide-y divide-border">
                                        {threads.recent_posts.map((p, i) => (
                                            <tr key={i} className="text-foreground">
                                                <td className="max-w-xs truncate px-3 py-2">
                                                    {p.url ? (
                                                        <a
                                                            href={p.url}
                                                            target="_blank"
                                                            rel="noopener noreferrer"
                                                            className="text-accent-info hover:underline"
                                                        >
                                                            {p.episode_id || p.media_id}
                                                        </a>
                                                    ) : (
                                                        p.episode_id || p.media_id || '—'
                                                    )}
                                                    {p.error && (
                                                        <span className="ml-2 text-xs text-muted-foreground">(no data)</span>
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
                icon={<Facebook className="h-5 w-5 text-accent-info" />}
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
                    className="group flex items-center justify-between rounded-xl border border-border bg-card p-4 text-foreground transition-colors hover:bg-muted"
                >
                    <span className="flex items-center gap-3 text-base font-medium">
                        <Globe className="h-5 w-5 text-orange-500" /> Cloudflare Web Analytics
                    </span>
                    <ExternalLink className="h-4 w-4 opacity-60 group-hover:opacity-100" />
                </a>
                <a
                    href={GA_DASH}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group flex items-center justify-between rounded-xl border border-border bg-card p-4 text-foreground transition-colors hover:bg-muted"
                >
                    <span className="flex items-center gap-3 text-base font-medium">
                        <TrendingUp className="h-5 w-5 text-accent-info" /> Google Analytics
                    </span>
                    <ExternalLink className="h-4 w-4 opacity-60 group-hover:opacity-100" />
                </a>
            </div>

            {/* Tracking Configuration */}
            <div className="rounded-xl border border-border bg-card p-6">
                <h3 className="text-xl font-semibold text-foreground">
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
