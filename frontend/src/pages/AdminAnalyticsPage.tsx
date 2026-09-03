/**
 * Admin Analytics Page — live traffic + SEO + social engagement.
 *
 * Pulls Cloudflare zone analytics, AdSense monetization (earnings/RPM/fill rate),
 * Google Search Console (clicks/impressions/CTR + top queries & pages), Threads +
 * Facebook Page engagement insights, and 方格子/Substack reading stats, and renders
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
    DollarSign,
    Gauge,
    Percent,
    BookOpen,
    Mail,
} from 'lucide-react';
import {
    getCloudflareOverview,
    getAdSenseOverview,
    getSeoOverview,
    getThreadsInsights,
    getFacebookInsights,
    getMemberAnalytics,
    getAnalyticsHistory,
    getVocusInsights,
    getSubstackInsights,
    type CloudflareOverview,
    type AdSenseOverview,
    type SeoOverview,
    type SeoRow,
    type AdSenseRow,
    type ThreadsInsights,
    type FacebookInsights,
    type MemberAnalytics,
    type AnalyticsSnapshot,
    type VocusInsights,
    type SubstackInsights,
    type SyndicationPostInsight,
} from '@/services/api/adminAnalytics';
import { TrendChart, type TrendPoint } from '@/components/admin/TrendChart';

// ── formatting helpers ─────────────────────────────────────────────────────
const nf = new Intl.NumberFormat('en-US');
const fmt = (n: number | null | undefined): string =>
    n === null || n === undefined ? '—' : nf.format(n);
const pct = (ctr: number | null | undefined): string =>
    ctr === null || ctr === undefined ? '—' : `${(ctr * 100).toFixed(2)}%`;
const money = (n: number | null | undefined, currency = 'USD'): string =>
    n === null || n === undefined
        ? '—'
        : new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(n);
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

// Build chart points from a per-day series row list; x is MM-DD for a compact axis.
const ptsFrom = (rows: Array<Record<string, unknown>> | undefined, key: string): TrendPoint[] =>
    (rows || []).map((r) => ({
        x: String(r.date || '').slice(5),
        y: Number(r[key] ?? 0) || 0,
    }));

const ChartBox: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
    <div className="rounded-xl border border-border bg-card p-4">
        <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">{title}</div>
        {children}
    </div>
);

// Both syndication platforms return the same row shape under different names, so one
// table renders either — the caller says which field is the read count.
const SyndicationTable: React.FC<{
    rows: SyndicationPostInsight[];
    countLabel: string;
    count: (r: SyndicationPostInsight) => number | null | undefined;
    engagementLabel: string;
    engagement: (r: SyndicationPostInsight) => number | null | undefined;
}> = ({ rows, countLabel, count, engagementLabel, engagement }) => (
    <div className="mt-6 overflow-x-auto rounded-lg border border-border">
        <table className="min-w-full text-base">
            <thead className="bg-muted text-xs uppercase text-muted-foreground">
                <tr>
                    <th className="px-3 py-2 text-left font-medium">Recent Article</th>
                    <th className="px-3 py-2 text-right font-medium">{countLabel}</th>
                    <th className="px-3 py-2 text-right font-medium">{engagementLabel}</th>
                </tr>
            </thead>
            <tbody className="divide-y divide-border">
                {rows.map((r, i) => (
                    <tr key={i} className="text-foreground">
                        <td className="max-w-md truncate px-3 py-2" title={r.title}>
                            {r.url ? (
                                <a
                                    href={r.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-accent-info hover:underline"
                                >
                                    {r.title || r.article_id || r.post_id}
                                </a>
                            ) : (
                                r.title || '—'
                            )}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums">{fmt(count(r))}</td>
                        <td className="px-3 py-2 text-right tabular-nums">{fmt(engagement(r))}</td>
                    </tr>
                ))}
            </tbody>
        </table>
    </div>
);

// When a platform answers but no read-count field matched, the keys it *did* send are
// the fix — showing them turns "why is this empty?" into a one-line code change.
const SampleKeys: React.FC<{ keys?: string[] }> = ({ keys }) =>
    keys && keys.length > 0 ? (
        <p className="mt-2 break-words text-xs text-muted-foreground">
            Fields returned: <code>{keys.join(', ')}</code>
        </p>
    ) : null;

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

const AdsPagesTable: React.FC<{ rows: AdSenseRow[]; currency: string }> = ({ rows, currency }) => (
    <div>
        <h4 className="mb-2 text-base font-semibold text-foreground">Top Earning Pages</h4>
        <div className="overflow-x-auto rounded-lg border border-border">
            <table className="min-w-full text-base">
                <thead className="bg-muted text-xs uppercase text-muted-foreground">
                    <tr>
                        <th className="px-3 py-2 text-left font-medium">Page</th>
                        <th className="px-3 py-2 text-right font-medium">Earnings</th>
                        <th className="px-3 py-2 text-right font-medium">Views</th>
                        <th className="px-3 py-2 text-right font-medium">RPM</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-border">
                    {rows.length === 0 ? (
                        <tr>
                            <td colSpan={4} className="px-3 py-4 text-center text-muted-foreground">
                                No data in this period
                            </td>
                        </tr>
                    ) : (
                        rows.map((r, i) => (
                            <tr key={i} className="text-foreground">
                                <td className="max-w-xs truncate px-3 py-2" title={r.url || ''}>
                                    {shortPath(r.url)}
                                </td>
                                <td className="px-3 py-2 text-right tabular-nums">{money(r.earnings, currency)}</td>
                                <td className="px-3 py-2 text-right tabular-nums">{fmt(r.pageViews)}</td>
                                <td className="px-3 py-2 text-right tabular-nums">{money(r.rpm, currency)}</td>
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
const ADSENSE_DASH = 'https://www.google.com/adsense/new/u/0/home';
const GSC_DASH = 'https://search.google.com/search-console?resource_id=sc-domain:tinboker.com';
const GA_DASH = 'https://analytics.google.com/analytics/web/#/p464726391/reports/intelligenthome';

export const AdminAnalyticsPage: React.FC = () => {
    const [cf, setCf] = useState<CloudflareOverview | null>(null);
    const [ads, setAds] = useState<AdSenseOverview | null>(null);
    const [seo, setSeo] = useState<SeoOverview | null>(null);
    const [threads, setThreads] = useState<ThreadsInsights | null>(null);
    const [fb, setFb] = useState<FacebookInsights | null>(null);
    const [vocus, setVocus] = useState<VocusInsights | null>(null);
    const [substack, setSubstack] = useState<SubstackInsights | null>(null);
    const [members, setMembers] = useState<MemberAnalytics | null>(null);
    const [history, setHistory] = useState<AnalyticsSnapshot[]>([]);
    const [loading, setLoading] = useState(true);

    const load = useCallback(async () => {
        setLoading(true);
        // Independent sources — settle each on its own so one failure never blanks the page.
        const [cfRes, adsRes, seoRes, thRes, fbRes, voRes, suRes, memRes, histRes] =
            await Promise.allSettled([
                getCloudflareOverview(28),
                getAdSenseOverview(28),
                getSeoOverview(28),
                getThreadsInsights(28, 5),
                getFacebookInsights(28),
                getVocusInsights(10),
                getSubstackInsights(10),
                getMemberAnalytics(10),
                getAnalyticsHistory(90),
            ]);
        if (cfRes.status === 'fulfilled') setCf(cfRes.value);
        if (adsRes.status === 'fulfilled') setAds(adsRes.value);
        if (seoRes.status === 'fulfilled') setSeo(seoRes.value);
        if (thRes.status === 'fulfilled') setThreads(thRes.value);
        if (fbRes.status === 'fulfilled') setFb(fbRes.value);
        if (voRes.status === 'fulfilled') setVocus(voRes.value);
        if (suRes.status === 'fulfilled') setSubstack(suRes.value);
        if (memRes.status === 'fulfilled') setMembers(memRes.value);
        if (histRes.status === 'fulfilled') setHistory(histRes.value);
        setLoading(false);
    }, []);

    useEffect(() => {
        load();
    }, [load]);

    const tm = threads?.metrics || {};
    const fm = fb?.metrics || {};

    // Reads are a cumulative counter, so a day with no value means "not measured",
    // never "reads went to zero" — carry the last known value forward. Both series
    // share one window so TrendChart's index-aligned x-axis stays honest.
    const firstReadDay = history.findIndex(
        (s) => s.vocus_reads !== null || s.substack_reads !== null,
    );
    const readHistory = firstReadDay < 0 ? [] : history.slice(firstReadDay);
    const readPoints = (pick: (s: AnalyticsSnapshot) => number | null): TrendPoint[] => {
        let last = 0;
        return readHistory.map((s) => {
            const value = pick(s);
            if (value !== null) last = value;
            return { x: s.day.slice(5), y: last };
        });
    };

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
                        {cf.series && cf.series.length >= 2 && (
                            <div className="mt-4 grid gap-4 sm:grid-cols-3">
                                <ChartBox title="Page Views">
                                    <TrendChart series={[{ name: 'Page Views', colorClass: 'text-accent-info', points: ptsFrom(cf.series, 'pageViews') }]} />
                                </ChartBox>
                                <ChartBox title="Visits">
                                    <TrendChart series={[{ name: 'Visits', colorClass: 'text-sentiment-bull', points: ptsFrom(cf.series, 'uniques') }]} />
                                </ChartBox>
                                <ChartBox title="Requests">
                                    <TrendChart series={[{ name: 'Requests', colorClass: 'text-primary', points: ptsFrom(cf.series, 'requests') }]} />
                                </ChartBox>
                            </div>
                        )}
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

            {/* AdSense monetization */}
            <SectionCard
                icon={<DollarSign className="h-5 w-5 text-sentiment-bull" />}
                title="AdSense Revenue"
                subtitle={
                    ads?.range
                        ? `Google AdSense · last ${ads.range.days} days (${ads.range.start} → ${ads.range.end})`
                        : 'Estimated earnings, page RPM, fill rate & viewability'
                }
            >
                {ads?.available && ads.totals ? (
                    <>
                        {/* Until the site clears review no data exists at all — say so, so a
                            row of zeros doesn't read as "ads are broken". */}
                        {ads.site?.state && ads.site.state !== 'READY' && (
                            <div className="mt-4 flex items-start gap-2 rounded-lg border border-dashed border-border bg-muted/50 p-3 text-base text-muted-foreground">
                                <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary" />
                                <span>
                                    {ads.site.domain} is <span className="font-medium text-foreground">{ads.site.state}</span> —
                                    still under AdSense review, so no ads are serving and every metric below is zero.
                                </span>
                            </div>
                        )}
                        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                            <Stat
                                icon={<DollarSign className="h-4 w-4" />}
                                label="Est. Earnings"
                                value={money(ads.totals.earnings, ads.currency)}
                            />
                            <Stat
                                icon={<TrendingUp className="h-4 w-4" />}
                                label="Page RPM"
                                value={money(ads.totals.rpm, ads.currency)}
                            />
                            {/* Coverage = share of ad requests that got filled; a drop here is
                                the first sign something is wrong with serving. */}
                            <Stat
                                icon={<Percent className="h-4 w-4" />}
                                label="Fill Rate"
                                value={pct(ads.totals.coverage)}
                            />
                            {/* Low viewability means Auto ads placed units below the fold. */}
                            <Stat
                                icon={<Gauge className="h-4 w-4" />}
                                label="Viewability"
                                value={pct(ads.totals.viewability)}
                            />
                        </div>
                        <div className="mt-4 grid gap-4 sm:grid-cols-3">
                            <Stat icon={<Eye className="h-4 w-4" />} label="Ad Impressions" value={fmt(ads.totals.impressions)} />
                            <Stat icon={<MousePointerClick className="h-4 w-4" />} label="Clicks" value={fmt(ads.totals.clicks)} />
                            <Stat icon={<Hash className="h-4 w-4" />} label="Impr. CTR" value={pct(ads.totals.ctr)} />
                        </div>
                        {ads.series && ads.series.length >= 2 && (
                            <div className="mt-4 grid gap-4 sm:grid-cols-2">
                                <ChartBox title="Estimated Earnings">
                                    <TrendChart series={[{ name: 'Earnings', colorClass: 'text-sentiment-bull', points: ptsFrom(ads.series, 'earnings') }]} />
                                </ChartBox>
                                <ChartBox title="Page RPM">
                                    <TrendChart series={[{ name: 'RPM', colorClass: 'text-primary', points: ptsFrom(ads.series, 'rpm') }]} />
                                </ChartBox>
                            </div>
                        )}
                        <div className="mt-6">
                            <AdsPagesTable rows={ads.top_pages || []} currency={ads.currency || 'USD'} />
                        </div>
                        <div className="mt-4 flex justify-end">
                            <a
                                href={ads.dashboard || ADSENSE_DASH}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 text-base text-muted-foreground hover:text-foreground"
                            >
                                Open AdSense dashboard <ExternalLink className="h-4 w-4" />
                            </a>
                        </div>
                    </>
                ) : (
                    <NotConnected
                        detail={ads?.detail || (loading ? 'Loading…' : 'AdSense credential not configured.')}
                        href={ads?.dashboard || ADSENSE_DASH}
                        cta="Open AdSense dashboard"
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
                        {seo.series && seo.series.length >= 2 && (
                            <div className="mt-4 grid gap-4 sm:grid-cols-2">
                                <ChartBox title="Clicks">
                                    <TrendChart series={[{ name: 'Clicks', colorClass: 'text-accent-info', points: ptsFrom(seo.series, 'clicks') }]} />
                                </ChartBox>
                                <ChartBox title="Impressions">
                                    <TrendChart series={[{ name: 'Impressions', colorClass: 'text-primary', points: ptsFrom(seo.series, 'impressions') }]} />
                                </ChartBox>
                            </div>
                        )}
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
                ) : null}
                {fb?.available && fb.series && fb.series.length >= 2 && (
                    <div className="mt-4 grid gap-4 sm:grid-cols-2">
                        <ChartBox title="Page Views">
                            <TrendChart series={[{ name: 'Page Views', colorClass: 'text-accent-info', points: ptsFrom(fb.series, 'page_views_total') }]} />
                        </ChartBox>
                        <ChartBox title="Engagements">
                            <TrendChart series={[{ name: 'Engagements', colorClass: 'text-sentiment-bull', points: ptsFrom(fb.series, 'page_post_engagements') }]} />
                        </ChartBox>
                    </div>
                )}
                {!fb?.available && (
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

            {/* 方格子 (vocus) reading */}
            <SectionCard
                icon={<BookOpen className="h-5 w-5 text-primary" />}
                title="方格子 Reading"
                subtitle="Lifetime reads across published articles — vocus keeps a running counter, so the trend lives in the growth chart below"
            >
                {vocus?.available ? (
                    <>
                        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                            <Stat icon={<BookOpen className="h-4 w-4" />} label="Reads" value={fmt(vocus.reads)} />
                            <Stat icon={<Hash className="h-4 w-4" />} label="Articles" value={fmt(vocus.articles)} />
                            <Stat icon={<Heart className="h-4 w-4" />} label="Likes" value={fmt(vocus.likes)} />
                            <Stat icon={<Bookmark className="h-4 w-4" />} label="Bookmarks" value={fmt(vocus.bookmarks)} />
                        </div>
                        {vocus.token?.expiring_soon && (
                            <p className="mt-3 text-xs text-primary">
                                方格子 token 即將到期，過期後閱讀數與發佈都會停止。
                            </p>
                        )}
                        {vocus.recent_posts && vocus.recent_posts.length > 0 && (
                            <SyndicationTable
                                rows={vocus.recent_posts}
                                countLabel="Reads"
                                count={(r) => r.reads}
                                engagementLabel="Likes"
                                engagement={(r) => r.likes}
                            />
                        )}
                    </>
                ) : (
                    <>
                        <NotConnected
                            detail={
                                vocus?.detail ||
                                (loading ? 'Loading…' : 'Set VOCUS_ID_TOKEN and VOCUS_USER_ID to enable vocus insights.')
                            }
                            href="https://vocus.cc/salon/tinboker"
                            cta="Open the vocus salon"
                        />
                        <SampleKeys keys={vocus?.sample_keys} />
                    </>
                )}
            </SectionCard>

            {/* Substack reading */}
            <SectionCard
                icon={<Mail className="h-5 w-5 text-orange-500" />}
                title="Substack Reading"
                subtitle="Lifetime views across published posts"
            >
                {substack?.available ? (
                    <>
                        <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                            <Stat icon={<Eye className="h-4 w-4" />} label="Views" value={fmt(substack.views)} />
                            <Stat icon={<Hash className="h-4 w-4" />} label="Posts" value={fmt(substack.posts)} />
                            <Stat icon={<Heart className="h-4 w-4" />} label="Reactions" value={fmt(substack.reactions)} />
                            <Stat icon={<MessageCircle className="h-4 w-4" />} label="Comments" value={fmt(substack.comments)} />
                        </div>
                        {substack.recent_posts && substack.recent_posts.length > 0 && (
                            <SyndicationTable
                                rows={substack.recent_posts}
                                countLabel="Views"
                                count={(r) => r.views}
                                engagementLabel="Reactions"
                                engagement={(r) => r.reactions}
                            />
                        )}
                    </>
                ) : (
                    <>
                        <NotConnected
                            detail={
                                substack?.detail ||
                                (loading
                                    ? 'Loading…'
                                    : 'Set SUBSTACK_SID, SUBSTACK_SUBDOMAIN and SUBSTACK_USER_ID to enable Substack insights.')
                            }
                            href="https://tinboker.substack.com/publish/posts"
                            cta="Open Substack"
                        />
                        <SampleKeys keys={substack?.sample_keys} />
                    </>
                )}
            </SectionCard>

            {/* Audience growth (daily snapshots) */}
            <SectionCard
                icon={<TrendingUp className="h-5 w-5 text-sentiment-bull" />}
                title="Audience Growth"
                subtitle="Daily follower snapshots · last 90 days"
            >
                <div className="mt-4">
                    <TrendChart
                        height={140}
                        series={[
                            { name: 'Threads 粉絲', colorClass: 'text-accent-info', points: history.map((s) => ({ x: s.day.slice(5), y: s.threads_followers ?? 0 })) },
                            { name: 'Facebook 粉絲', colorClass: 'text-primary', points: history.map((s) => ({ x: s.day.slice(5), y: s.fb_followers ?? 0 })) },
                            { name: 'FB 按讚', colorClass: 'text-sentiment-bull', points: history.map((s) => ({ x: s.day.slice(5), y: s.fb_fans ?? 0 })) },
                        ]}
                    />
                    {history.length < 2 && (
                        <p className="mt-2 text-xs text-muted-foreground">
                            每天自動記錄一次粉絲數，累積後即可看出成長曲線（剛啟用時為空）。
                        </p>
                    )}
                </div>
                {/* Reads are cumulative and an order of magnitude apart from follower
                    counts, so they get their own axis rather than flattening that one. */}
                <div className="mt-6">
                    <ChartBox title="Syndication Reads (lifetime)">
                        <TrendChart
                            height={140}
                            series={[
                                { name: '方格子 閱讀', colorClass: 'text-primary', points: readPoints((s) => s.vocus_reads) },
                                { name: 'Substack 閱讀', colorClass: 'text-orange-500', points: readPoints((s) => s.substack_reads) },
                            ]}
                        />
                    </ChartBox>
                    <p className="mt-2 text-xs text-muted-foreground">
                        累計閱讀數（每日快照）；兩點之間的差就是那天的閱讀量。
                    </p>
                </div>
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
                    <TrackingItem
                        label="方格子 (vocus)"
                        detail={vocus?.available
                            ? `Connected (reads via ${vocus.field_map?.reads || 'article list'})`
                            : vocus?.detail || 'Set VOCUS_ID_TOKEN to enable'}
                        status={vocus?.available ? 'active' : 'pending'}
                    />
                    <TrackingItem
                        label="Substack"
                        detail={substack?.available
                            ? `Connected (views via ${substack.field_map?.views || 'post list'})`
                            : substack?.detail || 'Set SUBSTACK_SID to enable'}
                        status={substack?.available ? 'active' : 'pending'}
                    />
                </ul>
            </div>
        </div>
    );
};
