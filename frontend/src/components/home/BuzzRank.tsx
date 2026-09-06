import React from 'react';
import { Link } from 'react-router-dom';
import { Tile } from '@/components/redesign/Tile';
import { useGrowIn } from '@/hooks/useMotion';
import type { AttentionTicker } from '@/validation/schemas';
import { DeltaText } from './DeltaText';

interface Props {
  rows: AttentionTicker[];
}

/** Layer ② left: most-discussed tickers over 30 days. The bar encodes mention count
 *  only — sentiment lives on the stock page. */
export const BuzzRank: React.FC<Props> = ({ rows }) => {
  const max = Math.max(1, ...rows.map((r) => r.count_30d));
  const grown = useGrowIn();
  return (
    <Tile title="最多人聊" aside="近 30 天提及集數 · 較前期變化" className="h-full">
      {rows.length === 0 ? (
        <div className="h-40 animate-pulse bg-muted/40 rounded-md" />
      ) : (
        <div className="grid grid-cols-[auto_1fr_auto_auto] items-center gap-x-3 gap-y-2 text-sm">
          {rows.map((r, i) => {
            return (
              <React.Fragment key={r.ticker}>
                <Link to={`/stock/${encodeURIComponent(r.ticker)}`} className="font-semibold font-mono whitespace-nowrap hover:text-primary transition-colors">
                  {r.ticker}{r.name && <span className="ml-1.5 font-sans font-normal text-xs text-muted-foreground">{r.name}</span>}
                </Link>
                <span className="h-3.5 rounded-[3px] bg-muted overflow-hidden">
                  <span className="block h-full bg-primary/85 rounded-[3px]" style={{ width: grown ? `${(r.count_30d / max) * 100}%` : '0%', transition: 'width 900ms cubic-bezier(0.22, 1, 0.36, 1)', transitionDelay: `${i * 60}ms` }} />
                </span>
                <span className="font-mono tabular-nums text-muted-foreground text-right">{r.count_30d}</span>
                <span className="text-right min-w-[48px] font-semibold"><DeltaText now={r.count_30d} prev={r.prev_30d} /></span>
              </React.Fragment>
            );
          })}
        </div>
      )}
    </Tile>
  );
};
