/**
 * SubscribeCTA — reusable subscription call-to-action block (issue #425).
 *
 * Points readers from the free public web edition to the paid full edition.
 * Reused across article detail, article list, and (later, #423) other surfaces.
 */

import { ArrowUpRight, Mail } from 'lucide-react';
import { resolveSubscribeUrl } from '@/lib/subscription';

interface SubscribeCTAProps {
  /** Per-article override; falls back to the global VITE_SUBSTACK_URL. */
  subscribeUrl?: string | null;
  /** Headline copy. */
  title?: string;
  /** Supporting line under the headline. */
  description?: string;
  /** Button label. */
  cta?: string;
  /** Compact single-line variant for list footers. */
  variant?: 'card' | 'inline';
  className?: string;
}

export const SubscribeCTA: React.FC<SubscribeCTAProps> = ({
  subscribeUrl,
  title = '訂閱完整版',
  description = '在 TinBoker 讀公開摘要，在 Substack 收到完整分析、後續追蹤與可執行的觀察名單。',
  cta = '前往訂閱',
  variant = 'card',
  className = '',
}) => {
  const href = resolveSubscribeUrl(subscribeUrl);
  const isExternal = /^https?:\/\//.test(href);

  if (variant === 'inline') {
    return (
      <a
        href={href}
        target={isExternal ? '_blank' : undefined}
        rel={isExternal ? 'noopener noreferrer' : undefined}
        data-analytics="subscribe-cta"
        data-analytics-variant="inline"
        className={`inline-flex items-center gap-1.5 text-sm font-medium text-accent-info hover:underline ${className}`}
      >
        <Mail className="h-4 w-4" />
        {title}
        <ArrowUpRight className="h-3.5 w-3.5" />
      </a>
    );
  }

  return (
    <div
      className={`rounded-[var(--radius-md)] border border-accent-info/30 bg-accent-info-soft/40 p-5 ${className}`}
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent-info/15 text-accent-info">
          <Mail className="h-4.5 w-4.5" />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="text-base font-semibold text-foreground">{title}</h3>
          <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{description}</p>
          <a
            href={href}
            target={isExternal ? '_blank' : undefined}
            rel={isExternal ? 'noopener noreferrer' : undefined}
            data-analytics="subscribe-cta"
            data-analytics-variant="card"
            className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-accent-info px-4 py-2 text-sm font-medium text-accent-info-foreground transition-colors hover:bg-accent-info/90"
          >
            {cta}
            <ArrowUpRight className="h-4 w-4" />
          </a>
        </div>
      </div>
    </div>
  );
};
