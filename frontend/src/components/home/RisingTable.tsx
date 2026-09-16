import React from 'react';
import { Link } from 'react-router-dom';
import type { AttentionTicker } from '@/validation/schemas';
import { Bar } from './Bar';
import { HomePanel } from './HomePanel';

interface Props {
  rows: AttentionTicker[];
}

/** Layer ② right: tickers heating up — 7-day mentions vs the prior 7 days, ordered by
 *  the backend's momentum score (volume floors keep 2 → 4 jumps off the board). Shows
 *  the absolute gain, not a percent: a 1 → 7 jump reading "+600%" would outshout the
 *  6 → 15 row the score actually ranks first.
 *
 *  Same rows as 本週市場在聊什麼 above, in the momentum teal — as a bare table of small
 *  grey numbers it disappeared next to that panel. The bar encodes the 7-day count, and
 *  the prior week rides along as the muted 「前 N」 so the gain still reads as a change,
 *  not a level. */
export const RisingTable: React.FC<Props> = ({ rows }) => {
  const max = Math.max(1, ...rows.map((r) => r.count_7d));
  return (
    <HomePanel title="升溫最快" aside="近 7 天 · 較前 7 天 — 熱門 ≠ 正在升溫">
      {rows.length === 0 ? (
        <div className="h-40 animate-pulse bg-muted/40 rounded-md" />
      ) : (
        <div className="grid grid-cols-[auto_1fr_auto_auto] items-center gap-x-3 sm:gap-x-4 gap-y-2.5 text-sm">
          {rows.map((r, i) => (
            <React.Fragment key={r.ticker}>
              <Link to={`/stock/${encodeURIComponent(r.ticker)}`} className="font-semibold font-mono whitespace-nowrap hover:text-primary transition-colors">
                {r.ticker}
                {r.name && <span className="ml-1.5 font-sans font-normal text-sm text-muted-foreground inline-block align-bottom truncate max-w-[72px] sm:max-w-[120px]">{r.name}</span>}
                {r.prev_7d <= 1 && <span className="ml-1.5 align-[1px] text-2xs text-accent-info border border-accent-info rounded px-1">NEW</span>}
              </Link>
              <Bar value={r.count_7d} max={max} tone="momentum" delayMs={i * 60} />
              <span className="font-mono tabular-nums text-right whitespace-nowrap">
                {r.count_7d} <span className="text-2xs text-muted-foreground">前 {r.prev_7d}</span>
              </span>
              <span className="text-right min-w-[48px] font-semibold font-mono tabular-nums text-sentiment-bull whitespace-nowrap">
                +{r.count_7d - r.prev_7d} <span className="text-2xs font-normal">集</span>
              </span>
            </React.Fragment>
          ))}
        </div>
      )}
    </HomePanel>
  );
};
