import React from 'react';
import { Link } from 'react-router-dom';
import { Change } from '@/components/redesign';
import type { TrailingPerf } from '@/services/api/podcasts';

export type Timeframe = 'd1' | 'd7' | 'd30' | 'd90';

interface SectorTickerCardProps {
  ticker: string;
  name: string;
  perf?: TrailingPerf;
  timeframe: Timeframe;
  loading?: boolean;
}

/**
 * Compact performance card for a sector/theme constituent. Shows the ticker,
 * name, and the change % for the currently-selected timeframe — the toggle in
 * SectorPage is the single label, so nothing is repeated per card. <Change>
 * applies the user's TW/US color convention and renders a muted "—" for windows
 * with no data. No sparkline (daily-close history is too shallow / rate-limited
 * to draw an honest per-window curve).
 */
export const SectorTickerCard: React.FC<SectorTickerCardProps> = ({
  ticker,
  name,
  perf,
  timeframe,
  loading = false,
}) => {
  const bare = ticker.replace(/\.[A-Z]+$/i, '');
  const awaiting = loading && !perf;
  const value = perf ? perf[timeframe] : null;

  return (
    <Link
      to={`/stock/${encodeURIComponent(ticker)}`}
      className="group flex flex-col gap-1.5 bg-card rounded-lg p-3.5 overflow-hidden
                 border border-border dark:border-white/[0.08]
                 hover:border-border/80 dark:hover:border-white/[0.14]
                 shadow-[0_1px_2px_rgba(0,0,0,0.04)] dark:shadow-none transition-all duration-200"
    >
      <div className="flex items-baseline gap-2 min-w-0">
        <span className="font-mono text-[13px] font-semibold tabular-nums text-foreground shrink-0 group-hover:text-accent-info transition-colors">
          {bare}
        </span>
        <span className="text-[12px] text-muted-foreground truncate">{name}</span>
      </div>
      {awaiting ? (
        <span className="inline-block h-[18px] w-16 animate-pulse bg-muted rounded" />
      ) : (
        <Change value={value} big />
      )}
    </Link>
  );
};
