import React from 'react';
import { Link } from 'react-router-dom';
import { Change } from '@/components/redesign';
import type { TrailingPerf } from '@/services/api/podcasts';

// Trailing windows, in column order. Labels live once in the table header
// (SectorPage) rather than being repeated on every row.
const KEYS: ('d1' | 'd7' | 'd30' | 'd90')[] = ['d1', 'd7', 'd30', 'd90'];

interface SectorTickerRowProps {
  ticker: string;
  name: string;
  perf?: TrailingPerf;
  loading?: boolean;
}

/**
 * One constituent row in the 成分股表現 table. Its columns align with the table
 * header (代號 · 名稱 | 1天 | 7天 | 30天 | 90天), so the timeframe labels appear
 * once for the whole table instead of on every card. <Change> applies the user's
 * TW/US color convention and renders a muted "—" for windows with no data.
 */
export const SectorTickerRow: React.FC<SectorTickerRowProps> = ({
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
      className="group flex items-center gap-1.5 px-4 py-2.5 hover:bg-muted/40 transition-colors"
    >
      <div className="flex-1 min-w-0 flex items-baseline gap-2">
        <span className="font-mono text-[13px] font-semibold tabular-nums text-foreground shrink-0 group-hover:text-accent-info transition-colors">
          {bare}
        </span>
        <span className="text-[12px] text-muted-foreground truncate">{name}</span>
      </div>
      {KEYS.map((key) => (
        <div key={key} className="w-[56px] text-right shrink-0">
          {awaiting ? (
            <span className="inline-block h-3 w-10 align-middle animate-pulse bg-muted rounded" />
          ) : (
            <Change value={perf ? perf[key] : null} className="text-[12px]" />
          )}
        </div>
      ))}
    </Link>
  );
};
