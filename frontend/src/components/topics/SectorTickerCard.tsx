import React from 'react';
import { Link } from 'react-router-dom';
import { useStockTrendColor } from '@/hooks/useStockTrendColor';
import { SimpleSparkline } from '@/components/charts/SimpleSparkline';
import { ChangePct } from './ChangePct';
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
 * Mini performance card for a sector/theme constituent.
 * Ticker · name · smooth sparkline · active-timeframe change %.
 * Color follows the user's TW/US scheme via useStockTrendColor; switching the
 * timeframe re-colors the % and sparkline to that window's direction.
 */
export const SectorTickerCard: React.FC<SectorTickerCardProps> = ({
  ticker,
  name,
  perf,
  timeframe,
  loading = false,
}) => {
  const value = perf ? perf[timeframe] : null;
  const trend = useStockTrendColor(value ?? 0);
  const hasValue = value != null && Number.isFinite(value);
  const series = perf?.series && perf.series.length > 1 ? perf.series : undefined;
  const bare = ticker.replace(/\.[A-Z]+$/i, '');
  const awaiting = loading && !perf;

  return (
    <Link
      to={`/stock/${encodeURIComponent(ticker)}`}
      className="group flex flex-col gap-2 bg-card rounded-lg p-3 overflow-hidden
                 border border-border dark:border-white/[0.08]
                 hover:border-border/80 dark:hover:border-white/[0.14]
                 shadow-[0_1px_2px_rgba(0,0,0,0.04)] dark:shadow-none
                 transition-all duration-200"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-mono text-[10px] text-muted-foreground tabular-nums leading-none mb-1">
            {bare}
          </div>
          <div className="text-[12px] font-medium truncate leading-tight group-hover:text-foreground/80 transition-colors">
            {name}
          </div>
        </div>
        {awaiting ? (
          <span className="inline-block h-3 w-10 animate-pulse bg-muted rounded mt-0.5 shrink-0" />
        ) : (
          <ChangePct value={value} sizeClass="text-[12px]" />
        )}
      </div>

      <div className="h-[26px]">
        {series ? (
          <SimpleSparkline
            data={series}
            isPositive={(value ?? 0) >= 0}
            color={hasValue ? trend.lineColor : '#94a3b8'}
            smooth
            strokeWidth={1.5}
            width={120}
            height={26}
            className={`w-full h-full ${hasValue ? '' : 'opacity-50'}`}
          />
        ) : awaiting ? (
          <span className="block w-full h-[14px] mt-1.5 animate-pulse bg-muted rounded" />
        ) : (
          <div className="w-full h-full" />
        )}
      </div>
    </Link>
  );
};
