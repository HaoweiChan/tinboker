import React from 'react';
import { Link } from 'react-router-dom';
import { Change } from '@/components/redesign';
import { SimpleSparkline } from '@/components/charts/SimpleSparkline';
import { useStockTrendColor } from '@/hooks/useStockTrendColor';
import type { TrailingPerf } from '@/services/api/podcasts';

export type Timeframe = 'd1' | 'd7' | 'd30' | 'd90';

interface SectorTickerCardProps {
  ticker: string;
  name: string;
  perf?: TrailingPerf;
  timeframe: Timeframe;
  loading?: boolean;
  reason?: string;
}

/**
 * Compact performance card for a sector/theme constituent. Shows the ticker,
 * name, the change % for the selected timeframe, a real daily-close sparkline,
 * and — when available — a one-line reason for why the ticker belongs to the
 * sector (Tavily-discovered). <Change> applies the user's TW/US color convention
 * and renders a muted "—" for windows with no data. The sparkline is drawn from
 * the same /batch-prices-trailing close series the change % comes from, so it is
 * honest (no fabricated points); cards with too little history just hide it.
 */
export const SectorTickerCard: React.FC<SectorTickerCardProps> = ({
  ticker,
  name,
  perf,
  timeframe,
  loading = false,
  reason,
}) => {
  const bare = ticker.replace(/\.[A-Z]+$/i, '');
  const awaiting = loading && !perf;
  const value = perf ? perf[timeframe] : null;
  const series = perf?.series && perf.series.length > 1 ? perf.series : undefined;
  const trend = useStockTrendColor(value ?? 0);

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

      <div className="flex items-end justify-between gap-2">
        {awaiting ? (
          <span className="inline-block h-[18px] w-16 animate-pulse bg-muted rounded" />
        ) : (
          <Change value={value} big />
        )}
        {series && (
          <SimpleSparkline
            data={series}
            isPositive={(value ?? 0) >= 0}
            color={value != null ? trend.lineColor : undefined}
            smooth
            strokeWidth={1.5}
            width={56}
            height={22}
            className="shrink-0 opacity-80"
          />
        )}
      </div>

      {reason && (
        <p className="text-[11px] leading-[1.5] text-muted-foreground/90 mt-0.5">
          {reason}
        </p>
      )}
    </Link>
  );
};
