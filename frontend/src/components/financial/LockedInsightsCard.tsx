import React from 'react';
import { Link } from 'react-router-dom';
import { Lock } from 'lucide-react';
import { INSIGHT_PAYWALL_DAYS } from '@/lib/insightPaywall';

/**
 * Stands in for the 觀點 from the last week that a non-member doesn't get.
 *
 * It states the count and nothing else — the gated rows are filtered out upstream
 * and never render, so there is no text here to un-blur or read out of the DOM.
 */
export const LockedInsightsCard: React.FC<{ count: number }> = ({ count }) => (
  <div className="mb-2 flex items-center gap-3 rounded-md border border-dashed border-border bg-card/60 px-4 py-3">
    <span className="grid place-items-center h-8 w-8 shrink-0 rounded-full bg-muted text-muted-foreground">
      <Lock size={15} />
    </span>
    <div className="min-w-0 flex-1">
      <div className="text-sm font-medium text-foreground">
        近 {INSIGHT_PAYWALL_DAYS} 天還有 {count} 則觀點
      </div>
      <p className="mt-0.5 text-xs leading-[1.5] text-muted-foreground">
        最新一週的 Podcast 點名與漲跌幅是會員內容，先前的都可以免費看。
      </p>
    </div>
    <Link
      to="/member?tab=picks"
      className="shrink-0 rounded-md bg-foreground px-3 py-1.5 text-xs font-semibold text-background hover:opacity-90 transition-opacity"
    >
      升級
    </Link>
  </div>
);
