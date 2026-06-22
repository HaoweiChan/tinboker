import React from 'react';
import { Link } from 'react-router-dom';
import { Change } from '@/components/redesign';
import { StockIdentity } from '@/components/common/StockIdentity';
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
  const awaiting = loading && !perf;
  const value = perf ? perf[timeframe] : null;
  const series = perf?.series && perf.series.length > 1 ? perf.series : undefined;
  const trend = useStockTrendColor(value ?? 0);

  return (
    <Link
      to={`/stock/${encodeURIComponent(ticker)}`}
      className="group flex flex-col gap-2 bg-card rounded-lg p-4 overflow-hidden
                 border border-border dark:border-white/[0.08]
                 hover:border-border/80 dark:hover:border-white/[0.14]
                 shadow-[0_1px_2px_rgba(0,0,0,0.04)] dark:shadow-none transition-all duration-200"
    >
      {/* Name — the card's headline; canonical CODE + NAME (same colour, same size) */}
      <StockIdentity
        ticker={ticker}
        name={name}
        size="md"
        codeClassName="group-hover:text-accent-info transition-colors"
        className="gap-2"
      />

      <div className="flex items-end justify-between gap-2">
        {awaiting ? (
          <span className="inline-block h-[26px] w-20 animate-pulse bg-muted rounded" />
        ) : (
          <Change value={value} big className="text-2xl" />
        )}
        {series && (
          <SimpleSparkline
            data={series}
            isPositive={(value ?? 0) >= 0}
            color={value != null ? trend.lineColor : undefined}
            smooth
            strokeWidth={1.5}
            width={64}
            height={26}
            className="shrink-0 opacity-80"
          />
        )}
      </div>

      {reason && (
        <p className="text-xs leading-[1.6] text-muted-foreground mt-1 pt-2.5 border-t border-border/60">
          {reason}
        </p>
      )}
    </Link>
  );
};
