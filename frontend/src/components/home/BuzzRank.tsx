import React from 'react';
import { Link } from 'react-router-dom';
import { HomePanel } from './HomePanel';
import type { AttentionTicker } from '@/validation/schemas';
import { Bar } from './Bar';
import { DeltaText } from './DeltaText';

interface Props {
  rows: AttentionTicker[];
}

/** Layer ② left: most-discussed tickers over 30 days. The bar encodes mention count
 *  only — sentiment lives on the stock page. */
export const BuzzRank: React.FC<Props> = ({ rows }) => {
  const max = Math.max(1, ...rows.map((r) => r.count_30d));
  return (
    <HomePanel title="最多人聊" aside="近 30 天提及集數 · 較前期變化">
      {rows.length === 0 ? (
        <div className="h-40 animate-pulse bg-muted/40 rounded-md" />
      ) : (
        <div className="grid grid-cols-[auto_1fr_auto_auto] items-center gap-x-3 sm:gap-x-4 gap-y-2.5 text-sm">
          {rows.map((r, i) => {
            return (
              <React.Fragment key={r.ticker}>
                <Link to={`/stock/${encodeURIComponent(r.ticker)}`} className="font-semibold font-mono whitespace-nowrap hover:text-primary transition-colors">
                  <span className={`text-2xs tabular-nums mr-1.5 ${i === 0 ? 'text-primary' : 'text-muted-foreground/60'}`}>{String(i + 1).padStart(2, '0')}</span>
                  {r.ticker}{r.name && <span className="ml-1.5 font-sans font-normal text-sm text-muted-foreground">{r.name}</span>}
                </Link>
                <Bar value={r.count_30d} max={max} tone="ticker" delayMs={i * 60} />
                <span className="font-mono tabular-nums text-right">{r.count_30d} <span className="text-2xs text-muted-foreground">集</span></span>
                <span className="text-right min-w-[48px] font-semibold"><DeltaText now={r.count_30d} prev={r.prev_30d} /></span>
              </React.Fragment>
            );
          })}
        </div>
      )}
    </HomePanel>
  );
};
