/**
 * NewsletterCta — reusable subscription CTA block for article surfaces.
 *
 * Config-driven (see `@/config/site`): a single external destination + per-
 * placement zh-TW copy. Renders three visual variants:
 *   - `hero` — prominent banner above the article grid on /articles
 *   - `mid`  — compact inline card mid-article
 *   - `end`  — card below the article body
 *
 * Degrade-safe: renders `null` when no subscription URL is configured.
 * Emits impression (on first viewport entry) + click analytics events.
 */

import React, { useEffect, useRef } from 'react';
import { Mail, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { newsletter, isNewsletterEnabled, type NewsletterPlacement } from '@/config/site';
import { trackCtaEvent } from '@/lib/ctaAnalytics';

interface NewsletterCtaProps {
  placement: NewsletterPlacement;
  className?: string;
}

export const NewsletterCta: React.FC<NewsletterCtaProps> = ({ placement, className }) => {
  const ref = useRef<HTMLDivElement>(null);
  const seen = useRef(false);

  // Fire a single impression event when the CTA first enters the viewport.
  useEffect(() => {
    if (!isNewsletterEnabled()) return;
    const el = ref.current;
    if (!el || typeof IntersectionObserver === 'undefined') {
      // No observer support — count it as seen immediately.
      if (!seen.current) {
        seen.current = true;
        trackCtaEvent({ cta: 'newsletter', placement, action: 'impression' });
      }
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting && !seen.current) {
            seen.current = true;
            trackCtaEvent({ cta: 'newsletter', placement, action: 'impression' });
            observer.disconnect();
          }
        }
      },
      { threshold: 0.4 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [placement]);

  if (!isNewsletterEnabled()) return null;

  const copy = newsletter.copy[placement];
  const onClick = () =>
    trackCtaEvent({ cta: 'newsletter', placement, action: 'click' });

  const button = (
    <a
      href={newsletter.url}
      target="_blank"
      rel="noopener noreferrer"
      onClick={onClick}
      className={cn(
        'shrink-0 inline-flex items-center justify-center gap-2 rounded-full font-bold transition-all shadow-sm hover:shadow-md',
        'bg-accent-info text-accent-info-foreground hover:opacity-90',
        placement === 'mid' ? 'text-xs py-2 px-5' : 'text-sm py-2.5 px-6',
      )}
    >
      <span>{copy.cta}</span>
      <ArrowRight className="h-4 w-4" />
    </a>
  );

  if (placement === 'hero') {
    return (
      <div
        ref={ref}
        className={cn(
          'rounded-[var(--radius-md)] border border-accent-info/25 bg-accent-info-soft/40 p-5 sm:p-6',
          'flex flex-col sm:flex-row sm:items-center gap-4 sm:gap-6',
          className,
        )}
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1.5 text-accent-info">
            <Mail className="h-4 w-4 shrink-0" />
            <span className="text-xs font-semibold tracking-wide">{copy.eyebrow}</span>
          </div>
          <h2 className="text-lg sm:text-xl font-bold tracking-[-0.01em] text-foreground mb-1">
            {copy.title}
          </h2>
          <p className="text-sm text-muted-foreground leading-[1.5]">{copy.description}</p>
        </div>
        {button}
      </div>
    );
  }

  if (placement === 'mid') {
    return (
      <div
        ref={ref}
        className={cn(
          'not-prose my-8 rounded-[var(--radius-md)] border border-border bg-card p-4 sm:p-5',
          'flex flex-col sm:flex-row sm:items-center justify-between gap-3 sm:gap-5',
          className,
        )}
      >
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <Mail className="h-4 w-4 shrink-0 text-accent-info" />
            <span className="text-sm font-bold text-foreground">{copy.eyebrow}</span>
          </div>
          <p className="text-xs text-muted-foreground leading-[1.5]">{copy.description}</p>
        </div>
        {button}
      </div>
    );
  }

  // end
  return (
    <div
      ref={ref}
      className={cn(
        'mt-12 pt-8 border-t border-border',
        'flex flex-col sm:flex-row items-center justify-between gap-4',
        className,
      )}
    >
      <div className="text-center sm:text-left">
        <div className="flex items-center justify-center sm:justify-start gap-2 mb-1 text-accent-info">
          <Mail className="h-4 w-4 shrink-0" />
          <span className="text-xs font-semibold tracking-wide">{copy.eyebrow}</span>
        </div>
        <p className="text-base font-bold text-foreground mb-0.5">{copy.title}</p>
        <p className="text-xs text-muted-foreground">{copy.description}</p>
      </div>
      {button}
    </div>
  );
};
