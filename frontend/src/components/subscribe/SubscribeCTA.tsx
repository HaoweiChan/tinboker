/**
 * SubscribeCTA — reusable subscription call-to-action block (issue #424).
 *
 * Links into the TinBoker-owned outbound funnel at `/subscribe?source=<slot>`, so every
 * placement is attributable. The `source` slot names where the click came from
 * (e.g. "article_detail_end", "articles_hero", "ticker_page") and MUST stay in sync with
 * docs/features/subscription-funnel.md so top-CTA analytics stay comparable over time.
 *
 * Two variants: `card` (full block, default) for end-of-content, and `inline` (compact
 * button) for tighter slots. This is the shared building block issue #423 can drop into
 * more surfaces without re-plumbing attribution.
 */
import React from 'react';
import { Link } from 'react-router-dom';
import { Mail } from 'lucide-react';

interface SubscribeCTAProps {
    /** Attribution slot — snake_case, documented in subscription-funnel.md. */
    source: string;
    variant?: 'card' | 'inline';
    title?: string;
    description?: string;
    className?: string;
}

export const SubscribeCTA: React.FC<SubscribeCTAProps> = ({
    source,
    variant = 'card',
    title = '訂閱 TinBoker 電子報',
    description = '每週精選台股與 podcast 智慧摘要，直接送到你的信箱。',
    className = '',
}) => {
    // Route through the internal landing page (records a view + carries attribution),
    // which then hands off to the config-driven outbound destination.
    const to = `/subscribe?source=${encodeURIComponent(source)}`;

    if (variant === 'inline') {
        return (
            <Link
                to={to}
                className={`inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:opacity-90 ${className}`}
            >
                <Mail className="h-4 w-4" />
                訂閱電子報
            </Link>
        );
    }

    return (
        <div
            className={`rounded-xl border border-border bg-card p-6 text-center ${className}`}
        >
            <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
                <Mail className="h-5 w-5 text-primary" />
            </div>
            <h3 className="text-lg font-semibold text-foreground">{title}</h3>
            <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">{description}</p>
            <Link
                to={to}
                className="mt-4 inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:opacity-90"
            >
                <Mail className="h-4 w-4" />
                免費訂閱
            </Link>
        </div>
    );
};
