import React from 'react';
import { Link } from 'react-router-dom';
import { Tile } from '@/components/redesign/Tile';
import { useGrowIn } from '@/hooks/useMotion';
import type { AttentionTicker } from '@/validation/schemas';

interface Props {
  rows: AttentionTicker[];
}

/** Layer ② right: tickers heating up — 7-day mentions vs the prior 7 days, ordered by
 *  the backend's momentum score (volume floors keep 2 → 4 jumps off the board). Shows
 *  the absolute gain, not a percent: a 1 → 7 jump reading "+600%" would outshout the
 *  6 → 15 row the score actually ranks first. */
export const RisingTable: React.FC<Props> = ({ rows }) => {
  const grown = useGrowIn();
  return (
    <Tile title="升溫最快" aside="近 7 天 · 較前 7 天 — 熱門 ≠ 正在升溫" className="h-full">
      {rows.length === 0 ? (
        <div className="h-40 animate-pulse bg-muted/40 rounded-md" />
      ) : (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-2xs text-muted-foreground font-normal">
              <th className="text-left font-normal pb-1.5 border-b border-border">股票</th>
              <th className="text-right font-normal pb-1.5 border-b border-border">近 7 天</th>
              <th className="text-right font-normal pb-1.5 border-b border-border">前 7 天</th>
              <th className="text-right font-normal pb-1.5 border-b border-border">增加</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
                const cell = { opacity: grown ? 1 : 0, transform: grown ? 'none' : 'translateX(-8px)', transition: 'opacity 400ms, transform 500ms cubic-bezier(0.22, 1, 0.36, 1)', transitionDelay: `${i * 80}ms` } as const;
              return (
                <tr key={r.ticker} className="border-b border-border last:border-0">
                  <td className="py-2 whitespace-nowrap" style={cell}>
                    <Link to={`/stock/${encodeURIComponent(r.ticker)}`} className="font-semibold font-mono hover:text-primary transition-colors">
                      {r.ticker}{r.name && <span className="ml-1.5 font-sans font-normal text-xs text-muted-foreground inline-block align-bottom truncate max-w-[72px] sm:max-w-[160px]">{r.name}</span>}
                    </Link>
                    {r.prev_7d <= 1 && <span className="ml-1.5 align-[1px] text-2xs text-accent-info border border-accent-info rounded px-1">NEW</span>}
                  </td>
                  <td className="py-2 text-right font-mono tabular-nums" style={cell}>{r.count_7d}</td>
                  <td className="py-2 text-right font-mono tabular-nums text-muted-foreground" style={cell}>{r.prev_7d}</td>
                  <td className="py-2 text-right font-mono tabular-nums font-semibold text-sentiment-bull whitespace-nowrap" style={cell}>+{r.count_7d - r.prev_7d} <span className="text-2xs font-normal">集</span></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Tile>
  );
};
