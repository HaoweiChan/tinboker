import React, { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { cn } from '@/lib/utils';
import { useTranslationMap } from '@/hooks/useTranslationMap';
import type { Episode as ApiEpisode } from '@/services/api';

interface CoMentionTileProps {
  symbol: string;
  episodes: ApiEpisode[];
  className?: string;
  max?: number;
}

/** Tickers that share episodes with this one, by number of shared episodes. */
export const CoMentionTile: React.FC<CoMentionTileProps> = ({ symbol, episodes, className, max = 6 }) => {
  const rows = useMemo(() => {
    const me = symbol.toUpperCase();
    const counts = new Map<string, number>();
    for (const ep of episodes) {
      const set = new Set((ep.related_tickers ?? []).map((t) => t.toUpperCase()));
      if (!set.has(me)) continue;
      for (const t of set) if (t !== me) counts.set(t, (counts.get(t) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, max).map(([ticker, n]) => ({ ticker, n }));
  }, [symbol, episodes, max]);
  const tickers = useMemo(() => rows.map((r) => r.ticker), [rows]);
  const names = useTranslationMap(tickers);
  if (rows.length === 0) return null;

  return (
    <div className={cn('bg-card border border-border rounded-[10px] p-5 flex flex-col gap-2.5', className)}>
      <div className="text-xs text-muted-foreground">常一起被提到</div>
      <div className="flex flex-wrap gap-x-3 gap-y-1.5 text-sm">
        {rows.map((r) => (
          <Link key={r.ticker} to={`/stock/${encodeURIComponent(r.ticker)}`} className="hover:text-primary transition-colors whitespace-nowrap">
            <span className="font-mono">{r.ticker}</span>{names.get(r.ticker)?.displayName ? ` ${names.get(r.ticker)!.displayName}` : ''}
            <span className="ml-1 text-xs font-mono tabular-nums text-muted-foreground">{r.n}</span>
          </Link>
        ))}
      </div>
    </div>
  );
};
