import React from 'react';
import { Link } from 'react-router-dom';
import { Change } from '@/components/redesign';
import type { TrailingPerf } from '@/services/api/podcasts';

// Trailing windows shown inline on each card — same shape as the picks card's
// metrics row (PickCard), minus "自提及" which has no meaning without a mention date.
const METRICS: { key: 'd1' | 'd7' | 'd30' | 'd90'; label: string }[] = [
  { key: 'd1', label: '1天' },
  { key: 'd7', label: '7天' },
  { key: 'd30', label: '30天' },
  { key: 'd90', label: '90天' },
];

interface SectorTickerCardProps {
  ticker: string;
  name: string;
  perf?: TrailingPerf;
  loading?: boolean;
}

/**
 * Compact performance card for a sector/theme constituent — aligned with the
 * picks card (PickCard): ticker · name on top, then a grid of trailing
 * 1/7/30/90D returns. All windows are shown at once (no toggle); a window with
 * no data renders a clean "—" via <Change>. Color follows the user's TW/US
 * scheme (handled inside <Change>).
 */
export const SectorTickerCard: React.FC<SectorTickerCardProps> = ({
  ticker,
  name,
  perf,
  loading = false,
}) => {
  const bare = ticker.replace(/\.[A-Z]+$/i, '');
  const awaiting = loading && !perf;

  return (
    <Link
      to={`/stock/${encodeURIComponent(ticker)}`}
      className="group flex flex-col gap-2.5 bg-card rounded-lg p-3.5 overflow-hidden
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

      <div className="grid grid-cols-4 gap-1">
        {METRICS.map(({ key, label }) => (
          <div key={key} className="text-center">
            <div className="text-[9px] uppercase tracking-wide text-muted-foreground mb-0.5">{label}</div>
            {awaiting ? (
              <span className="inline-block h-3 w-9 animate-pulse bg-muted rounded" />
            ) : (
              <Change value={perf ? perf[key] : null} />
            )}
          </div>
        ))}
      </div>
    </Link>
  );
};
