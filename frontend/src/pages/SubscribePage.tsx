/**
 * /subscribe — TinBoker-owned newsletter subscription landing (issue #424).
 *
 * The stable internal entry point for subscription intent. It:
 *   1. reads the `?source=` attribution slot (which CTA sent the user),
 *   2. records a landing-view beacon for the funnel analytics,
 *   3. hands off to the config-driven outbound destination (Substack today) via the
 *      backend `/api/subscribe` redirect, which records the outbound click.
 *
 * No email field, no account linkage, no payment — this is outbound funnel plumbing only.
 * The actual signup happens on the external newsletter host.
 */
import React, { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Mail, ExternalLink, CheckCircle } from 'lucide-react';
import { PageContent } from '@/components/layout/PageContent';
import { SEO } from '@/components/common/SEO';
import { subscribeOutboundUrl, trackSubscribeView } from '@/services/api/analytics';

const BENEFITS = [
    '每週台股與美股重點整理',
    'Podcast 智慧摘要與 ticker 情緒分析',
    '不寄垃圾信，隨時可退訂',
];

export const SubscribePage: React.FC = () => {
    const [params] = useSearchParams();
    // `subscribe_page` is the fallback slot for direct visits (nav, shared link).
    const source = params.get('source') || 'subscribe_page';
    const outboundUrl = subscribeOutboundUrl(source);

    useEffect(() => {
        // Fire-and-forget landing view, attributed to the referring CTA slot.
        void trackSubscribeView(source);
    }, [source]);

    return (
        <PageContent className="max-w-[640px]">
            <SEO
                title="訂閱電子報"
                description="訂閱 TinBoker 電子報，每週精選台股與 podcast 智慧摘要，直接送到你的信箱。"
                url="https://tinboker.com/subscribe"
            />
            <div className="rounded-2xl border border-border bg-card p-8 text-center">
                <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-primary/10">
                    <Mail className="h-7 w-7 text-primary" />
                </div>
                <h1 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
                    訂閱 TinBoker 電子報
                </h1>
                <p className="mx-auto mt-2 max-w-md text-base text-muted-foreground">
                    每週精選台股與 podcast 智慧摘要，直接送到你的信箱。
                </p>

                <ul className="mx-auto mt-6 max-w-sm space-y-2 text-left">
                    {BENEFITS.map((b) => (
                        <li key={b} className="flex items-start gap-2 text-sm text-foreground">
                            <CheckCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-sentiment-bull" />
                            <span>{b}</span>
                        </li>
                    ))}
                </ul>

                {/* Anchor (not SPA Link): the backend records the click then redirects
                    to the external newsletter host. */}
                <a
                    href={outboundUrl}
                    className="mt-7 inline-flex items-center gap-2 rounded-lg bg-primary px-6 py-3 text-base font-semibold text-primary-foreground transition-colors hover:opacity-90"
                >
                    前往訂閱
                    <ExternalLink className="h-4 w-4" />
                </a>
                <p className="mt-3 text-xs text-muted-foreground">
                    你將前往我們的電子報平台完成訂閱。
                </p>
            </div>
        </PageContent>
    );
};
