import { Link } from 'react-router-dom';
import { TrendingUp, ChevronDown } from 'lucide-react';
import type { Attention } from '@/validation/schemas';

/** The three market panels' headline facts on one scrollable line, anchoring down to the
 *  panels themselves.
 *
 *  The panels used to open the page, which put ~1,200px between a visitor and the first
 *  episode — on a phone the entire first screen was 本週市場在聊什麼 and 最多人聊, and
 *  someone arriving from a link about one episode had to scroll past all of it. The
 *  panels are the thing that makes this more than a list of podcasts, though, so they
 *  are not buried silently: this states what they say in ~52px and offers the rest.
 */
export function MarketDigestStrip({ data }: { data: Attention | null }) {
  if (!data) return <div className="h-[52px] rounded-[10px] bg-muted/40 animate-pulse" />;
  const topic = data.narratives?.[0];
  const ticker = data.tickers?.[0];
  const rising = data.rising?.[0];
  return (
    <a
      href="#market"
      aria-label="本週市場摘要，前往完整面板"
      className="flex items-center gap-2 rounded-[10px] border border-border bg-card pl-3.5 pr-2.5 py-2.5 text-sm transition-colors hover:border-primary/45"
    >
      {/* The facts scroll; the affordance does not. Inside the scroller it sat past the
          right edge on a phone — the one viewport where the panels are furthest away and
          the tap-through matters most. */}
      <span className="flex min-w-0 flex-1 items-center gap-3 overflow-x-auto scrollbar-thin">
        <span className="shrink-0 inline-flex items-center gap-1.5 text-2xs font-semibold uppercase tracking-wider text-muted-foreground">
          <TrendingUp size={13} className="text-primary" />
          本週
        </span>
        <span className="shrink-0 font-mono tabular-nums font-semibold">{data.episode_count_7d}</span>
        <span className="shrink-0 text-2xs text-muted-foreground -ml-2">集</span>
        {topic && (
          <span className="shrink-0 whitespace-nowrap">
            <span className="text-muted-foreground text-2xs mr-1.5">最熱</span>
            <span className="font-semibold">{topic.name}</span>
          </span>
        )}
        {ticker && (
          <span className="shrink-0 whitespace-nowrap">
            <span className="text-muted-foreground text-2xs mr-1.5">最多人聊</span>
            <span className="font-mono font-semibold">{ticker.ticker}</span>
          </span>
        )}
        {rising && (
          <span className="shrink-0 whitespace-nowrap">
            <span className="text-muted-foreground text-2xs mr-1.5">升溫</span>
            <span className="font-mono font-semibold text-accent-info">{rising.ticker}</span>
          </span>
        )}
      </span>
      <span aria-hidden className="shrink-0 inline-flex items-center gap-0.5 text-2xs font-medium text-accent-info">
        詳細
        <ChevronDown size={13} />
      </span>
    </a>
  );
}

/** Heading for the market panels in their new position below the feed. `scroll-mt`
 *  clears the sticky header so the strip's anchor does not land under it. */
export function MarketSectionHeading() {
  return (
    <h2 id="market" className="text-lg font-semibold tracking-[-0.02em] mt-6 mb-3.5 flex items-center gap-2 scroll-mt-20">
      <span aria-hidden className="inline-block w-[3px] h-[18px] rounded-sm bg-primary shrink-0" />
      本週市場
      <Link to="/topics" className="ml-auto text-2xs font-medium text-accent-info hover:underline">
        所有話題
      </Link>
    </h2>
  );
}
