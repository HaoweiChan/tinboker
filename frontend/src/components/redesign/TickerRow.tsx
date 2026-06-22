import React from 'react';
import { cn } from '@/lib/utils';
import type { Sentiment } from '@/lib/sentiment';
import { SentimentChip } from './SentimentChip';
import { Change } from './Change';
import { StockIdentity } from '@/components/common/StockIdentity';

export interface TickerRowData {
  symbol: string;            // e.g. 2330.TW, NVDA
  name?: string;             // resolved display_name from translation table (optional)
  sentiment?: Sentiment;     // LLM-derived; chip color follows the active price color mode
  changePercent?: number | null; // price change %; color follows the TW/US convention
  sinceLabel?: string | null;    // e.g. "播出至今" — shown next to changePercent when set
}

interface TickerRowProps {
  ticker: TickerRowData;
  onClick?: () => void;
  className?: string;
}

/** Inset row: [stock identity | sentiment chip | price change %].
 *  Identity is the canonical CODE + NAME (same colour, same size) via StockIdentity. */
export const TickerRow: React.FC<TickerRowProps> = ({ ticker, onClick, className }) => {
  const interactive = typeof onClick === 'function';
  const Tag = interactive ? 'button' : 'div';
  return (
    <Tag
      {...(interactive ? { type: 'button' as const, onClick } : {})}
      className={cn('ticker-row w-full text-left', interactive && 'hover:bg-muted transition-colors', className)}
    >
      <StockIdentity ticker={ticker.symbol} name={ticker.name} size="sm" className="min-w-0" />
      {ticker.sentiment ? <SentimentChip sentiment={ticker.sentiment} className="w-full justify-start" /> : <span />}
      <span className="flex items-baseline gap-1.5 justify-end">
        <Change value={ticker.changePercent} />
        {ticker.sinceLabel && (
          <span className="text-2xs text-muted-foreground whitespace-nowrap">{ticker.sinceLabel}</span>
        )}
      </span>
    </Tag>
  );
};
